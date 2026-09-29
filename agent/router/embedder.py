"""ONNX Runtime text embedder for the intent matcher (KARA-9).

Loads a local ONNX sentence-embedding model plus its HuggingFace
``tokenizer.json`` and turns text into L2-normalised float32 vectors.

Design constraints from the frozen contracts:

* **Local only.** One ``CPUExecutionProvider`` session, no network, no
  telemetry, no model download at runtime (fetching assets is a separate,
  one-shot tool).
* **Budget.** ``contracts.md §9.2`` caps the matcher at <150 MB RAM and
  <150 ms for embedding + search. The default asset is the int8-quantised
  ``multilingual-e5-small`` (~118 MB of weights); the session runs with
  ``intra_op_num_threads=1``, sequential execution and full graph
  optimisation to keep the arena small and the timing stable.
* **Determinism.** Fixed sequence length, fixed pooling, fixed normalisation,
  single intra-op thread, no sampling anywhere. The same string always
  produces the same vector.

E5-style prefixes (``query: `` / ``passage: ``) are applied only when the
model declares itself an E5 model in the ``config.json`` sitting next to the
weights, so pointing ``[matcher].onnx_model_path`` at a BGE-M3 export does
not silently mis-prefix it. Callers may also force the choice with
``prefix_style`` (a code-level parameter, not a config key — ``config.toml``
is frozen).
"""

from __future__ import annotations

import json
import os
from typing import Iterable, Sequence

DEFAULT_MAX_SEQ_LEN = 128
E5_QUERY_PREFIX = "query: "
E5_PASSAGE_PREFIX = "passage: "

PREFIX_STYLE_AUTO = "auto"
PREFIX_STYLE_E5 = "e5"
PREFIX_STYLE_NONE = "none"
_PREFIX_STYLES = (PREFIX_STYLE_AUTO, PREFIX_STYLE_E5, PREFIX_STYLE_NONE)


class EmbedderError(RuntimeError):
    """Embedding could not be produced.

    ``error_category`` uses the frozen contracts.md §2.2 enum:
    ``config_onnx_model_missing`` for missing model/tokenizer assets,
    ``os_generic`` for everything else (ONNX Runtime failed to load or the
    inference itself failed).
    """

    def __init__(self, message: str, error_category: str = "os_generic") -> None:
        super().__init__(message)
        self.error_category = error_category


def _import_onnxruntime():
    try:
        import onnxruntime  # noqa: PLC0415 - imported lazily so the error is ours
    except ImportError as exc:  # pragma: no cover - environment specific
        raise EmbedderError(
            "ONNX Runtime could not be imported: "
            f"{exc}. On Windows this usually means the Microsoft Visual C++ "
            "2015-2022 Redistributable (vcruntime140_1.dll, msvcp140_1.dll) "
            "is missing — install vc_redist.x64.exe.",
            error_category="os_generic",
        ) from exc
    return onnxruntime


def _import_tokenizer():
    try:
        from tokenizers import Tokenizer  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment specific
        raise EmbedderError(
            "the `tokenizers` package is required to read tokenizer.json "
            "(pip/uv install tokenizers)",
            error_category="os_generic",
        ) from exc
    return Tokenizer


def detect_prefix_style(model_path: str) -> str:
    """Return ``"e5"`` or ``"none"`` from the ``config.json`` beside the weights.

    Absent or unreadable ``config.json`` means "no prefix" — the safe default,
    because a wrong ``query: `` prefix on a non-E5 model silently shifts every
    cosine score.
    """
    config_path = os.path.join(os.path.dirname(os.path.abspath(model_path)), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError):
        return PREFIX_STYLE_NONE
    if not isinstance(config, dict):
        return PREFIX_STYLE_NONE
    haystack = " ".join(
        str(config.get(key, "")) for key in ("_name_or_path", "name_or_path", "model_type")
    ).lower()
    return PREFIX_STYLE_E5 if "e5" in haystack else PREFIX_STYLE_NONE


