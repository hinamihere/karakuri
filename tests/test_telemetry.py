"""Telemetry records for pruner events (contracts.md §2.1, §2.2, §3.5, §9.5)."""

from __future__ import annotations

import json
import os

import pytest

from core.a11y_tree import (
    PruneEvent,
    PruneLimits,
    RawNode,
    build_compact_tree,
    build_telemetry_records,
    append_jsonl,
    snapshot_hash,
)
from core.a11y_tree.pruner import BUDGET_EXCEEDED, DEPTH_CUT
from core.a11y_tree.telemetry import VALID_STATUS

REQUIRED_FIELDS = (
    "timestamp",
    "execution_mode",
    "intent",
    "window_title",
    "tree_snapshot_hash",
    "status",
    "error_category",
)


def depth_cut_event(automation_id="act-001") -> PruneEvent:
    return PruneEvent(
        error_category=DEPTH_CUT,
        detail="dropped at depth 9 > 8",
        depth=9,
        automation_id=automation_id,
        control_type="Button",
        name="削除",
    )


def records_for(events, **overrides):
    kwargs = {
        "tree_snapshot_hash": "a" * 64,
        "execution_mode": "mode_b",
        "intent": "売上データをCSVに出力",
        "window_title": "弥生会計 2024 - 仕訳入力",
    }
    kwargs.update(overrides)
    return build_telemetry_records(events, **kwargs)


def test_every_required_field_is_present():
    records = records_for([depth_cut_event()])
    assert len(records) == 1
    record = records[0]
    for field in REQUIRED_FIELDS:
        assert field in record, field
    # §2.1 optional-but-declared fields are present too
    for field in ("llm_output", "resolved_target", "os_error_code", "fallback_attempted"):
        assert field in record


def test_timestamp_is_iso8601_utc_with_milliseconds():
    record = records_for([depth_cut_event()])[0]
    assert record["timestamp"].endswith("Z")
    assert len(record["timestamp"]) == 24  # 2026-09-29T18:44:43.123Z
    assert record["timestamp"][4] == "-" and record["timestamp"] == record["timestamp"].replace(" ", "")


def test_status_and_error_category_pairing_follows_the_contract():
    record = records_for([depth_cut_event()])[0]
    assert record["status"] in VALID_STATUS
    # §2.1: a non-null error_category requires failure/fallback_applied
    assert record["status"] in ("failure", "fallback_applied")
    assert record["error_category"] == DEPTH_CUT


def test_long_intent_and_window_title_are_truncated():
    record = records_for(
        [depth_cut_event()],
        intent="あ" * 600,
        window_title="い" * 300,
    )[0]
    assert len(record["intent"]) == 500
    assert len(record["window_title"]) == 200


def test_budget_exceeded_records_carry_its_own_category():
    events = [PruneEvent(error_category=BUDGET_EXCEEDED, detail="still 600 > 500", depth=1)]
    record = records_for(events)[0]
    assert record["error_category"] == BUDGET_EXCEEDED


def test_no_event_no_record():
    assert records_for([]) == []


def test_execution_mode_is_validated():
    with pytest.raises(ValueError):
        records_for([depth_cut_event()], execution_mode="mode_c")


def test_hash_in_the_record_is_the_one_from_the_tree():
    raw = RawNode(control_type="Window", name="w")
    result = build_compact_tree(raw, limits=PruneLimits())
    assert result.events == (), "a root-only tree has nothing to report"
    record = records_for(
        [depth_cut_event()], tree_snapshot_hash=result.tree_snapshot_hash
    )[0]
    assert record["tree_snapshot_hash"] == result.tree_snapshot_hash
    assert record["tree_snapshot_hash"] == snapshot_hash(result.yaml)
    assert len(record["tree_snapshot_hash"]) == 64


def test_append_jsonl_writes_utf8_lines_and_appends(tmp_path):
    path = tmp_path / "logs" / "telemetry.jsonl"
    first = records_for([depth_cut_event()], intent="保存する")
    second = records_for([PruneEvent(error_category=BUDGET_EXCEEDED, detail="x")])

    assert append_jsonl(str(path), first) == 1
    assert append_jsonl(str(path), second) == 1

    text = path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line]
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["intent"] == "保存する"
    assert parsed[1]["error_category"] == BUDGET_EXCEEDED
    # JSONL must be append-only UTF-8, one object per line
    assert "保存する" in text


def test_append_jsonl_with_no_records_is_a_no_op(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    assert append_jsonl(str(path), []) == 0
    assert not os.path.exists(path)


def test_records_carry_no_secret_looking_fields():
    record = records_for([depth_cut_event()])[0]
    lowered = {key.lower() for key in record}
    assert not any("api_key" in key or "token" in key or "secret" in key or "password" in key for key in lowered)
    assert "api_key" not in json.dumps(record).lower()
