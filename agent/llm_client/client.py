"""OpenAI-compatible chat-completions client with the §4 schema guard (KARA-10).

One step of Mode B is ``plan_action``: build a request against any configured
``base_url``, take the model's message content, run it through the schema
guard, and hand back either a typed :class:`ActionContract` or an
:class:`LlmFailure`. **The client never executes an action** — a rejected
payload travels back to Mode B untouched (contracts.md §8.4).

Guarantees:

* ``temperature`` is always ``0.0`` (validated in :class:`LlmConfig`).
* ``timeout_ms`` comes from ``config.toml`` and bounds the request (§5.4).
* ``api_key`` is sent only as ``Authorization: Bearer`` and is redacted from
  every failure detail, telemetry event and repr (§10.5).
* Every failure that leaves ``plan_action``/``chat`` produces **exactly one**
  telemetry event when a sink is configured — ``llm_timeout`` and
  ``llm_unreachable`` with ``llm_output: null`` (§8.5), the schema categories
  with the raw, redacted, 1000-char response (§8.4). Successes emit nothing:
  the dispatcher owns that event, because only it knows ``resolved_target``.

Prompt construction (system/user messages carrying the compact YAML tree) belongs
to the Mode B dispatcher, not here — the client takes ``messages`` verbatim so
it stays usable by any caller.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Final, Mapping, Sequence

from .config import LlmConfig
from .redaction import MAX_REDACTED_CHARS, redact, truncate
from .schema_guard import (
    ActionContract,
    GuardRejection,
    parse_action_contract,
)
from .transport import (
    MAX_RESPONSE_BYTES,
    HttpRequest,
    LlmTransportError,
    urllib_transport,
)

__all__ = [
    "ActionContract",
    "ChatCompletion",
    "LlmClient",
    "LlmFailure",
    "TelemetryContext",
    "build_failure_event",
]

MALFORMED: Final[str] = "llm_malformed_json"
UNREACHABLE: Final[str] = "llm_unreachable"
TIMEOUT: Final[str] = "llm_timeout"

INTENT_MAX_CHARS: Final[int] = 500
WINDOW_TITLE_MAX_CHARS: Final[int] = 200


@dataclass(frozen=True)
class ChatCompletion:
    """A 2xx response whose ``choices[0].message.content`` carried text."""

    content: str
    model: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class LlmFailure:
    """A rejected step. ``llm_output`` follows §8.4/§8.5: raw text or null."""

    error_category: str
    detail: str
    llm_output: str | None
    status: str = "failure"


@dataclass(frozen=True)
class TelemetryContext:
    """§2.1 fields only the caller knows. Required to emit an event."""

    intent: str
    window_title: str
    tree_snapshot_hash: str

    def __post_init__(self) -> None:
        digest = self.tree_snapshot_hash
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(ch not in "0123456789abcdefABCDEF" for ch in digest)
        ):
            raise ValueError(
                "tree_snapshot_hash must be a 64-char SHA-256 hex digest "
                "(contracts.md §2.1)"
            )
        if set(digest) == {"0"}:
            raise ValueError(
                "tree_snapshot_hash of all zeros is forbidden (contracts.md §2.1)"
            )


def build_failure_event(
    failure: LlmFailure, context: TelemetryContext, *, now: datetime | None = None
) -> dict[str, Any]:
    """One complete §2.1 telemetry event for a failed Mode B step.

    ``os_error_code`` stays null: a network or schema failure never originates
    in the OS adapter (§2.1). ``resolved_target`` is null because nothing was
    resolved (§8.4 — the step never executed).
    """
    stamp = now or datetime.now(timezone.utc)
    timestamp = stamp.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    return {
        "timestamp": timestamp.replace("+00:00", "Z"),
        "execution_mode": "mode_b",
        "intent": truncate(context.intent, INTENT_MAX_CHARS),
        "window_title": truncate(context.window_title, WINDOW_TITLE_MAX_CHARS),
        "tree_snapshot_hash": context.tree_snapshot_hash,
        "llm_output": failure.llm_output,
        "resolved_target": None,
        "status": "failure",
        "error_category": failure.error_category,
        "os_error_code": None,
        "fallback_attempted": False,
    }


class LlmClient:
    """POSTs to any OpenAI-compatible endpoint and guards what comes back."""

    def __init__(
        self,
        config: LlmConfig,
        *,
        transport: Callable[[HttpRequest], Any] | None = None,
        on_event: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or urllib_transport
        self._on_event = on_event

    @property
    def config(self) -> LlmConfig:
        return self._config

    # ------------------------------------------------------------- public api
    def plan_action(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        telemetry: TelemetryContext | None = None,
        timeout_ms: int | None = None,
    ) -> ActionContract | LlmFailure:
        """One Mode B step: request → envelope → schema guard → contract.

        The only success value is a validated :class:`ActionContract`. Anything
        else is an :class:`LlmFailure` carrying the §2.2 ``error_category`` for
        Mode B to log and abort on — nothing is dispatched from here.
        """
        completion = self._request(messages, timeout_ms=timeout_ms)
        if isinstance(completion, LlmFailure):
            self._emit(completion, telemetry)
            return completion

        guarded = parse_action_contract(completion.content)
        if isinstance(guarded, GuardRejection):
            failure = self._failure(
                guarded.error_category,
                guarded.detail,
                # §8.4: the raw response is the text that failed validation.
                llm_output=completion.content,
            )
            self._emit(failure, telemetry)
            return failure
        return guarded

    def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        telemetry: TelemetryContext | None = None,
        timeout_ms: int | None = None,
    ) -> ChatCompletion | LlmFailure:
        """Raw chat completion without the action-contract guard.

        Telemetry behaves exactly as in :meth:`plan_action`; callers that need
        a validated action use ``plan_action``.
        """
        result = self._request(messages, timeout_ms=timeout_ms)
        if isinstance(result, LlmFailure):
            self._emit(result, telemetry)
        return result

    # ---------------------------------------------------------------- internals
    def _request(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        timeout_ms: int | None = None,
    ) -> ChatCompletion | LlmFailure:
        cfg = self._config
        effective_ms = cfg.timeout_ms if timeout_ms is None else timeout_ms
        body = json.dumps(
            {
                "model": cfg.model,
                "messages": list(messages),
                "temperature": cfg.temperature,
                "stream": False,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "karakuri-llm-client/0.1",
        }
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"

        request = HttpRequest(
            url=cfg.chat_completions_url,
            headers=headers,
            body=body,
            timeout_s=effective_ms / 1000.0,
        )

        try:
            response = self._transport(request)
        except LlmTransportError as exc:
            # §8.5: llm_output is null for timeout/unreachable.
            return self._failure(exc.error_category, exc.detail, llm_output=None)

        raw = response.body
        if not (200 <= response.status < 300):
            snippet = ""
            try:
                snippet = raw.decode("utf-8", errors="replace").strip()
            except Exception:  # pragma: no cover - decode never raises here
                snippet = ""
            detail = f"endpoint returned HTTP {response.status}"
            if snippet:
                detail += f": {snippet[:200]}"
            return self._failure(UNREACHABLE, detail, llm_output=None)

        if len(raw) > MAX_RESPONSE_BYTES:
            return self._failure(
                MALFORMED,
                f"response body exceeds {MAX_RESPONSE_BYTES} bytes — not an "
                "action contract",
                llm_output=None,
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return self._failure(
                MALFORMED, "response body is not valid UTF-8", llm_output=None
            )

        try:
            envelope = json.loads(text)
        except json.JSONDecodeError as exc:
            return self._failure(
                MALFORMED,
                f"response is not valid JSON: {exc}",
                llm_output=text,
            )

        extracted = _extract_content(envelope)
        if isinstance(extracted, LlmFailure):
            return self._failure(extracted.error_category, extracted.detail, llm_output=text)
        return ChatCompletion(
            content=extracted,
            model=_opt_str(envelope.get("model")) if isinstance(envelope, dict) else None,
            finish_reason=_finish_reason(envelope),
        )

    def _failure(
        self, error_category: str, detail: str, *, llm_output: str | None
    ) -> LlmFailure:
        # Redact first, truncate second (§8.4, §10.5).
        safe_detail = redact(detail, self._config.api_key)
        safe_output = (
            None
            if llm_output is None
            else redact(llm_output, self._config.api_key, limit=MAX_REDACTED_CHARS)
        )
        return LlmFailure(
            error_category=error_category, detail=safe_detail, llm_output=safe_output
        )

    def _emit(self, failure: LlmFailure, telemetry: TelemetryContext | None) -> None:
        if self._on_event is None:
            return
        if telemetry is None:
            raise ValueError(
                "telemetry context is required when an event sink is configured: "
                "contracts.md §2.1 makes execution_mode/intent/window_title/"
                "tree_snapshot_hash mandatory on every event"
            )
        self._on_event(build_failure_event(failure, telemetry))


# ------------------------------------------------------------------- helpers
def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _finish_reason(envelope: Any) -> str | None:
    if not isinstance(envelope, dict):
        return None
    choices = envelope.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return _opt_str(choices[0].get("finish_reason"))
    return None


def _extract_content(envelope: Any) -> str | LlmFailure:
    """Pull ``choices[0].message.content`` out of a chat-completions envelope.

    Every shape that does not carry usable text is §2.2's
    ``llm_malformed_json``: a 2xx whose body is not the action contract.
    """
    if not isinstance(envelope, dict):
        return LlmFailure(
            error_category=MALFORMED,
            detail=f"response envelope is not a JSON object "
            f"(got {type(envelope).__name__})",
            llm_output="",
        )
    if envelope.get("error"):
        return LlmFailure(
            error_category=MALFORMED,
            detail=f"endpoint returned an error payload: {envelope['error']!r}",
            llm_output="",
        )
    choices = envelope.get("choices")
    if not isinstance(choices, list) or not choices:
        return LlmFailure(
            error_category=MALFORMED,
            detail="response envelope has no choices — no message content to validate",
            llm_output="",
        )
    first = choices[0]
    if not isinstance(first, dict) or not isinstance(first.get("message"), dict):
        return LlmFailure(
            error_category=MALFORMED,
            detail="choices[0] has no message object",
            llm_output="",
        )
    content = first["message"].get("content")
    if isinstance(content, list):
        # Newer OpenAI-compatible servers return content parts instead of a
        # string; flatten the text parts, then guard the result as usual.
        parts = [
            part.get("text")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        content = "".join(parts)
    if not isinstance(content, str) or not content.strip():
        return LlmFailure(
            error_category=MALFORMED,
            detail="message content is empty — no action contract to validate",
            llm_output="",
        )
    return content
