"""Token budget enforcement (contracts.md §9.1, §9.5)."""

from __future__ import annotations

import math

import pytest

from core.a11y_tree import (
    PruneLimits,
    RawNode,
    Rect,
    build_compact_tree,
    count_tokens,
    within_budget,
)
from core.a11y_tree.pruner import BUDGET_EXCEEDED
from core.a11y_tree.tokens import BACKEND_APPROX, BACKEND_TIKTOKEN


def wide_window(buttons: int = 40) -> RawNode:
    """A shallow but wide Win32-style dialog: controls sit at depth 2."""
    return RawNode(
        control_type="Window",
        name="取引先一覧",
        bounding_rect=Rect(0, 0, 1024, 768),
        children=[
            RawNode(
                control_type="Pane",
                name="toolbar",
                bounding_rect=Rect(0, 0, 1024, 40),
                children=[
                    RawNode(
                        control_type="Button",
                        name=f"処理{i}",
                        automation_id=f"act-{i:03d}",
                        bounding_rect=Rect(i * 24, 0, 24, 24),
                    )
                    for i in range(buttons)
                ],
            )
        ],
    )


def test_small_tree_is_counted_with_cl100k_when_available():
    result = build_compact_tree(wide_window(3), limits=PruneLimits(max_tokens=10_000))
    assert result.token_backend == BACKEND_TIKTOKEN
    assert result.token_count > 0
    assert within_budget(result.token_count)


def test_tree_over_the_ceiling_is_repruned_shallower():
    limits = PruneLimits(max_depth=8, max_tokens=500)
    result = build_compact_tree(wide_window(40), limits=limits)
    assert result.token_count <= 500
    assert result.effective_max_depth < 8
    # the loop must not leave the ceiling unmet silently
    assert not [e for e in result.events if e.error_category == BUDGET_EXCEEDED]
    # the automation_id-bearing buttons cut by the shallower limit are reported
    cut = [e for e in result.events if e.error_category == "pruner_depth_cut"]
    assert cut, "depth-cutting 40 automation_id-bearing buttons must be reported"
    assert cut[0].automation_id.startswith("act-")
    assert cut[0].depth > result.effective_max_depth


def test_budget_exceeded_is_reported_once_when_even_root_fits_nothing():
    limits = PruneLimits(max_depth=8, max_tokens=5, min_budget_depth=1)
    result = build_compact_tree(wide_window(6), limits=limits)
    over = [e for e in result.events if e.error_category == BUDGET_EXCEEDED]
    assert len(over) == 1
    assert result.token_count > 5
    assert "limit 5" in over[0].detail


def test_no_budget_exceeded_when_tree_fits():
    result = build_compact_tree(wide_window(3), limits=PruneLimits(max_tokens=5000))
    assert not [e for e in result.events if e.error_category == BUDGET_EXCEEDED]


def test_max_tokens_ceiling_is_never_exceeded_for_a_deep_tree():
    def chain(depth: int) -> RawNode:
        node = RawNode(
            control_type="Button",
            name="deep" + "深" * 40,
            automation_id="deep-id",
            bounding_rect=Rect(1, 2, 3, 4),
        )
        for i in range(depth - 1):
            node = RawNode(
                control_type="Pane",
                name=f"lvl{i}",
                bounding_rect=Rect(0, 0, 10, 10),
                children=[node],
            )
        return RawNode(control_type="Window", name="w", children=[node])

    result = build_compact_tree(chain(30), limits=PruneLimits(max_tokens=500))
    assert result.token_count <= 500
    assert result.effective_max_depth <= 8


def test_count_tokens_approx_backend_over_estimates_on_realistic_text():
    samples = [
        "保存する前に確認してください。 OK ボタンを押しますか？",
        "bounding_rect: {x: 1100, y: 640, width: 100, height: 32}",
        "      automation_id: act-017",
        "Click the OK button to confirm the operation and continue.",
        "name: 弥生会計 2024 - 仕訳入力",
    ]
    for text in samples:
        approx, backend = count_tokens(text, backend="approx")
        real, real_backend = count_tokens(text, backend="tiktoken")
        assert backend == BACKEND_APPROX
        assert real_backend == BACKEND_TIKTOKEN
        assert approx >= real, f"fallback under-counted {text!r}: {approx} < {real}"


def test_count_tokens_rejects_unknown_backend():
    with pytest.raises(ValueError):
        count_tokens("x", backend="bpe-magic")


def test_within_budget_bounds():
    assert not within_budget(199)
    assert within_budget(200)
    assert within_budget(500)
    assert not within_budget(501)
