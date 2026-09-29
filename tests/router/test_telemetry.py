"""Telemetry event construction — contracts.md §2."""

from __future__ import annotations

import json

import pytest

from agent.router.telemetry import (
    ERROR_CATEGORIES,
    ExecutionStatus,
    JsonlTelemetrySink,
    MemoryTelemetrySink,
    TelemetryEventError,
    build_event,
    validate_tree_snapshot_hash,
)

HASH = "0123456789abcdef" * 4


def _base(**overrides):
    kwargs = dict(
        execution_mode="mode_b",
        intent="弥生会計で仕訳を新規作成する",
        window_title="弥生会計 2024",
        tree_snapshot_hash=HASH,
        status=ExecutionStatus.FALLBACK_APPLIED,
        error_category="matcher_below_threshold",
        fallback_attempted=True,
        timestamp="2026-09-29T00:00:00.000Z",
    )
    kwargs.update(overrides)
    return kwargs


def test_event_carries_every_required_field():
    event = build_event(**_base())
    assert set(event) == {
        "timestamp",
        "execution_mode",
        "intent",
        "window_title",
        "tree_snapshot_hash",
        "llm_output",
        "resolved_target",
        "status",
        "error_category",
        "os_error_code",
        "fallback_attempted",
    }
    assert event["timestamp"] == "2026-09-29T00:00:00.000Z"
    assert event["fallback_attempted"] is True
    assert event["llm_output"] is None
    assert event["resolved_target"] is None
    assert event["os_error_code"] is None


def test_failure_status_requires_an_error_category():
    with pytest.raises(TelemetryEventError):
        build_event(**_base(status=ExecutionStatus.FAILURE, error_category=None))


def test_success_status_forbids_an_error_category():
    with pytest.raises(TelemetryEventError):
        build_event(**_base(status=ExecutionStatus.SUCCESS, error_category="os_generic"))


def test_error_category_must_be_in_the_frozen_enum():
    with pytest.raises(TelemetryEventError):
        build_event(**_base(error_category="not_a_category"))
    assert "matcher_below_threshold" in ERROR_CATEGORIES
    assert "matcher_index_missing" in ERROR_CATEGORIES


def test_execution_mode_must_be_mode_a_or_mode_b():
    with pytest.raises(TelemetryEventError):
        build_event(**_base(execution_mode="mode_c"))


def test_all_zero_tree_hash_is_rejected():
    with pytest.raises(TelemetryEventError):
        validate_tree_snapshot_hash("0" * 64)


def test_malformed_tree_hash_is_rejected():
    for bad in ("", "abc", "A" * 64, "0" * 63):
        with pytest.raises(TelemetryEventError):
            validate_tree_snapshot_hash(bad)


def test_intent_is_truncated_to_500_chars():
    event = build_event(**_base(intent="あ" * 600))
    assert len(event["intent"]) == 500


def test_window_title_is_truncated_to_200_chars():
    event = build_event(**_base(window_title="い" * 300))
    assert len(event["window_title"]) == 200


def test_memory_sink_collects_events():
    sink = MemoryTelemetrySink()
    sink.append(build_event(**_base()))
    sink.append(build_event(**_base(error_category="matcher_index_missing")))
    assert sink.categories() == ["matcher_below_threshold", "matcher_index_missing"]


def test_jsonl_sink_appends_utf8_lines(tmp_path):
    path = tmp_path / "logs" / "telemetry.jsonl"
    sink = JsonlTelemetrySink(str(path))
    sink.append(build_event(**_base()))
    sink.append(build_event(**_base(error_category="matcher_index_missing")))

    raw = path.read_bytes()
    assert raw.count(b"\n") == 2
    # UTF-8 end to end: Japanese must survive without escapes or mojibake.
    text = raw.decode("utf-8")
    assert "弥生会計" in text
    assert "\\u5f18" not in text

    lines = [json.loads(line) for line in text.splitlines()]
    assert [line["error_category"] for line in lines] == [
        "matcher_below_threshold",
        "matcher_index_missing",
    ]
    # Append-only: a second writer instance adds to the same file.
    JsonlTelemetrySink(str(path)).append(build_event(**_base()))
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3
