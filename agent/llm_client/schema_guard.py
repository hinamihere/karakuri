"""Schema guard for the LLM action contract — contracts.md §4.

The guard is the only thing standing between a language model and the
dispatcher. It parses the model's message content and either returns a typed
:class:`ActionContract` or a rejection carrying the ``error_category`` that
telemetry must record. It never executes anything.

Category precedence (§2.2 + §4.3 read together), checked in this order so the
outcome is deterministic:

1. body is not JSON / not a JSON object      → ``llm_malformed_json``
2. ``action`` key absent                     → ``llm_malformed_json`` (§2.2:
   "valid JSON but missing required action-contract fields")
3. ``action`` present but outside the enum   → ``llm_unknown_action`` (§4.3 r1)
4. any other guard rule                      → ``llm_schema_violation`` (§4.3
   r2–r6, and §4.2's per-action required ``value``)

Rules 2 and 3 are the two halves of §2.2's split: the neighbouring rows assign
"missing required fields" to ``llm_malformed_json`` and "missing ``target_id`` /
``is_destructive absent``" to ``llm_schema_violation``, so a missing ``action``
(the field whose absence means there is no action contract at all) is the
malformed case while the other required fields stay schema violations, exactly
as §4.3 rules 2 and 3 say.

``target_id`` is required for *every* action, including ``finish``/``fail``
(§4.1 ``required``, §4.3 rule 2 unconditional). §4.2's "optional" rows describe
what the dispatcher consumes, not what the wire format may omit — so the prompt
shown to the model must always ask for a ``target_id``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

#: §4.1 enum, in contract order.
ACTION_VALUES: Final[tuple[str, ...]] = (
    "click",
    "set_value",
    "select",
    "wait",
    "finish",
    "fail",
)

#: §4.1 ``required``.
REQUIRED_KEYS: Final[tuple[str, ...]] = ("action", "target_id", "is_destructive")

#: §4.1 ``properties`` — ``additionalProperties: false`` covers everything else.
CONTRACT_KEYS: Final[frozenset[str]] = frozenset(
    {"thought", "value"} | set(REQUIRED_KEYS)
)

#: Internal marker added by :func:`_object_pairs_hook` when the payload repeats
#: a key. Never part of the contract — see the extras check below.
DUPLICATE_MARKER: Final[str] = "__duplicate_keys__"

#: §4.2: actions that cannot run without a payload value.
VALUE_REQUIRED_ACTIONS: Final[tuple[str, ...]] = ("set_value", "select")

#: §4.1 ``maxLength`` / §4.3 rule 5.
MAX_THOUGHT_CHARS: Final[int] = 500

MALFORMED: Final[str] = "llm_malformed_json"
UNKNOWN_ACTION: Final[str] = "llm_unknown_action"
SCHEMA_VIOLATION: Final[str] = "llm_schema_violation"


@dataclass(frozen=True)
class ActionContract:
    """A validated §4.1 object, ready to hand to the Mode B dispatcher."""

    action: str
    target_id: int
    is_destructive: bool
    value: str | None = None
    thought: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Contract key order, for telemetry ``llm_output`` on success (§2.3)."""
        return {
            "thought": self.thought,
            "action": self.action,
            "target_id": self.target_id,
            "value": self.value,
            "is_destructive": self.is_destructive,
        }


@dataclass(frozen=True)
class GuardRejection:
    """Why a response was refused. ``detail`` is safe to log (no secrets)."""

    error_category: str
    detail: str
    rule: str


def _reject(category: str, detail: str, rule: str) -> GuardRejection:
    return GuardRejection(error_category=category, detail=detail, rule=rule)


