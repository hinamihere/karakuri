# Intent router — `agent/router` (KARA-9)

Mode A / Mode B routing: embed the user intent with a **local** ONNX model,
cosine-search the indexed recipe description vectors, and cut at the frozen
**0.82** boundary (contracts.md §6.1).

| ≥ 0.82 | Mode A — deterministic recipe replay, **0 LLM tokens, 0 network calls** |
| < 0.82 | Mode B — guarded live planning, telemetry `matcher_below_threshold` |

Nothing in this package opens a socket. The only I/O is the local ONNX model,
the local recipe index and the local `logs/telemetry.jsonl`.

---

## Quick start

```bash
# 1. isolated environment + dependencies
uv venv .venv
uv pip install --python .venv -r agent/router/requirements.txt

# 2. one-shot asset fetch (the runtime never does this)
.venv/Scripts/python.exe scripts/fetch-embedding-model.py

# 3. copy the config and point it at your recipes
cp config.example.toml config.toml

# 4. build the embedding index
.venv/Scripts/python.exe -m agent.router build-index --config config.toml

# 5. route one intent (offline)
.venv/Scripts/python.exe -m agent.router route --config config.toml \
  --intent "弥生会計で仕訳を新規作成して保存する" \
  --window-title "弥生会計 2024" --tree-file path/to/tree.yaml

# 6. tests
KARAKURI_REQUIRE_MODEL=1 .venv/Scripts/python.exe -m pytest tests/router -q
```

`--tree-hash <64-hex>` may be passed instead of `--tree-file`; the hash is
mandatory because contracts.md §2.1 requires it on every telemetry event and
forbids an all-zeros value. The canonical hash comes from the pruner (KARA-6),
so `--tree-file` (sha256 of the serialized tree bytes) exists for use before
the two modules are wired together.

## Windows prerequisite

`onnxruntime` needs the **Microsoft Visual C++ 2015-2022 Redistributable**
(`vcruntime140_1.dll`, `msvcp140_1.dll`). On a machine without it the import
fails with a bare `ImportError: DLL load failed`. `OnnxEmbedder` catches that
and re-raises with the exact remediation; install `vc_redist.x64.exe`.

## Files

| File | Role |
|---|---|
| `config.py` | `config.toml` `[matcher]` / `[app]` keys, §5.3 and §5.5 validation |
| `embedder.py` | ONNX session + tokenizer → L2-normalised float32 vectors |
| `index.py` | FAISS recipe index, save/load, deterministic top-k |
| `recipes.py` | read-only `id` / `name` / `description` extraction (no schema validation — that is KARA-11) |
| `telemetry.py` | §2 event builder with the frozen field rules + JSONL sink |
| `router.py` | the §6.1 routing pseudocode |
| `cli.py` | `build-index` and `route` |

## Design decisions

**Index configuration** (contracts.md §10.2 leaves this to the Developer):

- type: `faiss.IndexFlatIP` — exact search, no graph, fully deterministic
- metric: inner product over L2-normalised vectors == cosine
- dimension: read from the model at runtime (384 for the default asset)
- `top_k`: 3, per §6.1
- ids: FAISS stores `int64`, recipe ids are strings, so
  `<index>.ids.json` holds the id list (row *i* ↔ id *i*)

Flat is right for a recipe library of tens of entries: exact, deterministic
(the "same intent → same recipe" rule), and far under the 150 ms budget.

**Saving uses `faiss.serialize_index` + Python file I/O**, not
`faiss.write_index`. `write_index` opens the path with a narrow-char `fopen`
and fails outright on non-ASCII Windows profile paths — which is this
workspace. The bytes written are identical.

**E5 prefixes.** `intfloat/multilingual-e5-small` expects `query: ` /
`passage: ` prefixes; measured on the default asset, dropping them pulls an
unrelated Japanese intent from 0.818 to 0.829, i.e. straight over the frozen
0.82 boundary. The prefix is applied only when the `config.json` next to the
weights declares an `e5` model, so pointing `onnx_model_path` at a BGE-M3
export does not mis-prefix it. Callers can force the choice with
`prefix_style=` — a code parameter, because `config.toml` is frozen and this
is not a config key.

