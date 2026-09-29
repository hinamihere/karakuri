"""Recipe embedding index — build, search, save/load (contracts.md §6.1, §10.2)."""

from __future__ import annotations

import numpy as np
import pytest

from agent.router.index import IndexLoadError, RecipeIndex


def _unit(dim=4, axis=0):
    vec = np.zeros(dim, dtype=np.float32)
    vec[axis] = 1.0
    return vec


def test_build_and_search_orders_by_cosine():
    ids = ["r-c", "r-a", "r-b"]
    vectors = np.stack([_unit(axis=1), _unit(axis=0), _unit(axis=2)])
    index = RecipeIndex.build(ids, vectors)
    assert len(index) == 3
    assert bool(index) is True

    hits = index.search(_unit(axis=0), top_k=3)
    assert [h[0] for h in hits] == ["r-a", "r-b", "r-c"]
    assert hits[0][1] == pytest.approx(1.0)


def test_search_respects_top_k():
    ids = [f"r{i}" for i in range(10)]
    rng = np.random.default_rng(0)
    vectors = rng.random((10, 8), dtype=np.float32)
    index = RecipeIndex.build(ids, vectors)
    assert len(index.search(vectors[0], top_k=3)) == 3
    assert len(index.search(vectors[0], top_k=99)) == 10


def test_search_ties_are_broken_by_recipe_id():
    # Two identical vectors => identical scores; order must still be stable.
    ids = ["zeta", "alpha"]
    vectors = np.stack([_unit(), _unit()])
    index = RecipeIndex.build(ids, vectors)
    assert [h[0] for h in index.search(_unit(), top_k=2)] == ["alpha", "zeta"]
    assert [h[0] for h in index.search(_unit(), top_k=2)] == ["alpha", "zeta"]


def test_empty_index_searches_to_nothing():
    index = RecipeIndex.empty(4)
    assert len(index) == 0
    assert bool(index) is False
    assert index.search(_unit(), top_k=3) == []


def test_saving_an_empty_index_is_refused():
    with pytest.raises(IndexLoadError):
        RecipeIndex.empty(4).save("unused.faiss")


def test_save_load_roundtrip(tmp_path):
    ids = ["r-b", "r-a"]
    vectors = np.stack([_unit(axis=1), _unit(axis=0)])
    path = str(tmp_path / "recipe_index.faiss")
    RecipeIndex.build(ids, vectors).save(path)

    loaded = RecipeIndex.load(path, dim=4)
    assert loaded.ids == ("r-b", "r-a")
    assert loaded.search(_unit(axis=0), top_k=2) == RecipeIndex.build(
        ids, vectors
    ).search(_unit(axis=0), top_k=2)


def test_missing_index_raises_index_load_error(tmp_path):
    with pytest.raises(IndexLoadError) as excinfo:
        RecipeIndex.load(str(tmp_path / "nope.faiss"), dim=4)
    assert "not found" in str(excinfo.value)


def test_index_built_for_another_model_is_rejected(tmp_path):
    path = str(tmp_path / "recipe_index.faiss")
    RecipeIndex.build(["r"], _unit(4).reshape(1, 4)).save(path)
    with pytest.raises(IndexLoadError) as excinfo:
        RecipeIndex.load(path, dim=8)
    assert "dim" in str(excinfo.value)


def test_corrupt_id_sidecar_is_rejected(tmp_path):
    path = str(tmp_path / "recipe_index.faiss")
    RecipeIndex.build(["r"], _unit(4).reshape(1, 4)).save(path)
    with open(path + ".ids.json", "w", encoding="utf-8") as handle:
        handle.write("{not json")
    with pytest.raises(IndexLoadError):
        RecipeIndex.load(path, dim=4)


def test_id_vector_count_mismatch_is_rejected():
    with pytest.raises(ValueError):
        RecipeIndex.build(["a", "b"], _unit(4).reshape(1, 4))


def test_search_rejects_a_query_of_the_wrong_dimension():
    index = RecipeIndex.build(["r"], _unit(4).reshape(1, 4))
    with pytest.raises(ValueError):
        index.search(_unit(8), top_k=1)
