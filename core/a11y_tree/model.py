"""Node models: what the OS adapter feeds the pruner, and what the pruner emits.

``RawNode`` is deliberately platform-neutral so the Windows UIA adapter
(KARA-5), an AT-SPI2 adapter, and the test fixtures all converge on one shape.
``from_dict`` accepts the usual UIA naming variants so an adapter can hand over
JSON without renaming anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from .utf16 import coerce_text


@dataclass(frozen=True)
class Rect:
    """Screen-coordinate rectangle, matching contracts.md §3.2 ``bounding_rect``."""

    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_value(cls, value: Any) -> "Rect":
        """Accept a ``Rect``, a ``{x,y,width,height}`` mapping, a 4-sequence, or a
        pywinauto/Win32 ``RECT``-like object with ``left/top/right/bottom``."""
        if isinstance(value, Rect):
            return value
        if value is None:
            return cls()
        if isinstance(value, Mapping):
            left = value.get("x", value.get("left", 0))
            top = value.get("y", value.get("top", 0))
            if "width" in value or "height" in value:
                return cls(int(left), int(top), int(value.get("width", 0)), int(value.get("height", 0)))
            return cls(int(left), int(top), int(value.get("right", 0)) - int(left), int(value.get("bottom", 0)) - int(top))
        if hasattr(value, "left") and hasattr(value, "top"):
            return cls(int(value.left), int(value.top), int(value.right) - int(value.left), int(value.bottom) - int(value.top))
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            items = list(value)
            if len(items) == 4:
                return cls(int(items[0]), int(items[1]), int(items[2]), int(items[3]))
        raise TypeError(f"cannot interpret bounding_rect from {type(value).__name__}")


@dataclass
class RawNode:
    """One node of the unpruned accessibility tree."""

    control_type: str
    name: str = ""
    automation_id: str = ""
    is_enabled: bool = True
    bounding_rect: Rect = field(default_factory=Rect)
    is_selected: Optional[bool] = None
    value: Optional[str] = None
    children: list["RawNode"] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawNode":
        """Build from a mapping. Tolerates UIA-style camelCase aliases.

        Recognized keys:
        ``control_type``/``controlType``/``role``, ``name``,
        ``automation_id``/``automationId``, ``is_enabled``/``enabled``,
        ``bounding_rect``/``boundingRectangle``/``rect``,
        ``is_selected``/``selected``, ``value``, ``children``.
        """
        if not isinstance(data, Mapping):
            raise TypeError(f"RawNode.from_dict expects a mapping, got {type(data).__name__}")
        control_type = data.get("control_type", data.get("controlType", data.get("role")))
        if control_type is None:
            raise KeyError("raw node is missing control_type")
        enabled = data.get("is_enabled", data.get("enabled", True))
        selected = data.get("is_selected", data.get("selected"))
        rect = data.get("bounding_rect", data.get("boundingRectangle", data.get("rect")))
        children = data.get("children") or []
        return cls(
            control_type=coerce_text(control_type, field="control_type"),
            name=coerce_text(data.get("name"), field="name"),
            automation_id=coerce_text(data.get("automation_id", data.get("automationId")), field="automation_id"),
            is_enabled=bool(enabled),
            bounding_rect=Rect.from_value(rect),
            is_selected=None if selected is None else bool(selected),
            value=None if data.get("value") is None else coerce_text(data.get("value"), field="value"),
            children=[cls.from_dict(child) for child in children],
        )

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "control_type": self.control_type,
            "name": self.name,
            "automation_id": self.automation_id,
            "is_enabled": self.is_enabled,
            "bounding_rect": self.bounding_rect.to_dict(),
        }
        if self.is_selected is not None:
            out["is_selected"] = self.is_selected
        if self.value is not None:
            out["value"] = self.value
        if self.children:
            out["children"] = [c.to_dict() for c in self.children]
        return out


@dataclass
class PrunedNode:
    """A node that survived pruning, ready for serialization (contracts.md §3.2)."""

    temp_id: int
    control_type: str
    name: str
    is_enabled: bool
    bounding_rect: Rect
    children_count: int
    automation_id: Optional[str] = None
    is_selected: Optional[bool] = None
    value: Optional[str] = None
    children: list["PrunedNode"] = field(default_factory=list)
