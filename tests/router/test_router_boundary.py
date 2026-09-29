"""The Mode A / Mode B boundary — contracts.md §6.1.

These tests drive :class:`IntentRouter.route` with stub embedder/index
objects so the threshold comparison can be exercised at exact float values
that no real model would ever produce. The real-model behaviour lives in
``test_router_e2e.py``.
"""

from __future__ import annotations

import pytest

from agent.router.config import MatcherConfig
from agent.router.router import MODE_A, MODE_B, TOP_K, IntentRouter


class StubEmbedder:
    """Returns a fixed vector; the stub index controls the score."""

    dim = 4

    def embed_query(self, text):
        return [0.0] * self.dim

    def embed_passages(self, texts):
        return [[0.0] * self.dim for _ in texts]


class StubIndex:
    dim = 4

    def __init__(self, results):
        self._results = list(results)
        self.queries = 0
        self.last_top_k = None

    def __len__(self):
        return len(self._results)

    def __bool__(self):
        return bool(self._results)

    def search(self, vector, top_k=3):
        self.queries += 1
        self.last_top_k = top_k
        return self._results[:top_k]


def _config(threshold=0.82):
    return MatcherConfig(onnx_model_path="unused.onnx", similarity_threshold=threshold)


def _router(results, threshold=0.82, telemetry=None, clock=None):
    if telemetry is None:
        from agent.router.telemetry import MemoryTelemetrySink

        telemetry = MemoryTelemetrySink()
    if clock is None:
        clock = lambda: "2026-09-29T00:00:00.000Z"  # noqa: E731 - fixed test clock
    index = StubIndex(results)
    return (
        IntentRouter(
            StubEmbedder(),
            index,
            _config(threshold),
            telemetry,
            clock=clock,
        ),
        index,
    )


HASH = "7f3a" + "b2c1" * 15


def _route(router, intent="仕訳を作成"):
    return router.route(intent, window_title="弥生会計", tree_snapshot_hash=HASH)


@pytest.mark.parametrize(
    "similarity,expected_mode",
    [
        (0.82, MODE_A),  # the frozen boundary itself routes to Mode A
        (0.8200001, MODE_A),
        (0.83, MODE_A),
        (1.0, MODE_A),
        (0.8199999, MODE_B),
        (0.81, MODE_B),
        (0.0, MODE_B),
        (-1.0, MODE_B),
    ],
)
def test_threshold_boundary(similarity, expected_mode):
    router, _ = _router([("kara-recipe", similarity)])
    result = _route(router)
    assert result.mode == expected_mode
    assert result.similarity == similarity
    assert result.threshold == 0.82
    if expected_mode == MODE_A:
        assert result.recipe_id == "kara-recipe"
    else:
        assert result.recipe_id is None


def test_mode_a_searches_top_k_three_and_emits_no_telemetry():
    from agent.router.telemetry import MemoryTelemetrySink

    sink = MemoryTelemetrySink()
    router, index = _router(
        [("a", 0.9), ("b", 0.88), ("c", 0.85), ("d", 0.1)], telemetry=sink
    )
    result = _route(router)
    assert result.mode == MODE_A
    assert index.last_top_k == TOP_K == 3
    assert [c.recipe_id for c in result.candidates] == ["a", "b", "c"]
    assert result.telemetry_events == ()
    assert sink.events == []


def test_mode_b_emits_exactly_one_matcher_below_threshold_event():
    from agent.router.telemetry import MemoryTelemetrySink

    sink = MemoryTelemetrySink()
    router, _ = _router([("a", 0.81)], telemetry=sink)
    result = _route(router, intent="弥生会計で請求書を印刷する")

    assert result.mode == MODE_B
    assert len(result.telemetry_events) == 1
    assert list(sink.events) == list(result.telemetry_events)

    event = result.telemetry_events[0]
    assert event["execution_mode"] == MODE_B
    assert event["status"] == "fallback_applied"
    assert event["error_category"] == "matcher_below_threshold"
    assert event["fallback_attempted"] is True
    assert event["intent"] == "弥生会計で請求書を印刷する"
    assert event["window_title"] == "弥生会計"
    assert event["tree_snapshot_hash"] == HASH
    assert event["timestamp"] == "2026-09-29T00:00:00.000Z"
    assert event["llm_output"] is None
    assert event["resolved_target"] is None
    assert event["error_category"] not in {  # Mode B is not reached yet: no llm_* category
        "llm_timeout",
        "llm_unreachable",
        "llm_malformed_json",
        "llm_unknown_action",
        "llm_schema_violation",
    }


def test_mode_b_is_the_destination_not_a_failure_status():
    router, _ = _router([("a", 0.5)])
    result = _route(router)
    assert result.is_mode_b is True
    assert result.is_mode_a is False


def test_empty_index_routes_to_mode_b_with_index_missing_event():
    from agent.router.telemetry import MemoryTelemetrySink

    sink = MemoryTelemetrySink()
    router, index = _router([], telemetry=sink)
    result = _route(router)

    assert result.mode == MODE_B
    assert result.similarity is None
    assert result.recipe_id is None
    assert result.candidates == ()
    event = result.telemetry_events[0]
    assert event["error_category"] == "matcher_index_missing"
    assert event["status"] == "fallback_applied"
    assert event["fallback_attempted"] is True
    assert event["execution_mode"] == MODE_B
    assert sink.categories() == ["matcher_index_missing"]


def test_configured_threshold_is_honoured():
    router, _ = _router([("a", 0.6)], threshold=0.5)
    assert _route(router).mode == MODE_A
    router, _ = _router([("a", 0.6)], threshold=0.7)
    assert _route(router).mode == MODE_B


def test_router_rejects_a_dim_mismatch():
    from agent.router.index import RecipeIndex

    with pytest.raises(ValueError):
        IntentRouter(StubEmbedder(), RecipeIndex.empty(8), _config(), None)


def test_route_makes_no_network_calls(no_network):
    # The no_network fixture raises on any connect/getaddrinfo/urlopen.
    router, _ = _router([("a", 0.95)])
    assert _route(router).mode == MODE_A
    router, _ = _router([("a", 0.1)])
    assert _route(router).mode == MODE_B


def test_route_is_deterministic():
    router, _ = _router([("a", 0.9)])
    first = _route(router)
    second = _route(router)
    assert first.mode == second.mode
    assert first.similarity == second.similarity
    assert first.recipe_id == second.recipe_id
    assert [c.recipe_id for c in first.candidates] == [
        c.recipe_id for c in second.candidates
    ]
