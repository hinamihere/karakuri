"""Real-window acceptance for KARA-6 (issue done-criteria).

Two runs of the same live window must serialize to the same
``tree_snapshot_hash``, and the result must sit under the §9.1 ceiling.

Skipped automatically when pywinauto is not installed or when no top-level
window can be enumerated (headless / no interactive session).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

pywinauto = pytest.importorskip("pywinauto", reason="pywinauto not installed (verify extra)")

from core.a11y_tree import PruneLimits, build_compact_tree  # noqa: E402
from dump_real_window import candidate_windows, dump_window  # noqa: E402


def _first_window():
    try:
        from pywinauto import Desktop

        windows = Desktop(backend="uia").windows()
    except Exception as exc:  # no UI session
        pytest.skip(f"cannot enumerate windows: {exc}")
    if not windows:
        pytest.skip("no top-level windows available")
    return windows[0]


def _dump(window):
    from pywinauto import Desktop  # noqa: F401

    return dump_window(window, max_depth=16, max_nodes=4000)


def test_a_real_window_serializes_within_budget():
    window = _first_window()
    raw, _ = _dump(window)
    result = build_compact_tree(raw, limits=PruneLimits(max_tokens=500))
    assert result.token_count <= 500, "§9.1 ceiling"
    assert result.node_count >= 1
    assert result.yaml.startswith("tree:")
    assert len(result.tree_snapshot_hash) == 64


def test_two_runs_of_the_same_window_produce_the_same_hash():
    window = _first_window()
    first = build_compact_tree(_dump(window)[0])
    second = build_compact_tree(_dump(window)[0])
    assert first.yaml == second.yaml
    assert first.tree_snapshot_hash == second.tree_snapshot_hash
    assert first.token_count == second.token_count
    assert first.node_count == second.node_count


def test_window_enumeration_helper_is_usable():
    windows = candidate_windows()
    assert isinstance(windows, list)
    for entry in windows[:3]:
        assert set(entry) == {"pid", "control_type", "name", "handle"}
