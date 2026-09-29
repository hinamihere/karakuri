"""Pruning rules (contracts.md §3.3) and limits (§3.5)."""

from __future__ import annotations

import pytest

from core.a11y_tree import (
    PruneLimits,
    RawNode,
    Rect,
    assign_temp_ids,
    count_nodes,
    prune_once,
)
from core.a11y_tree.pruner import BUDGET_EXCEEDED, DEPTH_CUT


def node(control_type, name="", automation_id="", children=None, **kwargs):
    return RawNode(
        control_type=control_type,
        name=name,
        automation_id=automation_id,
        bounding_rect=kwargs.pop("bounding_rect", Rect(10, 10, 100, 20)),
        children=children or [],
        **kwargs,
    )


def walk(root):
    yield root
    for child in root.children:
        yield from walk(child)


def types(root):
    return [n.control_type for n in walk(root)]


def test_dropped_types_disappear():
    raw = node(
        "Window",
        children=[
            node("Separator"),
            node("Splitter"),
            node("ScrollBar", children=[node("Button", "thumb-ish")]),
            node("MenuBar", children=[node("MenuItem", "ファイル")]),
            node("ContextMenu", children=[node("MenuItem", "コピー")]),
            node("Button", "OK", "btn-ok"),
        ],
    )
    root, events = prune_once(raw, PruneLimits())
    kept = types(root)
    assert "Separator" not in kept
    assert "Splitter" not in kept
    assert "ScrollBar" not in kept
    assert "MenuBar" not in kept
    assert "MenuItem" not in kept
    assert "Button" in kept
    assert events == []


@pytest.mark.parametrize(
    "control_type",
    ["Button", "Edit", "ComboBox", "CheckBox", "RadioButton", "TabItem",
     "ListItem", "Hyperlink", "Spinner", "Slider", "SplitButton", "ToggleButton"],
)
def test_actionable_leaves_are_kept(control_type):
    raw = node("Window", children=[node(control_type, "target", "id-1")])
    root, _ = prune_once(raw, PruneLimits())
    assert control_type in types(root)
    kept = [n for n in walk(root) if n.control_type == control_type][0]
    assert kept.automation_id == "id-1"


def test_empty_pane_and_childless_group_are_dropped():
    raw = node(
        "Window",
        children=[
            node("Pane", "empty"),
            node("Group", "empty group"),
            node("Text", "静的ラベル"),
            node("Image", ""),
        ],
    )
    root, _ = prune_once(raw, PruneLimits())
    assert types(root) == ["Window"]
    assert root.children_count == 0


def test_container_survives_only_with_kept_child():
    raw = node(
        "Window",
        children=[
            node("Pane", "busy", children=[node("Button", "go", "b1")]),
            node("Pane", "idle", children=[node("Text", "label")]),
        ],
    )
    root, _ = prune_once(raw, PruneLimits())
    kept_panes = [n for n in walk(root) if n.control_type == "Pane"]
    assert [p.name for p in kept_panes] == ["busy"]
    assert root.children_count == 1


def test_at_spi_role_aliases_match_uiA_sets():
    raw = node(
        "Frame",  # AT-SPI2-ish container alias
        children=[
            node("push button", "OK", "ok-1"),
            node("entry", "氏名", "name-1"),
            node("check box", "有効", "enable-1"),
            node("scroll bar", "縦"),
        ],
    )
    root, _ = prune_once(raw, PruneLimits())
    kept = types(root)
    assert "push button" in kept
    assert "entry" in kept
    assert "check box" in kept
    assert "scroll bar" not in kept


def test_depth_limit_drops_deeper_nodes():
    # chain: Window(1) -> Pane(2) ... -> Button at depth 9
    deep = node("Button", "buried", "deep-id")
    chain = deep
    for i in range(7):  # depths 2..8 are panes
        chain = node("Pane", f"level-{i + 2}", children=[chain])
    raw = node("Window", children=[chain])

    root, events = prune_once(raw, PruneLimits(max_depth=8))
    assert "Button" not in types(root)
    assert len(events) == 1
    event = events[0]
    assert event.error_category == DEPTH_CUT
    assert event.automation_id == "deep-id"
    assert event.depth == 9


def test_depth_cut_without_automation_id_is_silent():
    deep = node("Button", "no id")
    chain = deep
    for i in range(7):
        chain = node("Pane", f"level-{i + 2}", children=[chain])
    raw = node("Window", children=[chain])

    _, events = prune_once(raw, PruneLimits(max_depth=8))
    assert events == []


def test_node_exactly_at_depth_limit_is_kept():
    inner = node("Button", "at limit", "limit-id")
    chain = inner
    for i in range(6):  # Window(1) + panes(2..7) -> Button at depth 8
        chain = node("Pane", f"level-{i + 2}", children=[chain])
    raw = node("Window", children=[chain])

    root, events = prune_once(raw, PruneLimits(max_depth=8))
    assert "Button" in types(root)
    assert events == []


def test_breadth_limit_keeps_first_40_in_serialization_order():
    children = [node("Button", f"b{i:02d}", f"id-{i:02d}") for i in range(45)]
    raw = node("Window", children=children)

    root, events = prune_once(raw, PruneLimits(max_breadth=40))
    kept = [n for n in walk(root) if n.control_type == "Button"]
    assert len(kept) == 40
    assert [n.automation_id for n in kept] == [f"id-{i:02d}" for i in range(40)]
    assert events == []  # §3.5: breadth drop is silent


def test_temp_ids_are_depth_first_pre_order():
    raw = node(
        "Window",
        children=[
            node("Pane", "a", children=[node("Button", "a1"), node("Button", "a2")]),
            node("Button", "b"),
        ],
    )
    root, _ = prune_once(raw, PruneLimits())
    ids = [n.temp_id for n in walk(root)]
    names = [n.name for n in walk(root)]
    assert ids == [1, 2, 3, 4, 5]
    assert names == ["", "a", "a1", "a2", "b"]
    assert count_nodes(root) == 5


def test_temp_ids_are_dense_and_sequential():
    raw = node("Window", children=[node("Button", str(i)) for i in range(10)])
    root, _ = prune_once(raw, PruneLimits())
    assert sorted(n.temp_id for n in walk(root)) == list(range(1, 12))


def test_root_is_never_dropped():
    raw = RawNode(control_type="Window", name="", children=[])
    root, events = prune_once(raw, PruneLimits())
    assert root.control_type == "Window"
    assert root.temp_id == 1
    assert events == []


def test_assign_temp_ids_is_idempotent():
    raw = node("Window", children=[node("Button", "x"), node("Button", "y")])
    root, _ = prune_once(raw, PruneLimits())
    first = [n.temp_id for n in walk(root)]
    assign_temp_ids(root)
    assert [n.temp_id for n in walk(root)] == first


def test_pruned_output_is_independent_of_input_mutation():
    raw = node("Window", children=[node("Button", "x", "x1")])
    root, _ = prune_once(raw, PruneLimits())
    raw.children[0].name = "changed"
    raw.children.append(node("Button", "late"))
    assert [n.name for n in walk(root)] == ["", "x"]
