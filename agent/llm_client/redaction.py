"""Secret redaction and bounded truncation for anything that leaves the client.

contracts.md §8.4 requires the raw LLM response to be logged "with ``api_key``
and any Bearer token redacted", and §10.5 forbids the key reaching telemetry or
stdout. Redaction runs *before* truncation, so a secret that sits past the cut
point cannot survive by being half-visible.
"""

from __future__ import annotations

import re
from typing import Final

#: §8.4: raw response logged truncated to 1000 chars.
MAX_REDACTED_CHARS: Final[int] = 1000

#: ``Authorization: Bearer <token>`` in any form, in any text.
_BEARER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"
)

#: Secret-bearing query parameters (a key smuggled into a base_url).
_PARAM_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|authorization)=([^&\s\"']+)"
)

_MASK: Final[str] = "***"


def truncate(text: str, limit: int) -> str:
    """Cut to ``limit`` characters, marking the cut with a single ellipsis."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def redact(text: str, *secrets: str | None, limit: int | None = MAX_REDACTED_CHARS) -> str:
    """Replace every ``secrets`` value and any bearer/credential pattern.

    ``limit`` (default §8.4's 1000 chars) is applied last so nothing can leak by
    straddling the boundary. Pass ``limit=None`` to keep the full length.
    """
    if not isinstance(text, str):
        text = str(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, _MASK)
    text = _BEARER_RE.sub(f"Bearer {_MASK}", text)
    text = _PARAM_RE.sub(lambda m: f"{m.group(1)}={_MASK}", text)
    if limit is not None:
        text = truncate(text, limit)
    return text