class OnnxEmbedder:
    """Turns text into L2-normalised vectors using a local ONNX model."""

    def __init__(
        self,
        model_path: str,
        tokenizer_path: str | None = None,
        *,
        prefix_style: str = PREFIX_STYLE_AUTO,
        max_seq_len: int = DEFAULT_MAX_SEQ_LEN,
        intra_op_threads: int = 1,
    ) -> None:
        if prefix_style not in _PREFIX_STYLES:
            raise EmbedderError(
                f"prefix_style must be one of {_PREFIX_STYLES} (got {prefix_style!r})"
            )
        if not os.path.exists(model_path):
            raise EmbedderError(
                f"ONNX model not found: {model_path}",
                error_category="config_onnx_model_missing",
            )
        if tokenizer_path is None:
            tokenizer_path = os.path.join(
                os.path.dirname(os.path.abspath(model_path)), "tokenizer.json"
            )
        if not os.path.exists(tokenizer_path):
            raise EmbedderError(
                f"tokenizer.json not found next to the model: {tokenizer_path}",
                error_category="config_onnx_model_missing",
            )

        if prefix_style == PREFIX_STYLE_AUTO:
            prefix_style = detect_prefix_style(model_path)

        self.model_path = model_path
        self.tokenizer_path = tokenizer_path
        self.prefix_style = prefix_style
        self.max_seq_len = int(max_seq_len)
        self.intra_op_threads = int(intra_op_threads)

        ort = _import_onnxruntime()
        Tokenizer = _import_tokenizer()

        options = ort.SessionOptions()
        options.intra_op_num_threads = int(self.intra_op_threads)
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.log_severity_level = 3  # warnings and errors only, no stdout noise
        try:
            self._session = ort.InferenceSession(
                model_path,
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:  # noqa: BLE001 - surface ORT's own message
            raise EmbedderError(
                f"ONNX Runtime failed to load {model_path}: {exc}",
                error_category="os_generic",
            ) from exc

        inputs = {spec.name for spec in self._session.get_inputs()}
        self.providers = tuple(self._session.get_providers())
        for required in ("input_ids", "attention_mask"):
            if required not in inputs:
                raise EmbedderError(
                    f"model {model_path} does not expose `{required}`; "
                    "expected a HuggingFace-style encoder export"
                )
        self._has_token_type_ids = "token_type_ids" in inputs

        try:
            self._tokenizer = Tokenizer.from_file(tokenizer_path)
        except Exception as exc:  # noqa: BLE001
            raise EmbedderError(
                f"failed to read tokenizer {tokenizer_path}: {exc}",
                error_category="config_onnx_model_missing",
            ) from exc
        self._tokenizer.enable_truncation(max_length=self.max_seq_len)
        # Padding is applied per batch below; pad_id 0 is the XLM-R/BERT pad.
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=0)

        self._dim = int(self._infer_dim())

    # ------------------------------------------------------------------
    @property
    def dim(self) -> int:
        """Embedding dimensionality (384 for multilingual-e5-small)."""
        return self._dim

    def _infer_dim(self) -> int:
        import numpy as np  # noqa: PLC0415

        outputs = self._session.get_outputs()
        for spec in outputs:
            if spec.name == "last_hidden_state" and spec.shape and isinstance(spec.shape[-1], int):
                return spec.shape[-1]
        # Fall back to a tiny probe run — still fully local and deterministic.
        probe = self._run(np.zeros((1, 1), dtype=np.int64), np.ones((1, 1), dtype=np.int64))
        return int(probe.shape[-1])

    # ------------------------------------------------------------------
    def _prefix_for(self, kind: str) -> str:
        if self.prefix_style != PREFIX_STYLE_E5:
            return ""
        return E5_QUERY_PREFIX if kind == "query" else E5_PASSAGE_PREFIX

    def _encode(self, texts: Sequence[str], kind: str) -> "list[list[int]]":
        prefix = self._prefix_for(kind)
        return [self._tokenizer.encode(prefix + text).ids for text in texts]

    def _run(self, input_ids, attention_mask):
        import numpy as np  # noqa: PLC0415

        feeds = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        if self._has_token_type_ids:
            feeds["token_type_ids"] = np.zeros_like(input_ids)
        try:
            output = self._session.run(None, feeds)
        except Exception as exc:  # noqa: BLE001
            raise EmbedderError(
                f"ONNX inference failed for {self.model_path}: {exc}",
                error_category="os_generic",
            ) from exc
        return output[0]

    @staticmethod
    def _mean_pool(hidden, attention_mask):
        import numpy as np  # noqa: PLC0415

        mask = attention_mask[:, :, None].astype(np.float32)
        summed = (hidden.astype(np.float32) * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), 1.0, None)
        return summed / counts

    @staticmethod
    def _normalise(vectors):
        import numpy as np  # noqa: PLC0415

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.clip(norms, 1e-12, None)

    def embed(self, texts: Iterable[str], *, kind: str = "passage"):
        """Embed ``texts`` and return an ``(len(texts), dim)`` float32 matrix.

        ``kind`` is ``"query"`` for the user intent and ``"passage"`` for
        indexed recipe descriptions; it only matters for E5 models.
        """
        import numpy as np  # noqa: PLC0415

        if kind not in ("query", "passage"):
            raise EmbedderError(f"kind must be 'query' or 'passage' (got {kind!r})")
        texts = list(texts)
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)

        id_batches = self._encode(texts, kind)
        max_len = max(len(ids) for ids in id_batches)
        input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
        attention_mask = np.zeros((len(texts), max_len), dtype=np.int64)
        for row, ids in enumerate(id_batches):
            input_ids[row, : len(ids)] = ids
            attention_mask[row, : len(ids)] = 1

        hidden = self._run(input_ids, attention_mask)
        pooled = self._mean_pool(hidden, attention_mask)
        return self._normalise(pooled).astype(np.float32, copy=False)

    def embed_query(self, text: str):
        """Embed a single user intent. Returns shape ``(dim,)``."""
        return self.embed([text], kind="query")[0]

    def embed_passages(self, texts: Sequence[str]):
        """Embed recipe descriptions. Returns shape ``(len(texts), dim)``."""
        return self.embed(list(texts), kind="passage")
