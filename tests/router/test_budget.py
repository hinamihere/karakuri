"""Matcher budgets — contracts.md §9.2.

Two budgets, asserted:

* **Weights + index < 150 MB** — §9.2's Notes column defines the RAM row as
  "ONNX model weights + FAISS index", so that is what is checked.
* **Embedding + search < 150 ms** — measured on the real model, warm.

The *process* working set is measured in a clean subprocess and reported
(stdout + ``record_property``). It is not asserted: it is not what §9.2
defines, and it is materially larger than the weights+index figure — see
``agent/router/README.md`` → "Measured memory" for the numbers and the
open question they raise.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from agent.router.index import RecipeIndex
from agent.router.router import IntentRouter

BUDGET_BYTES = 150_000_000  # 150 MB — §9.2 matcher budget
BUDGET_MS = 150.0  # §9.2 embedding + search

_MEMORY_PROBE = r"""
import ctypes, sys, os
from ctypes import wintypes

class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

def rss():
    ps = ctypes.WinDLL("psapi"); k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = wintypes.HANDLE
    ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    ps.GetProcessMemoryInfo.restype = wintypes.BOOL
    c = PMC(); c.cb = ctypes.sizeof(PMC)
    ps.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.WorkingSetSize

repo, model = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo)
os.chdir(repo)
print("RSS_START", rss())
from agent.router.embedder import OnnxEmbedder
from agent.router.index import RecipeIndex
from agent.router.recipes import load_recipe_metas, index_text
print("RSS_IMPORTED", rss())
emb = OnnxEmbedder(model)
print("RSS_MODEL", rss())
metas, _ = load_recipe_metas("tests/router/fixtures/recipes")
idx = RecipeIndex.build([m.id for m in metas], emb.embed_passages([index_text(m) for m in metas]))
idx_path = os.path.join(os.environ.get("TMPDIR", "."), "karakuri-budget-index.faiss")
idx.save(idx_path)
print("RSS_INDEX", rss())
print("INDEX_BYTES", os.path.getsize(idx_path) + os.path.getsize(idx_path + ".ids.json"))
"""


def test_weights_and_index_stay_within_150_mb(model_path, recipe_index, tmp_path):
    index_path = str(tmp_path / "recipe_index.faiss")
    recipe_index.save(index_path)

    weights = os.path.getsize(model_path)
    index_size = os.path.getsize(index_path) + os.path.getsize(index_path + ".ids.json")
    total = weights + index_size

    print(
        f"\n[matcher budget] model weights {weights:,} B ({weights / 1e6:.1f} MB) "
        f"+ index {index_size:,} B ({index_size / 1e6:.3f} MB) "
        f"= {total:,} B ({total / 1e6:.1f} MB)"
    )
    assert total < BUDGET_BYTES, f"matcher weights+index {total} B exceeds {BUDGET_BYTES} B"


def test_embedding_and_search_stay_under_150_ms(
    embedder, recipe_index, matcher_config, tree_hash, window_title, record_property
):
    from agent.router.telemetry import MemoryTelemetrySink

    router = IntentRouter(
        embedder, recipe_index, matcher_config, MemoryTelemetrySink(), top_k=3
    )
    intents = [
        "弥生会計で仕訳を新規作成して保存する",
        "今日の天気は晴れですか",
        "奉行で経費伝票を登録する",
    ]
    for intent in intents:  # warm-up
        router.route(intent, window_title=window_title, tree_snapshot_hash=tree_hash)

    samples = []
    for _ in range(10):
        for intent in intents:
            started = time.perf_counter()
            router.route(intent, window_title=window_title, tree_snapshot_hash=tree_hash)
            samples.append((time.perf_counter() - started) * 1000.0)

    worst = max(samples)
    average = sum(samples) / len(samples)
    print(
        f"\n[matcher latency] embed+search over {len(samples)} routes: "
        f"avg {average:.2f} ms, worst {worst:.2f} ms (budget {BUDGET_MS:.0f} ms)"
    )
    record_property("matcher_avg_ms", round(average, 3))
    record_property("matcher_worst_ms", round(worst, 3))
    assert worst < BUDGET_MS, f"worst route took {worst:.1f} ms (budget {BUDGET_MS} ms)"


def test_process_working_set_is_measured_in_a_clean_subprocess(
    repo_root, model_path, record_property
):
    """Load the matcher from scratch and read the working set.

    Runs in a subprocess so the numbers are not polluted by the session-scoped
    fixture that has already loaded the same model into this process.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _MEMORY_PROBE, repo_root, model_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        cwd=repo_root,
    )
    assert completed.returncode == 0, completed.stderr
    values = {}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith("RSS_"):
            values[parts[0]] = int(parts[1])
        elif len(parts) == 2 and parts[0] == "INDEX_BYTES":
            values["INDEX_BYTES"] = int(parts[1])

    start = values["RSS_START"]
    with_model = values["RSS_MODEL"]
    with_index = values["RSS_INDEX"]
    delta = (with_index - start) / 1e6
    weights_mb = os.path.getsize(model_path) / 1e6
    index_mb = values["INDEX_BYTES"] / 1e6

    print(
        f"\n[matcher memory, clean subprocess] {start / 1e6:.1f} MB baseline -> "
        f"{with_model / 1e6:.1f} MB with model -> {with_index / 1e6:.1f} MB with index "
        f"(delta {delta:.1f} MB); weights+index on disk {weights_mb + index_mb:.1f} MB"
    )
    record_property("matcher_process_rss_delta_mb", round(delta, 1))
    record_property("matcher_weights_plus_index_mb", round(weights_mb + index_mb, 1))
    assert with_index > start


def test_session_configuration_is_deterministic(embedder):
    assert embedder.intra_op_threads == 1
    assert embedder.providers == ("CPUExecutionProvider",)
    assert embedder.prefix_style == "e5"
    assert embedder.max_seq_len == 128
