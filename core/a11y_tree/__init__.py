"""A11y tree pruner and compact YAML serializer (module map: ``core/a11y_tree``).

Public surface::

    from core.a11y_tree import RawNode, PruneLimits, build_compact_tree

    result = build_compact_tree(raw_tree)
    result.yaml                    # compact YAML for the LLM (§3)
    result.tree_snapshot_hash      # SHA-256 hex, stable across runs (§2.1)
    result.token_count             # cl100k_base tokens (§9.1)
    result.events                  # pruner telemetry triggers (§3.5, §9.5)

Everything here is deterministic: no wall-clock reads, no random ordering, no
network. The only third-party library involved is ``tiktoken`` (cl100k_base
vocabulary for the §9.1 token budget); when it is missing the pipeline falls
back to a conservative local estimator that never under-counts.
"""

from .model import PrunedNode, RawNode, Rect
from .pipeline import CompactTreeResult, build_compact_tree, snapshot_hash
from .pruner import (
    BUDGET_EXCEEDED,
    DEPTH_CUT,
    PruneEvent,
    PruneLimits,
    assign_temp_ids,
    count_nodes,
    prune_once,
)
from .taxonomy import normalize_role
from .telemetry import append_jsonl, build_telemetry_records
from .tokens import count_tokens, within_budget
from .utf16 import (
    MAX_NAME_UTF16_UNITS,
    MAX_VALUE_UTF16_UNITS,
    coerce_text,
    repair_lone_surrogates,
    utf16_len,
    utf16_truncate,
)
from .yaml_writer import emit_yaml, format_scalar

__all__ = [
    "BUDGET_EXCEEDED",
    "DEPTH_CUT",
    "MAX_NAME_UTF16_UNITS",
    "MAX_VALUE_UTF16_UNITS",
    "CompactTreeResult",
    "PruneEvent",
    "PruneLimits",
    "PrunedNode",
    "RawNode",
    "Rect",
    "append_jsonl",
    "assign_temp_ids",
    "build_compact_tree",
    "build_telemetry_records",
    "coerce_text",
    "count_nodes",
    "count_tokens",
    "emit_yaml",
    "format_scalar",
    "normalize_role",
    "prune_once",
    "repair_lone_surrogates",
    "snapshot_hash",
    "utf16_len",
    "utf16_truncate",
    "within_budget",
]
