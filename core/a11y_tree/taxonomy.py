"""Control-type taxonomy for the pruner (contracts.md §3.3).

The contract names UIA ``ControlType`` values but also accepts AT-SPI2 role
names, so membership is decided on a normalized key: lowercase, with spaces,
underscores and hyphens stripped. The alias tables below are an implementation
detail the contract leaves to the Developer (§10.2); the *output* field keeps the
original, unmodified role string from the adapter.
"""

from __future__ import annotations

import re

_norm_re = re.compile(r"[\s_\-]+")


def normalize_role(role: str) -> str:
    return _norm_re.sub("", (role or "").strip().lower())


# §3.3 "Drop these node types entirely". Subtree is discarded.
DROPPED_TYPES = frozenset(
    normalize_role(r)
    for r in (
        # separators / splitters
        "Separator",
        "Splitter",
        # scrollbars (Thumb is a scrollbar part)
        "ScrollBar",
        "ScrollBarPart",
        "Thumb",
        # menu bars and menu items — handled by the separate shortcut flow
        "MenuBar",
        "Menu",
        "MenuItem",
        "ContextMenu",
        "SystemMenu",
    )
)

# §3.3 "Keep these (actionable controls)". Always kept, even as a leaf.
ACTIONABLE_TYPES = frozenset(
    normalize_role(r)
    for r in (
        # UIA ControlType
        "Button",
        "ToggleButton",
        "SplitButton",
        "Edit",
        "ComboBox",
        "CheckBox",
        "RadioButton",
        "TabItem",
        "ListItem",
        "Hyperlink",
        "Spinner",
        "Slider",
        # AT-SPI2 / toolkit aliases
        "push button",
        "link",
        "entry",
        "page tab",
        "check box",
        "radio button",
        "combo box",
        "list item",
        "spin button",
        "scale",
    )
)

# §3.3 containers: kept only when at least one child survives pruning. Anything
# not named here follows the same container rule — an unknown type with kept
# children is structural context, an unknown type without them is layout noise.
CONTAINER_TYPES = frozenset(
    normalize_role(r)
    for r in (
        "Window",
        "Pane",
        "ToolBar",
        "Group",
        "List",
        "Tree",
        "Table",
        "Tab",
        "TabControl",
        "TabPanel",
        "Document",
        "Custom",
        "Panel",
        "Dialog",
        "Frame",
        "Desktop",
        "AppBar",
        "StatusBar",
        "TitleBar",
        "Selection",
        "Header",
        "Footer",
    )
)

# §3.2: `value` is present only for these.
VALUE_TYPES = frozenset(
    normalize_role(r) for r in ("Edit", "ComboBox", "entry", "combo box", "dropdown list", "DropDown")
)

# §3.2: `is_selected` is present only for these.
SELECTION_TYPES = frozenset(
    normalize_role(r)
    for r in ("CheckBox", "RadioButton", "ListItem", "check box", "radio button", "list item")
)


def is_dropped(role: str) -> bool:
    return normalize_role(role) in DROPPED_TYPES


def is_actionable(role: str) -> bool:
    return normalize_role(role) in ACTIONABLE_TYPES


def carries_value(role: str) -> bool:
    return normalize_role(role) in VALUE_TYPES


def carries_selection(role: str) -> bool:
    return normalize_role(role) in SELECTION_TYPES
