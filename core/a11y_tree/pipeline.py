"""End-to-end pruner pipeline: raw tree → compact YAML → tree_snapshot_hash.

This is the single entry point the OS adapter / orchestrator calls.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from .model import PrunedNode, RawNode
from .pruner import BUDGET_EXCEEDED, PruneEvent, PruneLimits, prune_once
from .tokens import count_tokens
from .yaml_writer import emit_yaml


@dataclass(frozen=True)
class CompactTreeResult:
    yaml: str
    tree_snapshot_hash: str
    token_count: int
    token_backend: str
    node_count: int
    effective_max_depth: int
    events: tuple[PruneEvent, ...] = field(default_factory=tuple)

    @property
    def within_ceiling(self) -> bool:
        return self.token_count <= 500

    def telemetry_events(self) -> list[PruneEvent]:
        return list(self.events)


def snapshot_hash(yaml_text: str) -> str:
    """SHA-256 of the serialized YAML, hex, 64 chars (contracts.md §2.1).

    The hash is over the UTF-8 bytes of exactly what the LLM would receive, so
    Mode A and Mode B agree on ``tree_snapshot_hash``.
    """
    return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()


def build_compact_tree(
    raw: RawNode,
    *,
    limits: Optional[PruneLimits] = None,
    token_backend: str = "auto",
) -> CompactTreeResult:
    """Prune, serialize, hash — enforcing the §9.1 token ceiling.

    If the tree is still over ``limits.max_tokens`` at the contracted depth 8,
    the depth limit is reduced one level at a time (§9.5 "applies additional
    depth limiting … until the budget is met"). Events are collected from the
    final pass only, so a tightening retry never duplicates telemetry.
    """
    limits = limits or PruneLimits()
    depth = limits.max_depth
    while True:
        root, events = prune_once(raw, limits, max_depth=depth)
        text = emit_yaml(root)
        tokens, backend = count_tokens(text, backend=token_backend)
        if tokens <= limits.max_tokens or depth <= limits.min_budget_depth:
            break
        depth -= 1

    if tokens > limits.max_tokens:
        events.append(
            PruneEvent(
                error_category=BUDGET_EXCEEDED,
                detail=(
                    f"tree still {tokens} tokens after depth limiting to "
                    f"{depth} (limit {limits.max_tokens})"
                ),
                depth=depth,
            )
        )

    return CompactTreeResult(
        yaml=text,
        tree_snapshot_hash=snapshot_hash(text),
        token_count=tokens,
        token_backend=backend,
        node_count=_count(root),
        effective_max_depth=depth,
        events=tuple(events),
    )


def _count(node: PrunedNode) -> int:
    return 1 + sum(_count(child) for child in node.children)
