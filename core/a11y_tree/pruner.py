"""The a11y tree pruner (contracts.md §3.3 / §3.5).

Input is an unpruned ``RawNode`` tree from an OS adapter; output is a pruned
tree whose nodes carry the §3.2 fields and temp ids in depth-first serialization
order.

Rules implemented here:

- Drop separators, splitters, scrollbars, menu bars and menu items (§3.3).
- Keep actionable controls even as leaves (§3.3).
- Keep containers only when at least one child survives — this is also what
  makes "empty panels" and "groupings with children_count == 0" disappear (§3.3).
- Max depth 8 from the window root; a cut node with an ``automation_id`` emits a
  ``pruner_depth_cut`` telemetry event, everything else drops silently (§3.5).
- Max 40 kept children per level, first 40 in serialization order (§3.5).
- If the serialized tree still exceeds the token budget, re-prune with a shallower
  depth limit until it fits; if it cannot fit, emit ``pruner_budget_exceeded``
  once (§9.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from . import taxonomy
from .model import PrunedNode, RawNode
from .utf16 import (
    MAX_NAME_UTF16_UNITS,
    MAX_VALUE_UTF16_UNITS,
    coerce_text,
    utf16_truncate,
)

DEPTH_CUT = "pruner_depth_cut"
BUDGET_EXCEEDED = "pruner_budget_exceeded"


@dataclass(frozen=True)
class PruneLimits:
    """§3.5 depth/breadth limits plus the §9.1 token ceiling."""

    max_depth: int = 8
    max_breadth: int = 40
    max_tokens: int = 500
    # Floor for the budget-tightening loop: never prune shallower than this
    # before giving up and logging pruner_budget_exceeded.
    min_budget_depth: int = 1


@dataclass(frozen=True)
class PruneEvent:
    """A pruner-side telemetry trigger (§3.5, §9.5)."""

    error_category: str
    detail: str
    depth: int = 0
    automation_id: Optional[str] = None
    control_type: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "error_category": self.error_category,
            "detail": self.detail,
            "depth": self.depth,
        }
        if self.automation_id:
            out["automation_id"] = self.automation_id
        if self.control_type:
            out["control_type"] = self.control_type
        if self.name:
            out["name"] = self.name
        return out


def _visit(
    raw: RawNode,
    depth: int,
    limits: PruneLimits,
    events: list[PruneEvent],
    *,
    is_root: bool = False,
) -> Optional[PrunedNode]:
    control_type = coerce_text(raw.control_type, field="control_type")
    automation_id = coerce_text(raw.automation_id, field="automation_id").strip()

    # Depth gate first (§3.5): an automation_id-bearing node cut by depth is the
    # one case the contract wants surfaced in telemetry.
    if not is_root and depth > limits.max_depth:
        if automation_id:
            events.append(
                PruneEvent(
                    error_category=DEPTH_CUT,
                    detail=f"dropped at depth {depth} > {limits.max_depth}",
                    depth=depth,
                    automation_id=automation_id,
                    control_type=control_type,
                    name=utf16_truncate(coerce_text(raw.name, field="name"), MAX_NAME_UTF16_UNITS),
                )
            )
        return None

    # Type gate (§3.3): separators, scrollbars, menus take their subtree with them.
    if not is_root and taxonomy.is_dropped(control_type):
        return None

    kept_children: list[PrunedNode] = []
    for child in raw.children:
        pruned = _visit(child, depth + 1, limits, events)
        if pruned is not None:
            kept_children.append(pruned)

    # Breadth gate (§3.5): first 40 kept children in serialization order, silent.
    if len(kept_children) > limits.max_breadth:
        del kept_children[limits.max_breadth :]

    # Keep policy (§3.3): actionable controls always; containers only when they
    # still hold something; everything else is layout noise. The root is the
    # anchor of the document and is never dropped (§3.4).
    if not is_root and not taxonomy.is_actionable(control_type) and not kept_children:
        return None

    name = utf16_truncate(coerce_text(raw.name, field="name"), MAX_NAME_UTF16_UNITS)
    value = None if raw.value is None else utf16_truncate(
        coerce_text(raw.value, field="value"), MAX_VALUE_UTF16_UNITS
    )
    is_selected = raw.is_selected if taxonomy.carries_selection(control_type) else None
    if value is not None and not taxonomy.carries_value(control_type):
        value = None

    return PrunedNode(
        temp_id=0,
        control_type=control_type,
        name=name,
        is_enabled=bool(raw.is_enabled),
        bounding_rect=raw.bounding_rect,
        children_count=len(kept_children),
        automation_id=automation_id or None,
        is_selected=is_selected,
        value=value,
        children=kept_children,
    )


def assign_temp_ids(root: PrunedNode) -> PrunedNode:
    """Number nodes 1..N in depth-first pre-order (§3.2 "serialization order")."""
    counter = 0
    stack: list[PrunedNode] = [root]
    while stack:
        node = stack.pop()
        counter += 1
        node.temp_id = counter
        # reverse so children are visited left-to-right
        stack.extend(reversed(node.children))
    return root


def count_nodes(root: PrunedNode) -> int:
    return 1 + sum(count_nodes(child) for child in root.children)


def prune_once(
    raw: RawNode,
    limits: PruneLimits,
    *,
    max_depth: Optional[int] = None,
) -> tuple[PrunedNode, list[PruneEvent]]:
    """Single pruning pass at a fixed depth limit (no budget tightening)."""
    events: list[PruneEvent] = []
    depth_limit = limits.max_depth if max_depth is None else max_depth
    effective = PruneLimits(
        max_depth=depth_limit,
        max_breadth=limits.max_breadth,
        max_tokens=limits.max_tokens,
        min_budget_depth=limits.min_budget_depth,
    )
    root = _visit(raw, 1, effective, events, is_root=True)
    assert root is not None  # the root is never dropped
    assign_temp_ids(root)
    return root, events