def _as_int(value: Any) -> int | None:
    """JSON-Schema ``integer`` semantics: integral numbers, never booleans.

    ``4`` and ``4.0`` both mean node 4 (§4.1 ``type: integer`` accepts an
    integral number); ``"4"`` (§4.3 rule 2: *string \"4\" is rejected*), ``4.5``,
    ``true``, ``NaN`` and ``Infinity`` do not.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def validate_action_contract(payload: Any) -> ActionContract | GuardRejection:
    """Validate an already-parsed JSON value against §4.1/§4.3.

    Checks run in the fixed order documented in the module docstring; the first
    failure wins, so the same payload always produces the same category.
    """
    if not isinstance(payload, dict):
        return _reject(
            MALFORMED,
            f"response is not a JSON object (got {type(payload).__name__}) — "
            "no action contract present",
            "§2.2 llm_malformed_json",
        )

    # §4.3 rule 1 — a present action must be one of the six values.
    if "action" not in payload:
        return _reject(
            MALFORMED,
            "required field 'action' is missing — valid JSON without an "
            "action-contract field",
            "§2.2 llm_malformed_json",
        )
    action = payload["action"]
    if not isinstance(action, str) or action not in ACTION_VALUES:
        return _reject(
            UNKNOWN_ACTION,
            f"action {action!r} is not one of {list(ACTION_VALUES)}",
            "§4.3 rule 1",
        )

    # §4.3 rule 2 — target_id, integer ≥ 1, unconditionally required.
    if "target_id" not in payload:
        return _reject(
            SCHEMA_VIOLATION, "required field 'target_id' is missing", "§4.3 rule 2"
        )
    target_id = _as_int(payload["target_id"])
    if target_id is None:
        return _reject(
            SCHEMA_VIOLATION,
            f"target_id must be an integer ≥ 1, got {payload['target_id']!r} "
            "(a string such as \"4\" is rejected)",
            "§4.3 rule 2",
        )
    if target_id < 1:
        return _reject(
            SCHEMA_VIOLATION,
            f"target_id must be ≥ 1, got {target_id}",
            "§4.3 rule 2",
        )

    # §4.3 rule 3 — is_destructive, boolean, unconditionally required.
    if "is_destructive" not in payload:
        return _reject(
            SCHEMA_VIOLATION,
            "required field 'is_destructive' is missing",
            "§4.3 rule 3",
        )
    if not isinstance(payload["is_destructive"], bool):
        return _reject(
            SCHEMA_VIOLATION,
            f"is_destructive must be a boolean, got "
            f"{payload['is_destructive']!r}",
            "§4.3 rule 3",
        )

    # §4.3 rule 4 — value is string | null, optional.
    value = payload.get("value")
    if value is not None and not isinstance(value, str):
        return _reject(
            SCHEMA_VIOLATION,
            f"value must be a string or null, got {type(value).__name__}",
            "§4.3 rule 4",
        )

    # §4.3 rule 5 — thought is a string, silently capped at 500 chars.
    thought = payload.get("thought")
    if thought is not None and not isinstance(thought, str):
        return _reject(
            SCHEMA_VIOLATION,
            f"thought must be a string, got {type(thought).__name__}",
            "§4.3 rule 5",
        )

    # §4.3 rule 6 — additionalProperties: false. Duplicate keys are refused
    # here too: a payload whose is_destructive appears twice parses differently
    # in different libraries, and a parser difference at this boundary could
    # route a destructive action past the overlay guard.
    duplicates = payload.get(DUPLICATE_MARKER)
    if duplicates:
        return _reject(
            SCHEMA_VIOLATION,
            f"duplicate field(s): {', '.join(duplicates)}",
            "§4.3 rule 6",
        )
    extras = sorted(
        k for k in payload if k not in CONTRACT_KEYS and k != DUPLICATE_MARKER
    )
    if extras:
        return _reject(
            SCHEMA_VIOLATION,
            f"unexpected field(s): {', '.join(extras)}",
            "§4.3 rule 6",
        )

    # §4.2 — per-action required fields.
    if action in VALUE_REQUIRED_ACTIONS and value is None:
        return _reject(
            SCHEMA_VIOLATION,
            f"'{action}' requires a non-null 'value' (contracts.md §4.2)",
            "§4.2",
        )

    return ActionContract(
        action=action,
        target_id=target_id,
        is_destructive=payload["is_destructive"],
        value=value,
        thought=(thought or "")[:MAX_THOUGHT_CHARS],
    )


def _object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Collect duplicate keys so :func:`validate_action_contract` can refuse them."""
    seen: dict[str, Any] = {}
    duplicates: list[str] = []
    for key, val in pairs:
        if key in seen:
            duplicates.append(key)
        seen[key] = val
    if duplicates:
        seen[DUPLICATE_MARKER] = sorted(set(duplicates))
    return seen


def parse_action_contract(text: str) -> ActionContract | GuardRejection:
    """Parse the model's message content and validate it as an action contract.

    ``text`` is the *content* of ``choices[0].message`` — the string that was
    supposed to be the action contract — which is what §8.4 means by "the raw
    response" for a schema failure.
    """
    if not isinstance(text, str):
        return _reject(
            MALFORMED,
            f"message content must be a string, got {type(text).__name__}",
            "§8.4",
        )
    try:
        payload = json.loads(text, object_pairs_hook=_object_pairs_hook)
    except json.JSONDecodeError as exc:
        # JSONDecodeError messages carry position, never payload text.
        return _reject(MALFORMED, f"response is not valid JSON: {exc}", "§8.4")
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        return _reject(MALFORMED, f"response is not valid JSON: {exc}", "§8.4")
    return validate_action_contract(payload)