**Index text** is `name` + newline + `description` (or `name` alone when the
recipe has no description). contracts.md §1.1 calls `description` "*additional*
embedding context", and a description-less recipe would otherwise be
unreachable.

**Empty index ≠ failure.** Per §5.2 an absent/unreadable/mis-sized index
becomes an empty index at load time; the first execution that needs it logs
`status: fallback_applied`, `error_category: matcher_index_missing`.

**Failure paths** (`error_category` from the frozen §2.2 enum):

| Situation | Behaviour |
|---|---|
| `[matcher].onnx_model_path` missing / empty / file absent | `MatcherConfigError("config_onnx_model_missing")` at startup |
| unknown key in `[app]` / `[matcher]` | ignored, `ConfigWarning("config_unknown_key")` |
| threshold outside 0–1 | clamped to `[0, 1]`, warning (§5.3) |
| non-numeric threshold | `MatcherConfigError`, **no category** — see below |
| model or `tokenizer.json` absent | `EmbedderError("config_onnx_model_missing")` |
| ONNX Runtime fails to load / inference fails | `EmbedderError("os_generic")` with the underlying message |
| index missing / corrupt / wrong dimension | empty index, `matcher_index_missing` telemetry on first use |
| best similarity < threshold | `matcher_below_threshold` telemetry, `status: fallback_applied` |
| unreadable / id-less / duplicate recipe | `RecipeMetaError("recipe_invalid")`, collected, not raised |

Config problems are **raised with their category attached** rather than
written to telemetry: a startup failure has no `intent`, no `window_title` and
no `tree_snapshot_hash`, and §2.1 makes `tree_snapshot_hash` mandatory while
§2.1 forbids an all-zeros value. The caller decides how to log them.

## Measured on this machine (Windows 10, Core i-class CPU)

```
[matcher budget]   model weights 118,054,593 B (118.1 MB) + index 6,324 B
                   = 118,060,917 B (118.1 MB)     < 150 MB budget  ✓
[matcher latency]  embed + search over 30 routes: avg 6.20 ms,
                   worst 7.57 ms                  < 150 ms budget  ✓
[matcher memory]   clean subprocess: 12.0 MB baseline -> 436.4 MB with model
                   -> 458.8 MB with index (delta 446.8 MB)
```

### Measured memory — open question for the Architect

contracts.md §9.2's RAM row reads `< 150 MB | ONNX model weights + FAISS
index`, and by that definition the matcher passes at **118.1 MB**. The
*process working set* with the same model loaded is **~459 MB**, because:

| Component | Working-set cost |
|---|---|
| python + numpy + onnxruntime | ~30 MB |
| `tokenizer.json` (XLM-R 250k vocab) | ~262 MB |
| int8 ONNX session | ~135 MB |

Neither named option can meet 150 MB of *process* RSS: BGE-M3 is ~568 MB of
int8 weights alone, and `multilingual-e5-small` is 118 MB of weights plus a
262 MB tokenizer. The test suite asserts the definition §9.2 actually writes
(weights + index) and reports the process number; changing the budget, or
swapping to a smaller encoder, is an Architect decision.

## Known contract gaps (not fixed here)

1. **Startup failures have no valid telemetry context.** §5.3/§5.5 require an
   `error_category` at startup, but §2.1 requires every event to carry a real
   (non-zero) `tree_snapshot_hash` — which does not exist yet at startup.
2. **No category for a non-numeric `similarity_threshold`** and none for a
   clamped threshold's warning; §2.2 has no `config_invalid_value`.

Both need an Architect ruling before the daemon can log them properly.

## Tests

```bash
KARAKURI_REQUIRE_MODEL=1 .venv/Scripts/python.exe -m pytest tests/router -q
```

82 tests. `KARAKURI_REQUIRE_MODEL=1` turns "model not fetched" into a failure
so a run cannot pass by skipping the real end-to-end cases.

- `test_router_boundary.py` — the 0.82 cut at exact float values, both sides
- `test_router_e2e.py` — real model, real fixture recipes, **`no_network`
  fixture fails the test on any socket/URL access**
- `test_config.py`, `test_telemetry.py`, `test_index.py`, `test_recipes.py`
- `test_budget.py` — weights+index and latency asserted, process RSS reported
