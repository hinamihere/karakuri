"""RawNode / Rect adapter-facing models."""

from __future__ import annotations

import pytest

from core.a11y_tree import RawNode, Rect


def test_from_dict_accepts_uia_camel_case_aliases():
    node = RawNode.from_dict(
        {
            "controlType": "Button",
            "name": "保存",
            "automationId": "btn-save",
            "enabled": False,
            "boundingRectangle": {"left": 10, "top": 20, "right": 110, "bottom": 52},
        }
    )
    assert node.control_type == "Button"
    assert node.automation_id == "btn-save"
    assert node.is_enabled is False
    assert node.bounding_rect == Rect(10, 20, 100, 32)


def test_from_dict_accepts_role_key_for_at_spi():
    node = RawNode.from_dict({"role": "push button", "name": "OK"})
    assert node.control_type == "push button"


def test_from_dict_requires_control_type():
    with pytest.raises(KeyError):
        RawNode.from_dict({"name": "orphan"})


def test_rect_from_various_shapes():
    assert Rect.from_value({"x": 1, "y": 2, "width": 3, "height": 4}) == Rect(1, 2, 3, 4)
    assert Rect.from_value({"x": 1, "y": 2, "right": 11, "bottom": 22}) == Rect(1, 2, 10, 20)
    assert Rect.from_value((5, 6, 7, 8)) == Rect(5, 6, 7, 8)
    assert Rect.from_value(None) == Rect()
    assert Rect.from_value(Rect(9, 9, 9, 9)) == Rect(9, 9, 9, 9)

    class RECT:  # pywinauto / Win32 style
        left, top, right, bottom = 100, 200, 300, 240

    assert Rect.from_value(RECT()) == Rect(100, 200, 200, 40)


def test_rect_rejects_junk():
    with pytest.raises(TypeError):
        Rect.from_value("0,0,100,100")


def test_to_dict_omits_absent_optional_fields():
    node = RawNode(control_type="Button", name="OK")
    data = node.to_dict()
    assert "is_selected" not in data
    assert "value" not in data
    assert "children" not in data
    assert data["bounding_rect"] == {"x": 0, "y": 0, "width": 0, "height": 0}


def test_round_trip_preserves_the_tree():
    source = {
        "control_type": "Window",
        "name": "帳票出力",
        "automation_id": "main",
        "is_enabled": True,
        "bounding_rect": {"x": 0, "y": 0, "width": 800, "height": 600},
        "children": [
            {
                "control_type": "Edit",
                "name": "対象期間",
                "automation_id": "period",
                "is_enabled": True,
                "value": "2026/08/01",
                "bounding_rect": {"x": 8, "y": 8, "width": 120, "height": 24},
                "is_selected": False,
            }
        ],
    }
    assert RawNode.from_dict(source).to_dict() == source


def test_text_fields_are_coerced_from_bytes():
    node = RawNode.from_dict(
        {"control_type": b"Button", "name": "保存".encode("utf-8"), "automation_id": None}
    )
    assert node.control_type == "Button"
    assert node.name == "保存"
    assert node.automation_id == ""
