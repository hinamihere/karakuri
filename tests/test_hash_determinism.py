"""tree_snapshot_hash determinism (contracts.md §2.1, §3.1, §6.2)."""

from __future__ import annotations

import hashlib
import json
import re

from core.a11y_tree import PruneLimits, RawNode, Rect, build_compact_tree, snapshot_hash


def make_raw() -> RawNode:
    return RawNode.from_dict(
        {
            "control_type": "Window",
            "name": "弥生会計 2024 - 仕訳入力",
            "bounding_rect": {"x": 0, "y": 0, "width": 1280, "height": 720},
            "children": [
                {"control_type": "Separator", "name": "sep"},
                {"control_type": "Edit", "name": "借方科目", "automation_id": "borrow",
                 "value": "", "bounding_rect": {"x": 1, "y": 2, "width": 3, "height": 4}},
                {"control_type": "Button", "name": "保存", "automation_id": "save",
                 "bounding_rect": {"x": 5, "y": 6, "width": 7, "height": 8}},
                {"control_type": "Pane", "name": "empty"},
            ],
        }
    )


def test_two_runs_of_the_same_tree_produce_the_same_hash():
    first = build_compact_tree(make_raw())
    second = build_compact_tree(make_raw())
    assert first.yaml == second.yaml
    assert first.tree_snapshot_hash == second.tree_snapshot_hash
    assert first.node_count == second.node_count == 3
    assert first.token_count == second.token_count


def test_hash_is_sha256_hex_over_the_serialized_yaml():
    result = build_compact_tree(make_raw())
    expected = hashlib.sha256(result.yaml.encode("utf-8")).hexdigest()
    assert result.tree_snapshot_hash == expected
    assert snapshot_hash(result.yaml) == expected


def test_hash_is_64_hex_chars_and_not_all_zeroes():
    result = build_compact_tree(make_raw())
    assert len(result.tree_snapshot_hash) == 64
    assert re_fullmatch_hex(result.tree_snapshot_hash)
    assert set(result.tree_snapshot_hash) != {"0"}


def re_fullmatch_hex(value: str) -> bool:
    return all(c in "0123456789abcdef" for c in value)


def test_hash_does_not_depend_on_wall_clock_or_object_identity():
    a = build_compact_tree(make_raw())
    b = build_compact_tree(make_raw())
    # no timestamp, date, or other time-derived text may leak into the payload
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:", a.yaml)
    assert a.yaml == b.yaml
    assert a.tree_snapshot_hash == b.tree_snapshot_hash


def test_different_tree_produces_different_hash():
    base = build_compact_tree(make_raw())
    changed = make_raw()
    changed.children[1].name = "貸方科目"
    other = build_compact_tree(changed)
    assert other.tree_snapshot_hash != base.tree_snapshot_hash


def test_hash_is_stable_across_repeated_calls_in_one_process():
    results = [build_compact_tree(make_raw()) for _ in range(5)]
    assert len({r.tree_snapshot_hash for r in results}) == 1
    assert len({r.yaml for r in results}) == 1


def test_pruning_input_is_not_mutated_between_runs():
    raw = make_raw()
    before = json.dumps(raw.to_dict(), ensure_ascii=False, sort_keys=True)
    build_compact_tree(raw)
    after = json.dumps(raw.to_dict(), ensure_ascii=False, sort_keys=True)
    assert before == after


def test_hash_changes_when_limits_change_the_output():
    wide = RawNode(
        control_type="Window",
        name="w",
        children=[RawNode(control_type="Button", name=f"b{i}", automation_id=f"i{i}") for i in range(30)],
    )
    default = build_compact_tree(wide, limits=PruneLimits(max_tokens=10_000))
    tight = build_compact_tree(wide, limits=PruneLimits(max_tokens=10_000, max_breadth=5))
    assert default.node_count == 31
    assert tight.node_count == 6
    assert default.tree_snapshot_hash != tight.tree_snapshot_hash
