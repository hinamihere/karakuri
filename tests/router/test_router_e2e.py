"""End-to-end routing with the real ONNX model (KARA-9 acceptance criteria).

Two things are proven here:

1. A known recipe prompt routes to Mode A — with the ``no_network`` fixture
   failing the test on any socket/URL access, so "0 network calls" is an
   observed property rather than a claim.
2. The threshold boundary behaves as contracts.md §6.1 specifies against real
   cosine scores: at-or-above 0.82 is Mode A, below is Mode B with a
   ``matcher_below_threshold`` telemetry event.

If the model has not been fetched these tests skip with a pointer to
``scripts/fetch-embedding-model.py``; set ``KARAKURI_REQUIRE_MODEL=1`` to
turn that skip into a failure so a run cannot pass without executing them.
"""

from __future__ import annotations

import pytest

from agent.router.index import RecipeIndex
from agent.router.router import MODE_A, MODE_B, IntentRouter

THRESHOLD = 0.82

# (intent, expected recipe, expected mode) — scored against the real model.
KNOWN_RECIPE_INTENTS = [
    ("弥生会計で仕訳を新規作成して保存する", "kara-yayoi-journal-new", MODE_A),
    ("仕訳の新規作成", "kara-yayoi-journal-new", MODE_A),
    ("弥生会計で請求書を印刷する", "kara-yayoi-invoice-print", MODE_A),
    ("奉行で経費伝票を登録する", "kara-bugyo-expense-register", MODE_A),
    ("SAP GUI で会計伝票を転記してポストする", "kara-sap-gui-post-voucher", MODE_A),
    # English intent, Japanese recipe: cross-lingual routing still hits Mode A.
    ("create a new journal entry in yayoi accounting", "kara-yayoi-journal-new", MODE_A),
]

OUT_OF_SCOPE_INTENTS = [
    "今日の天気は晴れですか",
    "Pythonで関数を定義する方法を教えて",
    "忘年会の会場予約をする",
]


def _route(router, intent, window_title, tree_hash):
    return router.route(intent, window_title=window_title, tree_snapshot_hash=tree_hash)


@pytest.mark.parametrize("intent,expected_recipe,expected_mode", KNOWN_RECIPE_INTENTS)
def test_known_recipe_prompt_routes_to_mode_a_without_network(
    no_network, real_router, window_title, tree_hash, intent, expected_recipe, expected_mode
):
    result = _route(real_router, intent, window_title, tree_hash)
    assert result.mode == expected_mode, f"{intent!r} -> {result.mode} ({result.similarity})"
    assert result.recipe_id == expected_recipe
    assert result.similarity >= THRESHOLD, result.similarity
    assert result.threshold == THRESHOLD
    # Mode A: 0 LLM tokens and no routing-stage telemetry at all.
    assert result.telemetry_events == ()
    assert real_router._telemetry.events == []


@pytest.mark.parametrize("intent", OUT_OF_SCOPE_INTENTS)
def test_unrelated_intent_routes_to_mode_b(
    no_network, real_router, window_title, tree_hash, intent
):
    result = _route(real_router, intent, window_title, tree_hash)
    assert result.mode == MODE_B, f"{intent!r} -> {result.mode} ({result.similarity})"
    assert result.similarity < THRESHOLD, result.similarity
    assert result.recipe_id is None

    events = result.telemetry_events
    assert len(events) == 1
    event = events[0]
    assert event["error_category"] == "matcher_below_threshold"
    assert event["status"] == "fallback_applied"
    assert event["fallback_attempted"] is True
    assert event["execution_mode"] == MODE_B
    assert event["intent"] == intent
    assert event["tree_snapshot_hash"] == tree_hash
    assert list(real_router._telemetry.events) == list(events)


def test_routing_never_emits_an_llm_category_or_llm_output(
    no_network, real_router, window_title, tree_hash
):
    for intent in OUT_OF_SCOPE_INTENTS + [KNOWN_RECIPE_INTENTS[0][0]]:
        result = _route(real_router, intent, window_title, tree_hash)
        for event in result.telemetry_events:
            assert event["llm_output"] is None
            assert not str(event["error_category"]).startswith("llm_")


def test_route_is_deterministic(no_network, real_router, window_title, tree_hash):
    intent = "弥生会計で仕訳を新規作成して保存する"
    first = _route(real_router, intent, window_title, tree_hash)
    second = _route(real_router, intent, window_title, tree_hash)
    assert first.mode == second.mode == MODE_A
    assert first.similarity == second.similarity  # bit-for-bit, not just close
    assert first.recipe_id == second.recipe_id
    assert [c.similarity for c in first.candidates] == [
        c.similarity for c in second.candidates
    ]


def test_unrelated_intent_is_deterministic(
    no_network, real_router, window_title, tree_hash
):
    intent = "忘年会の会場予約をする"
    first = _route(real_router, intent, window_title, tree_hash)
    second = _route(real_router, intent, window_title, tree_hash)
    assert first.similarity == second.similarity
    assert first.mode == second.mode == MODE_B


def test_empty_index_routes_everything_to_mode_b(
    no_network, embedder, matcher_config, telemetry, clock, window_title, tree_hash
):
    router = IntentRouter(
        embedder,
        RecipeIndex.empty(embedder.dim),
        matcher_config,
        telemetry,
        clock=clock,
    )
    result = _route(router, "弥生会計で仕訳を新規作成する", window_title, tree_hash)
    assert result.mode == MODE_B
    assert result.similarity is None
    assert [e["error_category"] for e in telemetry.events] == ["matcher_index_missing"]
    assert telemetry.events[0]["status"] == "fallback_applied"
    assert telemetry.events[0]["execution_mode"] == MODE_B


def test_index_load_failure_becomes_an_empty_index(tmp_path):
    loaded = IntentRouter.load_index(str(tmp_path / "missing.faiss"), dim=4)
    assert len(loaded) == 0
    assert bool(loaded) is False


def test_prefix_style_is_detected_as_e5_for_the_default_model(model_path):
    from agent.router.embedder import detect_prefix_style

    assert detect_prefix_style(model_path) == "e5"


def test_model_without_config_json_gets_no_prefix(tmp_path):
    from agent.router.embedder import PREFIX_STYLE_NONE, detect_prefix_style

    model = tmp_path / "m.onnx"
    model.write_bytes(b"")
    assert detect_prefix_style(str(model)) == PREFIX_STYLE_NONE
