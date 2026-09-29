"""Recipe embedding index (contracts.md §6.1, §9.2, §10.2).

Index configuration — this is the Developer's call per §10.2:

* **Type:** ``faiss.IndexFlatIP`` (exact / brute force)
* **Metric:** inner product over L2-normalised vectors == cosine similarity
* **Dimension:** the embedding model's output dimension (384 for
  multilingual-e5-small), read from the model at runtime
* **top_k:** 3, per the frozen routing pseudocode in §6.1

Flat is deliberate: a Karakuri install holds tens of recipes, not millions.
Exact search is deterministic (no graph construction, no approximate
neighbours) which is what "same intent + same window -> same recipe" needs,
and it is far below the 150 ms budget.

Recipe ids are strings, and FAISS stores ``int64`` only, so the id list is
written next to the index as ``<path>.ids.json`` — position ``i`` in that
list is the id of FAISS row ``i``. Both files together are "the index".
"""

from __future__ import annotations

import json
import os
from typing import Sequence

import numpy as np

IDS_SUFFIX = ".ids.json"


class IndexLoadError(RuntimeError):
    """The on-disk index is missing, unreadable or built for another model.

    The router converts this into the ``matcher_index_missing`` telemetry
    event required by contracts.md §5.2 and continues with an empty index
    (which routes everything to Mode B) rather than crashing at startup.
    """


def _ids_path(index_path: str) -> str:
    return index_path + IDS_SUFFIX


def _import_faiss():
    try:
        import faiss  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment specific
        raise IndexLoadError(
            "the `faiss-cpu` package is required by the recipe index "
            f"(pip/uv install faiss-cpu): {exc}"
        ) from exc
    return faiss


class RecipeIndex:
    """Cosine index over recipe description vectors."""

    def __init__(self, ids: Sequence[str], vectors: np.ndarray, dim: int) -> None:
        ids = tuple(str(i) for i in ids)
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        if vectors.ndim != 2:
            raise ValueError(f"vectors must be 2-D, got shape {vectors.shape}")
        if len(ids) != vectors.shape[0]:
            raise ValueError(
                f"id/vector count mismatch: {len(ids)} ids vs {vectors.shape[0]} vectors"
            )
        if vectors.shape[1] != dim:
            raise ValueError(
                f"vector dim {vectors.shape[1]} does not match index dim {dim}"
            )
        self._ids = ids
        self._dim = int(dim)
        self._index = None
        if ids:
            faiss = _import_faiss()
            index = faiss.IndexFlatIP(self._dim)
            index.add(vectors)
            self._index = index
        self._vectors = vectors

    # ------------------------------------------------------------------
    @classmethod
    def empty(cls, dim: int) -> "RecipeIndex":
        return cls((), np.zeros((0, int(dim)), dtype=np.float32), int(dim))

    @classmethod
    def build(cls, ids: Sequence[str], vectors: np.ndarray) -> "RecipeIndex":
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1 and len(ids) == 1:
            vectors = vectors.reshape(1, -1)
        dim = int(vectors.shape[1]) if vectors.size else 0
        return cls(ids, vectors, dim)

    # ------------------------------------------------------------------
    @property
    def dim(self) -> int:
        return self._dim

    @property
    def ids(self) -> tuple[str, ...]:
        return self._ids

    def __len__(self) -> int:
        return len(self._ids)

    def __bool__(self) -> bool:
        return bool(self._ids)

    # ------------------------------------------------------------------
    def save(self, path: str) -> None:
        """Write the index with Python file I/O.

        ``faiss.write_index`` is deliberately not used: it opens the path with
        a narrow-char ``fopen``, which fails outright when the absolute path
        is not representable in the ANSI codepage (this workspace runs under
        a non-ASCII Windows user profile). ``serialize_index`` plus Python's
        wide path handling produces byte-identical output and always works.
        """
        if not self._ids:
            raise IndexLoadError("refusing to save an empty index — nothing to replay")
        faiss = _import_faiss()
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        blob = np.asarray(faiss.serialize_index(self._index), dtype=np.uint8)
        with open(path, "wb") as handle:
            handle.write(blob.tobytes())
        with open(_ids_path(path), "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"dim": self._dim, "ids": list(self._ids)}, handle, ensure_ascii=False)

    @classmethod
    def load(cls, path: str, dim: int) -> "RecipeIndex":
        """Load the index, raising :class:`IndexLoadError` for every failure."""
        ids_path = _ids_path(path)
        if not os.path.exists(path) or not os.path.exists(ids_path):
            raise IndexLoadError(f"recipe index not found: {path}")
        faiss = _import_faiss()
        try:
            with open(ids_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as exc:
            raise IndexLoadError(f"recipe index id file unreadable: {ids_path}: {exc}") from exc
        ids = payload.get("ids") if isinstance(payload, dict) else None
        stored_dim = payload.get("dim") if isinstance(payload, dict) else None
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise IndexLoadError(f"recipe index id file malformed: {ids_path}")
        if stored_dim is not None and int(stored_dim) != int(dim):
            raise IndexLoadError(
                f"recipe index was built with dim {stored_dim} but the configured "
                f"model produces dim {dim} — rebuild the index"
            )
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError as exc:
            raise IndexLoadError(f"recipe index unreadable: {path}: {exc}") from exc
        try:
            index = faiss.deserialize_index(np.frombuffer(raw, dtype=np.uint8).copy())
        except Exception as exc:  # noqa: BLE001 - faiss raises RuntimeError
            raise IndexLoadError(f"recipe index unreadable: {path}: {exc}") from exc
        if index.d != int(dim):
            raise IndexLoadError(
                f"recipe index dim {index.d} does not match model dim {dim} — "
                "rebuild the index"
            )
        if index.ntotal != len(ids):
            raise IndexLoadError(
                f"recipe index holds {index.ntotal} vectors but {len(ids)} ids are "
                f"recorded in {ids_path} — rebuild the index"
            )
        return cls._from_faiss(index, ids, dim)

    @classmethod
    def _from_faiss(cls, index, ids, dim) -> "RecipeIndex":
        obj = cls((), np.zeros((0, int(dim)), dtype=np.float32), int(dim))
        obj._index = index
        obj._ids = tuple(ids)
        obj._dim = int(dim)
        return obj

    # ------------------------------------------------------------------
    def search(self, vector: np.ndarray, top_k: int = 3) -> list[tuple[str, float]]:
        """Return the ``top_k`` ``(recipe_id, cosine)`` pairs, best first.

        Ties are broken by recipe id so the result never depends on FAISS's
        internal ordering — determinism is a hard contract rule (§6.2).
        """
        if not self._ids or top_k <= 0:
            return []
        vector = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if vector.shape[1] != self._dim:
            raise ValueError(
                f"query dim {vector.shape[1]} does not match index dim {self._dim}"
            )
        k = min(int(top_k), len(self._ids))
        scores, rows = self._index.search(vector, k)
        pairs = [
            (self._ids[int(row)], float(score))
            for row, score in zip(rows[0], scores[0])
            if int(row) >= 0
        ]
        pairs.sort(key=lambda pair: (-pair[1], pair[0]))
        return pairs
