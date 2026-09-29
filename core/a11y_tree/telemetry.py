"""Telemetry record construction for pruner events (contracts.md §2, §3.5, §9.5).

The pruner itself stays pure: it returns :class:`PruneEvent` objects and this
module turns them into §2.1-shaped JSONL records. The full telemetry writer is
KARA-11's module; ``append_jsonl`` is the minimal bridge the pruner's own
verification uses so the failure path is demonstrably exercised today.

Status choice: §3.5 and §9.5 mandate an ``error_category`` for pruner events,
and §2.1 only allows a non-null ``error_category`` when ``status`` is ``failure``
or ``fallback_applied``. Pruning does not fail the execution — the tree is served
in a shallower/truncated form — so ``fallback_applied`` follows the §2.2
``matcher_below_threshold`` precedent ("not a failure per se … logged as
status: fallback_applied").
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Iterable, Optional

from .pruner import PruneEvent

VALID_STATUS = ("success", "failure", "fallback_applied", "user_aborted")


def _utc_now() -> str:
    # ISO 8601 UTC with millisecond precision, e.g. 2026-09-29T18:44:43.123Z
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit]


def build_telemetry_records(
    events: Iterable[PruneEvent],
    *,
    tree_snapshot_hash: str,
    execution_mode: str,
    intent: str,
    window_title: str,
    timestamp: Optional[str] = None,
) -> list[dict]:
    """Expand pruner events into §2.1 telemetry records.

    Every common field from §2.1 is always present; pruner events carry
    ``status: "fallback_applied"`` with the pruner's ``error_category``.
    """
    if execution_mode not in ("mode_a", "mode_b"):
        raise ValueError(f"execution_mode must be mode_a|mode_b, got {execution_mode!r}")
    ts = timestamp or _utc_now()
    records: list[dict] = []
    for event in events:
        records.append(
            {
                "timestamp": ts,
                "execution_mode": execution_mode,
                "intent": _truncate(intent, 500),
                "window_title": _truncate(window_title, 200),
                "tree_snapshot_hash": tree_snapshot_hash,
                "llm_output": None,
                "resolved_target": None,
                "status": "fallback_applied",
                "error_category": event.error_category,
                "os_error_code": None,
                "fallback_attempted": True,
                "pruner": event.to_dict(),
            }
        )
    return records


def append_jsonl(path: str, records: Iterable[dict]) -> int:
    """Append records to ``path`` as UTF-8 JSONL. Returns the number written."""
    records = list(records)
    if not records:
        return 0
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(records)
