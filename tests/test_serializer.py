"""Compact YAML serialization (contracts.md §3.2 field set, §3.4 shape)."""

from __future__ import annotations

import re

import pytest
import yaml

from core.a11y_tree import PruneLimits, RawNode, Rect, emit_yaml, format_scalar, prune_once
from core.a11y_tree.yaml_writer import field_order


def build(raw):
    root, _ = prune_once(raw, PruneLimits())
    return emit_yaml(root)


SAMPLE = RawNode.from_dict(
    {
        "control_type": "Window",
        "name": "弥生会計 2024 - 仕訳入力",
        "bounding_rect": {"x": 0, "y": 0, "width": 1280, "height": 720},
        "children": [
            {
                "control_type": "Edit",
                "name": "借方科目",
                "automation_id": "borrow-side-code",
                "value": "",
                "bounding_rect": {"x": 24, "y": 80, "width": 180, "height": 24},
            },
            {
                "control_type": "CheckBox",
                "name": "消費税",
                "automation_id": "tax",
                "is_selected": True,
                "bounding_rect": {"x": 24, "y": 120, "width": 180, "height": 24},
            },
            {
                "control_type": "Button",
                "name": "保存",
                "automation_id": "btn-save",
                "bounding_rect": {"x": 1100, "y": 640, "width": 100, "height": 32},
            },
        ],
    }
)


def test_output_is_valid_yaml_and_has_tree_root():
    parsed = yaml.safe_load(build(SAMPLE))
    assert isinstance(parsed, dict)
    assert list(parsed) == ["tree"]
    assert parsed["tree"]["temp_id"] == 1


def test_field_order_follows_the_contract():
    parsed = yaml.safe_load(build(SAMPLE))
    order = list(parsed["tree"])
    expected = [k for k in field_order() if k in order]
    assert order == expected
    # contract order: temp_id, control_type, name, automation_id?, is_enabled,
    # is_selected?, value?, children_count, bounding_rect, children?
    assert order.index("temp_id") < order.index("control_type") < order.index("name")
    assert order.index("is_enabled") < order.index("children_count")
    assert order.index("children_count") < order.index("bounding_rect")


def test_absent_automation_id_is_omitted_not_empty_string():
    text = build(SAMPLE)
    root_block = text.split("children:")[0]
    assert "automation_id" not in root_block
    assert 'automation_id: ""' not in text
    parsed = yaml.safe_load(text)
    assert "automation_id" not in parsed["tree"]


def test_value_present_only_for_edit_and_combo():
    parsed = yaml.safe_load(build(SAMPLE))
    children = {c["control_type"]: c for c in parsed["tree"]["children"]}
    assert children["Edit"]["value"] == ""
    assert "value" not in children["Button"]
    assert "value" not in children["CheckBox"]


def test_is_selected_present_only_for_selection_types():
    parsed = yaml.safe_load(build(SAMPLE))
    children = {c["control_type"]: c for c in parsed["tree"]["children"]}
    assert children["CheckBox"]["is_selected"] is True
    assert "is_selected" not in children["Button"]


def test_leaves_omit_children_key_and_report_zero_count():
    parsed = yaml.safe_load(build(SAMPLE))
    for child in parsed["tree"]["children"]:
        assert child["children_count"] == 0
        assert "children" not in child


def test_bounding_rect_is_an_object_with_screen_coordinates():
    parsed = yaml.safe_load(build(SAMPLE))
    assert parsed["tree"]["bounding_rect"] == {"x": 0, "y": 0, "width": 1280, "height": 720}
    rect_line = [line for line in build(SAMPLE).splitlines() if "bounding_rect" in line][0]
    assert rect_line.strip().startswith("bounding_rect: {x: ")


def test_children_count_equals_kept_children():
    parsed = yaml.safe_load(build(SAMPLE))
    assert parsed["tree"]["children_count"] == 3


def test_japanese_text_is_emitted_as_utf8_not_escaped():
    text = build(SAMPLE)
    assert "弥生会計" in text
    assert "\\u" not in text


@pytest.mark.parametrize(
    "value,expected",
    [
        ("保存", "保存"),
        ("true", '"true"'),
        ("no", '"no"'),
        ("null", '"null"'),
        ("~", '"~"'),
        ("123", '"123"'),
        ("1.5", '"1.5"'),
        (".inf", '".inf"'),
        ("", '""'),
        (" leading", '" leading"'),
        ("trailing ", '"trailing "'),
        ("key: value", '"key: value"'),
        ("a # comment", '"a # comment"'),
        ("- item", '"- item"'),
        ("[bracket]", '"[bracket]"'),
        ("multi\nline", '"multi\\nline"'),
    ],
)
def test_ambiguous_or_unsafe_scalars_are_quoted(value, expected):
    assert format_scalar(value) == expected
    # whatever we emit must round-trip
    assert yaml.safe_load(format_scalar(value)) == value


def test_plain_scalars_stay_unquoted_for_token_budget():
    assert format_scalar("btn-save") == "btn-save"
    assert format_scalar("借方科目") == "借方科目"
    assert format_scalar("2026/08/01") == "2026/08/01"


def test_quoted_values_survive_yaml_parsing_intact():
    tricky = RawNode(
        control_type="Edit",
        name="値: テスト #1",
        bounding_rect=Rect(1, 2, 3, 4),
        value="yes",
    )
    raw = RawNode(control_type="Window", name="w", children=[tricky])
    parsed = yaml.safe_load(build(raw))
    assert parsed["tree"]["children"][0]["name"] == "値: テスト #1"
    assert parsed["tree"]["children"][0]["value"] == "yes"


def test_nested_children_indent_correctly():
    raw = RawNode.from_dict(
        {
            "control_type": "Window",
            "name": "w",
            "children": [
                {
                    "control_type": "Pane",
                    "name": "p",
                    "children": [{"control_type": "Button", "name": "b"}],
                }
            ],
        }
    )
    text = build(raw)
    parsed = yaml.safe_load(text)
    assert parsed["tree"]["children"][0]["children"][0]["control_type"] == "Button"
    assert re.search(r"\n {8}- temp_id: 3\n", text)
