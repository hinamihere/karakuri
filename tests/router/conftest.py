"""Shared fixtures for the intent-router tests (KARA-9)."""

from __future__ import annotations

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

MODEL_PATH = os.path.join(REPO_ROOT, "models", "multilingual-e5-small-int8.onnx")
FIXTURE_RECIPES = os.path.join(REPO_ROOT, "tests", "router", "fixtures", "recipes")

# contracts.md §6.1 — any 64-hex, non-zero hash (§2.1 forbids all zeros).
TREE_HASH = "7f3a" + "b2c1" * 15
WINDOW_TITLE = "弥生会計 2024 - 仕訳入力"

# Set KARAKURI_REQUIRE_MODEL=1 to turn "model not fetched" into a failure
# instead of a skip, so a run cannot pass without exercising the real model.
REQUIRE_MODEL = os.environ.get("KARAKURI_REQUIRE_MODEL", "") not in ("", "0", "false")


def model_missing_reason() -> str | None:
    if os.path.exists(MODEL_PATH):
        return None
    message = (
        f"embedding model not found at {MODEL_PATH} — run "
        "`python scripts/fetch-embedding-model.py` first"
    )
    if REQUIRE_MODEL:
        pytest.fail(message)
    return message


@pytest.fixture(scope="session")
def repo_root() -> str:
    return REPO_ROOT


@pytest.fixture(scope="session")
def fixture_recipes_dir() -> str:
    return FIXTURE_RECIPES


@pytest.fixture(scope="session")
def tree_hash() -> str:
    return TREE_HASH


@pytest.fixture(scope="session")
def window_title() -> str:
    return WINDOW_TITLE


@pytest.fixture(scope="session")
def model_path() -> str:
    reason = model_missing_reason()
    if reason:
        pytest.skip(reason)
    return MODEL_PATH


@pytest.fixture(scope="session")
def embedder(model_path):
    from agent.router.embedder import OnnxEmbedder

    return OnnxEmbedder(model_path)


@pytest.fixture(scope="session")
def recipe_index(embedder, fixture_recipes_dir):
    from agent.router.index import RecipeIndex
    from agent.router.recipes import index_text, load_recipe_metas

    metas, problems = load_recipe_metas(fixture_recipes_dir)
    assert not problems, f"fixture recipes must all load: {problems}"
    vectors = embedder.embed_passages([index_text(meta) for meta in metas])
    return RecipeIndex.build([meta.id for meta in metas], vectors)


@pytest.fixture(scope="session")
def matcher_config():
    from agent.router.config import MatcherConfig

    return MatcherConfig(onnx_model_path=MODEL_PATH)


@pytest.fixture
def telemetry():
    from agent.router.telemetry import MemoryTelemetrySink

    return MemoryTelemetrySink()


@pytest.fixture
def clock():
    """Deterministic timestamp for reproducible telemetry assertions."""
    return lambda: "2026-09-29T00:00:00.000Z"


@pytest.fixture
def real_router(embedder, recipe_index, matcher_config, telemetry, clock):
    from agent.router.router import IntentRouter

    return IntentRouter(embedder, recipe_index, matcher_config, telemetry, clock=clock)


@pytest.fixture
def no_network(monkeypatch):
    """Fail the test if anything under test tries to open a socket.

    The KARA-9 acceptance criterion is "0 network calls" for the Mode A path,
    so the guard is a fixture rather than a claim in a comment.
    """
    import socket
    import urllib.request

    class NetworkBlocked(RuntimeError):
        pass

    def blocked(*_args, **_kwargs):
        raise NetworkBlocked("network access attempted during intent routing")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "gethostbyname", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    return NetworkBlocked
