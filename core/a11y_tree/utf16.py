"""Text helpers for the compact a11y tree.

UI Automation hands us strings as UTF-16 (``BSTR`` / UTF-16 code units), and the
contract sizes its limits in the same unit:

- ``name`` is truncated to 120 chars (contracts.md §3.2)
- ``value`` is truncated to 200 chars (contracts.md §3.2 / §9.1)

Truncation therefore happens on the UTF-16 code-unit boundary and is guaranteed
never to split a surrogate pair, so whatever we serialize is always valid UTF-8.
"""

from __future__ import annotations

import re
from typing import Any

MAX_NAME_UTF16_UNITS = 120
MAX_VALUE_UTF16_UNITS = 200

# A high surrogate not followed by a low one, or a low surrogate not preceded by
# a high one. UIA can return unpaired surrogates from broken legacy controls; a
# lone surrogate makes ``str.encode("utf-8")`` raise, which would break both the
# YAML payload and the tree_snapshot_hash.
_LONE_SURROGATE = re.compile("[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]")

REPLACEMENT = "�"


def utf16_len(text: str) -> int:
    """Length of ``text`` in UTF-16 code units (what UIA measures)."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def repair_lone_surrogates(text: str) -> str:
    """Replace unpaired UTF-16 surrogates with U+FFFD so UTF-8 encoding works."""
    if not _LONE_SURROGATE.search(text):
        return text
    return _LONE_SURROGATE.sub(REPLACEMENT, text)


def utf16_truncate(text: str, max_units: int) -> str:
    """Truncate to ``max_units`` UTF-16 code units, never splitting a surrogate pair.

    A cut that lands between a high/low surrogate pair drops the dangling high
    surrogate instead of emitting half of an astral character.
    """
    if max_units <= 0:
        return ""
    encoded = text.encode("utf-16-le", "surrogatepass")
    if len(encoded) <= max_units * 2:
        return text
    chunk = encoded[: max_units * 2]
    last_unit = int.from_bytes(chunk[-2:], "little")
    if 0xD800 <= last_unit <= 0xDBFF:  # dangling high surrogate
        chunk = chunk[:-2]
    return chunk.decode("utf-16-le", "replace")


def coerce_text(value: Any, *, field: str) -> str:
    """Normalize an adapter-supplied string field to a clean Python ``str``.

    Accepts ``str``, ``bytes`` (UTF-8, or UTF-16 with a BOM — what a native
    adapter hands over), and ``None``. Anything else is a programming error in
    the adapter and raises instead of being silently stringified.

    CP932/Shift-JIS is deliberately *not* accepted here: conversion happens only
    at CSV file boundaries (AGENTS.md, "Encoding").
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return repair_lone_surrogates(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            text = raw.decode("utf-16", "strict")
        else:
            text = raw.decode("utf-8", "strict")
        return repair_lone_surrogates(text)
    raise TypeError(
        f"{field}: expected str | bytes | None, got {type(value).__name__}"
    )
