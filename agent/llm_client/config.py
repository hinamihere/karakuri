"""``config.toml`` ``[llm]`` section — contracts.md §5.4 and §5.5.

The section is validated *before* any request is built, so an unusable endpoint
fails at load time (or at the Mode B routing stage) instead of mid-execution.

Two failure phases are distinguished because the contract distinguishes them:

``startup``
    The config itself is rejected. Only ``temperature != 0.0`` is mandated to
    fail this way (§5.4: "rejected at startup with
    ``error_category: "config_non_zero_temperature"``").

``routing``
    The config loads, but Mode B is unavailable: any execution that would reach
    Mode B fails with this category at the routing stage (§5.4 for a missing or
    invalid ``base_url``, §5.5 for a missing ``[llm]`` section).

``error_category`` is the value the caller must log. It is ``None`` for config
*type* errors (a string where an integer belongs): contracts.md §2.2 assigns no
category to those, and inventing one would be a contract change.
"""

from __future__ import annotations

import tomllib
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable, Mapping

TIMEOUT_MIN_MS = 1000
TIMEOUT_MAX_MS = 60000
DEFAULT_TIMEOUT_MS = 5000
DEFAULT_MODEL = "llama3"

#: §5.4 keys. Anything else is an unknown key (§5.5: ignored, warned once).
LLM_KEYS = ("base_url", "api_key", "model", "timeout_ms", "temperature")


class LlmConfigError(ValueError):
    """Invalid ``[llm]`` configuration.

    Attributes:
        error_category: contracts.md §2.2 value to log, or ``None`` when the
            contract defines no category for this failure.
        phase: ``"startup"`` or ``"routing"`` — see the module docstring.
    """

    def __init__(
        self,
        message: str,
        *,
        error_category: str | None = None,
        phase: str = "startup",
    ) -> None:
        super().__init__(message)
        self.error_category = error_category
        self.phase = phase


