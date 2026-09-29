"""Append-only JSONL telemetry for the routing stage (contracts.md §2).

Only the fields the routing stage can honestly populate are written here.
``llm_output`` and ``resolved_target`` are always ``null``/absent because the
router never calls an LLM and never resolves an a11y node — the dispatcher
that consumes :class:`~agent.router.router.RouteResult` appends its own event
with those fields filled in.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import threading
from typing import Iterable, Mapping, Protocol

# contracts.md §2.2 — closed enum, do not extend without an Architect issue.
ERROR_CATEGORIES = frozenset(
    {
        "selector_miss",
        "pattern_missing",
        "stale_handle",
        "llm_malformed_json",
        "llm_unknown_action",
        "llm_schema_violation",
        "llm_timeout",
        "llm_unreachable",
        "template_missing_var",
        "recipe_invalid",
        "matcher_below_threshold",
        "overlay_rejected",
        "user_aborted",
        "os_generic",
        # added by contracts.md §5.2/§5.3 for the matcher/config stage
        "matcher_index_missing",
        "config_onnx_model_missing",
        "config_unknown_key",
        "config_invalid_hotkey",
        "config_recipe_dir_missing",
        "config_non_zero_temperature",
    }
)

# contracts.md §2.1
_EXECUTION_MODES = frozenset({"mode_a", "mode_b"})
_STATUSES = frozenset({"success", "failure", "fallback_applied", "user_aborted"})
# §2.1: required when status is failure or fallback_applied, null otherwise.
_STATUS_NEEDS_CATEGORY = frozenset({"failure", "fallback_applied"})

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ZERO_HASH = "0" * 64

INTENT_MAX_CHARS = 500
WINDOW_TITLE_MAX_CHARS = 200


class TelemetryEventError(ValueError):
    """A caller tried to build an event the frozen schema does not allow."""


class ExecutionStatus:
    """String constants for the ``status`` field (contracts.md §2.1)."""

    SUCCESS = "success"
    FAILURE = "failure"
    FALLBACK_APPLIED = "fallback_applied"
    USER_ABORTED = "user_aborted"


def _truncate(value: str, limit: int) -> str:
    value = "" if value is None else str(value)
    return value if len(value) <= limit else value[:limit]


def utc_timestamp() -> str:
    """ISO 8601 UTC with millisecond precision, e.g. ``2026-09-29T18:44:43.123Z``."""
    now = _dt.datetime.now(_dt.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def validate_tree_snapshot_hash(tree_snapshot_hash: str) -> str:
    """§2.1: 64 lowercase hex chars, all-zeros forbidden."""
    if not isinstance(tree_snapshot_hash, str) or not _HASH_RE.match(tree_snapshot_hash):
        raise TelemetryEventError(
            "tree_snapshot_hash must be 64 lowercase hex characters "
            f"(got {tree_snapshot_hash!r})"
        )
    if tree_snapshot_hash == _ZERO_HASH:
        raise TelemetryEventError(
            "tree_snapshot_hash must not be all zeros — every real execution "
            "produces a real hash (contracts.md §2.1)"
        )
    return tree_snapshot_hash


def build_event(
    *,
    execution_mode: str,
    intent: str,
    window_title: str,
    tree_snapshot_hash: str,
    status: str,
    error_category: str | None = None,
    os_error_code: int | None = None,
    fallback_attempted: bool = False,
    llm_output: object | None = None,
    resolved_target: object | None = None,
    timestamp: str | None = None,
) -> dict:
    """Build one telemetry event validating every §2.1 rule.

    ``timestamp`` is injectable so tests stay deterministic; production code
    leaves it ``None`` and gets the wall clock (§2.1 requires it, and telemetry
    timestamps are data, not control flow).
    """
    if execution_mode not in _EXECUTION_MODES:
        raise TelemetryEventError(
            f"execution_mode must be one of {sorted(_EXECUTION_MODES)} "
            f"(got {execution_mode!r})"
        )
    if status not in _STATUSES:
        raise TelemetryEventError(
            f"status must be one of {sorted(_STATUSES)} (got {status!r})"
        )
    if status in _STATUS_NEEDS_CATEGORY:
        if error_category is None:
            raise TelemetryEventError(
                f"error_category is required when status is {status!r}"
            )
        if error_category not in ERROR_CATEGORIES:
            raise TelemetryEventError(
                f"error_category {error_category!r} is not in the contracts.md §2.2 enum"
            )
    elif error_category is not None:
        raise TelemetryEventError(
            f"error_category must be null when status is {status!r} "
            f"(got {error_category!r})"
        )

    if timestamp is None:
        timestamp = utc_timestamp()

    event = {
        "timestamp": timestamp,
        "execution_mode": execution_mode,
        "intent": _truncate(intent, INTENT_MAX_CHARS),
        "window_title": _truncate(window_title, WINDOW_TITLE_MAX_CHARS),
        "tree_snapshot_hash": validate_tree_snapshot_hash(tree_snapshot_hash),
        # Mode A never carries an LLM response (§2.3); the routing stage has
        # not made a call yet either, so this stays null until the dispatcher
        # appends the execution event.
        "llm_output": llm_output,
        "resolved_target": resolved_target,
        "status": status,
        "error_category": error_category,
        "os_error_code": os_error_code,
        "fallback_attempted": bool(fallback_attempted),
    }
    return event


class TelemetrySink(Protocol):
    """Anything that can persist a telemetry event."""

    def append(self, event: Mapping[str, object]) -> None:  # pragma: no cover
        ...


class MemoryTelemetrySink:
    """Collects events in memory. Used by tests and by callers that forward
    the routing events to the shared telemetry writer."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def append(self, event: Mapping[str, object]) -> None:
        self.events.append(dict(event))

    def categories(self) -> list[str | None]:
        return [e.get("error_category") for e in self.events]


class JsonlTelemetrySink:
    """Append-only JSONL writer for ``logs/telemetry.jsonl`` (contracts.md §2).

    UTF-8 end to end, one JSON object per line, no network path. Thread-safe
    via a lock so the dispatcher and the router can share one file handle
    policy without interleaving partial lines.
    """

    def __init__(self, path: str | os.PathLike[str] = "logs/telemetry.jsonl") -> None:
        self.path = str(path)
        self._lock = threading.Lock()

    def append(self, event: Mapping[str, object]) -> None:
        line = json.dumps(event, ensure_ascii=False)
        directory = os.path.dirname(os.path.abspath(self.path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")

    def read_all(self) -> list[dict]:  # pragma: no cover - convenience for QA
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


def append_all(sink: TelemetrySink, events: Iterable[Mapping[str, object]]) -> None:
    for event in events:
        sink.append(event)
