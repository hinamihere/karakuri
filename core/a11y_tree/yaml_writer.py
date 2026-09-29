"""Deterministic, minimal YAML emitter for the compact a11y tree.

Hand-rolled rather than delegating to a YAML library because three properties
are contractual:

1. **Field order** is fixed by contracts.md §3.2 — a library that sorted keys or
   varied insertion order would break the hash.
2. **Quoting** is minimal but always safe, so the tree stays inside the 200–500
   token budget without ever emitting a scalar that parses as ``true``/``null``.
3. **Byte-for-byte reproducibility** — same tree, same output, every run.

Output follows the shape of contracts.md §3.4.
"""

from __future__ import annotations

import re
from typing import Optional

from .model import PrunedNode, Rect

# Scalars YAML 1.1 loaders resolve to bool/null, plus anything that looks numeric.
_AMBIGUOUS_SCALAR = re.compile(
    r"^(?:"
    r"true|false|yes|no|on|off|y|n|"
    r"null|~|"
    r"[-+]?(?:0|[1-9][0-9_]*)\.(?:[0-9_]*)(?:[eE][-+]?[0-9]+)?|"
    r"[-+]?[0-9_]+|"
    r"0x[0-9a-fA-F_]+|"
    r"0o[0-7_]+|"
    r"[-+]?\.(?:inf|INF)|\.nan|\.NaN"
    r")$",
    re.VERBOSE,
)
_LEADING_INDICATOR = re.compile(r"[-?:,\[\]{}#&*!|>'\"%@`\s]")
_NEEDS_ESCAPE = re.compile(r'[\\"\x00-\x1f\x7f]')

_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _quote(text: str) -> str:
    def repl(match: "re.Match[str]") -> str:
        ch = match.group(0)
        if ch in _ESCAPES:
            return _ESCAPES[ch]
        return f"\\u{ord(ch):04x}"

    return '"' + _NEEDS_ESCAPE.sub(repl, text) + '"'


def format_scalar(value: str) -> str:
    """Render a string scalar, quoting only when YAML would misread it plain."""
    if value == "":
        return '""'
    if _AMBIGUOUS_SCALAR.match(value):
        return _quote(value)
    if _LEADING_INDICATOR.match(value):
        return _quote(value)
    if value[-1] in ":#" or ": " in value or " #" in value:
        return _quote(value)
    if value != value.strip() or _NEEDS_ESCAPE.search(value):
        return _quote(value)
    return value


def _format_rect(rect: Rect) -> str:
    return f"{{x: {rect.x}, y: {rect.y}, width: {rect.width}, height: {rect.height}}}"


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _render(node: PrunedNode, indent: int) -> list[str]:
    """Render one node's mapping; callers indent every returned line."""
    pad = " " * indent
    lines = [
        f"{pad}temp_id: {node.temp_id}",
        f"{pad}control_type: {format_scalar(node.control_type)}",
        f"{pad}name: {format_scalar(node.name)}",
    ]
    if node.automation_id:
        lines.append(f"{pad}automation_id: {format_scalar(node.automation_id)}")
    lines.append(f"{pad}is_enabled: {_format_bool(node.is_enabled)}")
    if node.is_selected is not None:
        lines.append(f"{pad}is_selected: {_format_bool(node.is_selected)}")
    if node.value is not None:
        lines.append(f"{pad}value: {format_scalar(node.value)}")
    lines.append(f"{pad}children_count: {node.children_count}")
    lines.append(f"{pad}bounding_rect: {_format_rect(node.bounding_rect)}")
    if node.children:
        lines.append(f"{pad}children:")
        for child in node.children:
            # The child mapping is rendered as if indented at `indent + 4` (where
            # its first key lands after "- "), then the first line is re-prefixed
            # with the sequence marker at `indent + 2`.
            child_lines = _render(child, indent + 4)
            lines.append(f"{pad}  - " + child_lines[0].lstrip(" "))
            lines.extend(child_lines[1:])
    return lines


def emit_yaml(root: PrunedNode) -> str:
    """Serialize the pruned tree as the compact YAML contract document."""
    lines = ["tree:"]
    lines.extend(_render(root, 2))
    return "\n".join(lines) + "\n"


def field_order() -> tuple[str, ...]:
    """The §3.2 field order, exposed so tests can pin it."""
    return (
        "temp_id",
        "control_type",
        "name",
        "automation_id",
        "is_enabled",
        "is_selected",
        "value",
        "children_count",
        "bounding_rect",
        "children",
    )
