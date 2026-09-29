#!/usr/bin/env python
"""Real-window verification harness for the KARA-6 pruner (contracts.md §3, §9.1).

Dumps a live top-level window through the UIA tree, feeds it to
``build_compact_tree``, and proves the two acceptance properties:

1. the serialized tree sits inside the 200–500 token budget, and
2. independent dumps of the same window produce the same ``tree_snapshot_hash``.

This is a *verification* harness, not production code: it uses pywinauto to get
a tree today. The shipping path is the UIA OS Adapter from KARA-5
(``core/platform/windows``), which feeds the same ``RawNode`` shape.

Usage::

    .venv/Scripts/python.exe scripts/dump_real_window.py --list
    .venv/Scripts/python.exe scripts/dump_real_window.py --title-regex "弥生" --runs 3
    .venv/Scripts/python.exe scripts/dump_real_window.py --pid 1220 --json-out out.json

Exit status: 0 when every run produced the same hash and the ceiling held,
1 otherwise (so it can be used as an acceptance gate).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.a11y_tree import (  # noqa: E402
    PruneLimits,
    RawNode,
    Rect,
    build_compact_tree,
    build_telemetry_records,
    append_jsonl,
)
from core.a11y_tree.taxonomy import carries_selection, carries_value  # noqa: E402

DEFAULT_RAW_DEPTH = 16
DEFAULT_MAX_NODES = 4000


def candidate_windows() -> list[dict]:
    from pywinauto import Desktop

    out = []
    for window in Desktop(backend="uia").windows():
        try:
            info = window.element_info
        except Exception:
            continue
        out.append(
            {
                "pid": info.process_id,
                "control_type": info.control_type,
                "name": info.name,
                "handle": int(info.handle or 0),
            }
        )
    return out


def _get_pattern(info, pattern_name: str):
    """Return a UIA pattern interface for ``info``, or None when it is absent.

    pywinauto's ``uia_defines.get_elem_interface`` expects an object exposing
    ``GetCurrentPattern``; in pywinauto 0.6.9 that lives on the raw COM element
    (``info.element``) rather than on ``UIAElementInfo``, so the query is done
    against the element directly.
    """
    from pywinauto.uia_defines import pattern_ids

    pattern_id, interface = pattern_ids[pattern_name]
    element = getattr(info, "element", info)
    try:
        return element.GetCurrentPattern(pattern_id).QueryInterface(interface)
    except Exception:
        return None


def _read_value(info) -> Optional[str]:
    pattern = _get_pattern(info, "Value")
    if pattern is None:
        return None
    for attribute in ("CurrentValue", "Value"):
        try:
            value = getattr(pattern, attribute)
            if callable(value):
                value = value()
            return "" if value is None else str(value)
        except Exception:
            continue
    return None


def _read_selection(info, control_type: str) -> Optional[bool]:
    lowered = control_type.lower()
    if "check" in lowered or "toggle" in lowered:
        toggle = _get_pattern(info, "Toggle")
        if toggle is None:
            return None
        try:
            return bool(toggle.CurrentToggleState == 1)
        except Exception:
            return None
    selection = _get_pattern(info, "SelectionItem")
    if selection is None:
        return None
    try:
        return bool(selection.CurrentIsSelected)
    except Exception:
        return None


def dump_window(
    window,
    *,
    max_depth: int = DEFAULT_RAW_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> tuple[RawNode, dict]:
    """Walk a live window into a ``RawNode`` tree.

    Value/selection patterns are only queried for control types that carry them
    (§3.2), so the walk stays cheap — this is a harness, not the batched
    CacheRequest path KARA-5 owns.
    """
    stats = {"raw_nodes": 0, "truncated": False, "seconds": 0.0}
    started = time.perf_counter()
    info = window.element_info

    def walk(node_info, depth: int) -> RawNode:
        stats["raw_nodes"] += 1
        control_type = node_info.control_type or ""
        node = RawNode(
            control_type=control_type,
            name=node_info.name or "",
            automation_id=node_info.automation_id or "",
            is_enabled=bool(node_info.enabled),
            bounding_rect=Rect.from_value(node_info.rectangle),
        )
        if carries_value(control_type):
            node.value = _read_value(node_info)
        if carries_selection(control_type):
            node.is_selected = _read_selection(node_info, control_type)
        if depth >= max_depth:
            return node
        if stats["raw_nodes"] >= max_nodes:
            stats["truncated"] = True
            return node
        children = node_info.children
        if callable(children):
            children = children()
        for child in children:
            if stats["raw_nodes"] >= max_nodes:
                stats["truncated"] = True
                break
            node.children.append(walk(child, depth + 1))
        return node

    root = walk(info, 1)
    stats["seconds"] = round(time.perf_counter() - started, 3)
    return root, stats


def find_window(args) -> object:
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    if args.pid:
        for window in desktop.windows():
            try:
                if window.element_info.process_id == args.pid:
                    return window
            except Exception:
                continue
        raise SystemExit(f"no top-level window found for pid {args.pid}")
    if args.title_regex:
        import re

        pattern = re.compile(args.title_regex, re.IGNORECASE)
        for window in desktop.windows():
            try:
                title = window.element_info.name or ""
            except Exception:
                continue
            if pattern.search(title):
                return window
        raise SystemExit(f"no top-level window matches /{args.title_regex}/")
    if args.handle:
        for window in desktop.windows():
            try:
                if int(window.element_info.handle or 0) == args.handle:
                    return window
            except Exception:
                continue
        raise SystemExit(f"no top-level window with handle {args.handle:#x}")
    raise SystemExit("select a window with --pid, --handle or --title-regex (see --list)")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="list top-level windows and exit")
    parser.add_argument("--pid", type=int, help="target window by process id")
    parser.add_argument("--handle", type=int, help="target window by HWND (decimal)")
    parser.add_argument("--title-regex", help="target window by title regex")
    parser.add_argument("--runs", type=int, default=2, help="independent dumps to compare (default 2)")
    parser.add_argument("--raw-depth", type=int, default=DEFAULT_RAW_DEPTH)
    parser.add_argument("--max-nodes", type=int, default=DEFAULT_MAX_NODES)
    parser.add_argument("--max-depth", type=int, default=8, help="pruner depth limit (§3.5)")
    parser.add_argument("--max-breadth", type=int, default=40, help="pruner breadth limit (§3.5)")
    parser.add_argument("--max-tokens", type=int, default=500, help="token ceiling (§9.1)")
    parser.add_argument("--token-backend", default="auto", choices=("auto", "tiktoken", "approx"))
    parser.add_argument("--print-yaml", action="store_true", help="print the serialized tree")
    parser.add_argument("--json-out", help="write raw tree + per-run results to this JSON file")
    parser.add_argument("--telemetry", help="append pruner telemetry events to this JSONL file")
    args = parser.parse_args(argv)

    if args.list:
        for index, entry in enumerate(candidate_windows()):
            name = (entry["name"] or "").replace("\n", " ")[:80]
            print(f"[{index:2d}] pid={entry['pid']:<6} ct={entry['control_type']:<10} {name}")
        return 0

    window = find_window(args)
    title = window.element_info.name or ""
    print(f"target: {title!r} (pid={window.element_info.process_id})")

    limits = PruneLimits(
        max_depth=args.max_depth,
        max_breadth=args.max_breadth,
        max_tokens=args.max_tokens,
    )

    results = []
    raw_first = None
    for run in range(1, args.runs + 1):
        raw, stats = dump_window(window, max_depth=args.raw_depth, max_nodes=args.max_nodes)
        if raw_first is None:
            raw_first = raw
        result = build_compact_tree(raw, limits=limits, token_backend=args.token_backend)
        results.append(result)
        print(
            f"run {run}: raw_nodes={stats['raw_nodes']} kept={result.node_count} "
            f"tokens={result.token_count} ({result.token_backend}) "
            f"depth_used={result.effective_max_depth} "
            f"hash={result.tree_snapshot_hash} dump={stats['seconds']}s"
        )
        for event in result.events:
            print(f"  telemetry: {event.error_category}: {event.detail}")

    hashes = {result.tree_snapshot_hash for result in results}
    stable = len(hashes) == 1
    ceiling_ok = all(result.token_count <= args.max_tokens for result in results)
    print(f"hash stable across {args.runs} runs: {'YES' if stable else 'NO'}")
    print(f"token ceiling <= {args.max_tokens}: {'YES' if ceiling_ok else 'NO'}")

    if args.print_yaml:
        print("---")
        print(results[0].yaml, end="")

    if args.telemetry:
        records = []
        for result in results:
            records.extend(
                build_telemetry_records(
                    result.events,
                    tree_snapshot_hash=result.tree_snapshot_hash,
                    execution_mode="mode_b",
                    intent="KARA-6 verification dump",
                    window_title=title,
                )
            )
        written = append_jsonl(args.telemetry, records)
        print(f"telemetry records appended: {written} -> {args.telemetry}")

    if args.json_out:
        payload = {
            "window_title": title,
            "pid": window.element_info.process_id,
            "raw_tree": raw_first.to_dict() if raw_first else None,
            "runs": [
                {
                    "hash": r.tree_snapshot_hash,
                    "tokens": r.token_count,
                    "token_backend": r.token_backend,
                    "nodes": r.node_count,
                    "effective_max_depth": r.effective_max_depth,
                    "events": [e.to_dict() for e in r.events],
                }
                for r in results
            ],
            "yaml": results[0].yaml,
        }
        with open(args.json_out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        print(f"wrote {args.json_out}")

    return 0 if (stable and ceiling_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