@dataclass(frozen=True, repr=False)
class LlmConfig:
    """Validated ``[llm]`` values (§5.4).

    ``temperature`` is forced to ``0.0`` — the determinism requirement is not a
    caller preference (§10.5: "Do not relax the temperature = 0 requirement").
    ``timeout_ms`` is clamped to 1000–60000 rather than rejected (§5.4).
    """

    base_url: str
    api_key: str = ""
    model: str = DEFAULT_MODEL
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    temperature: float = 0.0

    def __post_init__(self) -> None:
        # --- temperature (§5.4) -------------------------------------------
        temp = self.temperature
        if isinstance(temp, bool) or not isinstance(temp, (int, float)):
            raise LlmConfigError(
                f"[llm].temperature must be a number, got {type(temp).__name__}"
            )
        if float(temp) != 0.0:
            raise LlmConfigError(
                "[llm].temperature must be 0.0 for determinism (contracts.md "
                f"§5.4), got {float(temp)!r}",
                error_category="config_non_zero_temperature",
                phase="startup",
            )
        object.__setattr__(self, "temperature", 0.0)

        # --- base_url (§5.4) ----------------------------------------------
        url = self.base_url
        if isinstance(url, str):
            url = url.strip().rstrip("/")
        if not isinstance(url, str) or not url:
            raise LlmConfigError(
                "[llm].base_url is required and must be a valid http(s) URL; "
                "without it Mode B is unavailable (contracts.md §5.4)",
                error_category="llm_unreachable",
                phase="routing",
            )
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise LlmConfigError(
                "[llm].base_url must be an absolute http(s) URL with a host "
                f"(contracts.md §5.4), got {url!r}; Mode B is unavailable",
                error_category="llm_unreachable",
                phase="routing",
            )
        object.__setattr__(self, "base_url", url)

        # --- model (§5.4) --------------------------------------------------
        model = self.model
        if not isinstance(model, str) or not model.strip():
            raise LlmConfigError(
                f"[llm].model must be a non-empty string, got {model!r}"
            )
        object.__setattr__(self, "model", model.strip())

        # --- timeout_ms (§5.4: clamp, never reject) ------------------------
        raw = self.timeout_ms
        if isinstance(raw, bool):
            raise LlmConfigError(
                f"[llm].timeout_ms must be an integer, got bool"
            )
        if isinstance(raw, str):
            try:
                raw = int(raw)
            except ValueError:
                raise LlmConfigError(
                    f"[llm].timeout_ms must be an integer, got {raw!r}"
                ) from None
        if isinstance(raw, float):
            raw = int(raw)
        if not isinstance(raw, int):
            raise LlmConfigError(
                f"[llm].timeout_ms must be an integer, got {raw!r}"
            )
        clamped = max(TIMEOUT_MIN_MS, min(TIMEOUT_MAX_MS, int(raw)))
        object.__setattr__(self, "timeout_ms", clamped)

        # --- api_key (§5.4: empty means no auth header) --------------------
        key = self.api_key
        if key is None:
            key = ""
        if not isinstance(key, str):
            raise LlmConfigError(
                f"[llm].api_key must be a string, got {type(key).__name__}"
            )
        object.__setattr__(self, "api_key", key.strip())

    # ------------------------------------------------------------------ url
    @property
    def chat_completions_url(self) -> str:
        """``base_url`` + ``/chat/completions`` (§5.4 example includes ``/v1``).

        ``base_url`` already carries any version prefix the endpoint wants, so
        only the OpenAI path segment is appended — appending ``/v1`` as well
        would produce ``/v1/v1/chat/completions`` against the documented
        default. A ``base_url`` that already ends in the full path wins.
        """
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def __repr__(self) -> str:
        # §10.5: the api_key must never reach a log, a repr, or telemetry.
        key = "***" if self.api_key else "(none)"
        return (
            f"LlmConfig(base_url={self.base_url!r}, api_key={key}, "
            f"model={self.model!r}, timeout_ms={self.timeout_ms}, "
            f"temperature={self.temperature!r})"
        )


def llm_config_from_document(
    document: Mapping[str, Any],
    *,
    on_warning: Callable[[str, str], None] | None = None,
) -> LlmConfig:
    """Build :class:`LlmConfig` from a parsed ``config.toml`` document.

    ``on_warning(error_category, message)`` is called once per unknown key with
    ``"config_unknown_key"`` (§5.5) so the config loader owns the single
    startup warning; unknown keys are ignored, never rejected.
    """
    if "llm" not in document:
        raise LlmConfigError(
            "config.toml has no [llm] section — Mode B is unavailable "
            "(contracts.md §5.5)",
            error_category="llm_unreachable",
            phase="routing",
        )
    section = document["llm"]
    if not isinstance(section, Mapping):
        raise LlmConfigError(
            "[llm] must be a table (contracts.md §5.1)",
            error_category="llm_unreachable",
            phase="routing",
        )

    if on_warning is not None:
        for key in sorted(k for k in section if k not in LLM_KEYS):
            on_warning(
                "config_unknown_key",
                f"[llm].{key} is not a known key and was ignored (contracts.md §5.5)",
            )

    known = {k: section[k] for k in LLM_KEYS if k in section}
    return LlmConfig(**known)


def load_llm_config(
    path: str,
    *,
    on_warning: Callable[[str, str], None] | None = None,
) -> LlmConfig:
    """Read ``config.toml`` from ``path`` and return its ``[llm]`` section.

    Convenience for the LLM client's own tests and for callers that have no
    wider config loader yet; the full config loader (§5.5 unknown-key warnings
    for every section) is KARA-11's. ``FileNotFoundError`` propagates untouched
    — a missing file is the caller's to report.
    """
    with open(path, "rb") as handle:  # tomllib requires binary input
        document = tomllib.load(handle)
    return llm_config_from_document(document, on_warning=on_warning)
