"""Mode A / Mode B intent router (contracts.md §6.1).

Implements the frozen routing pseudocode::

    embedding = matcher.embed(intent)
    candidates = index.similarity_search(embedding, top_k=3)
    best = candidates[0]
    if best.similarity >= config.similarity_threshold (0.82):
        -> Mode A (deterministic recipe replay, 0 LLM tokens, 0 network calls)
    else:
        -> Mode B (guarded live planning)

The router never opens a socket and never imports an HTTP client: the only
side effect of :meth:`IntentRouter.route` besides computing the decision is
appending local telemetry events for the two routing-stage categories the
contract defines (``matcher_below_threshold``, ``matcher_index_missing``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from agent.router.config import MatcherConfig
from agent.router.embedder import OnnxEmbedder
from agent.router.index import IndexLoadError, RecipeIndex
from agent.router.recipes import load_recipe_metas, index_text
from agent.router.telemetry import (
    ExecutionStatus,
    TelemetrySink,
    append_all,
    build_event,
)

MODE_A = "mode_a"
MODE_B = "mode_b"

# contracts.md §6.1: similarity_search(embedding, top_k=3)
TOP_K = 3

# contracts.md §6.1 / §5.3 — the frozen Mode A / Mode B boundary.
DEFAULT_THRESHOLD = 0.82


@dataclass(frozen=True)
class Candidate:
    """One index hit: a recipe id and its cosine similarity to the intent."""

    recipe_id: str
    similarity: float


@dataclass(frozen=True)
class RouteResult:
    """The routing decision plus the telemetry events it produced."""

    mode: str
    intent: str
    threshold: float
    similarity: float | None
    recipe_id: str | None
    candidates: tuple[Candidate, ...] = ()
    telemetry_events: tuple[dict, ...] = field(default_factory=tuple)

    @property
    def is_mode_a(self) -> bool:
        return self.mode == MODE_A

    @property
    def is_mode_b(self) -> bool:
        return self.mode == MODE_B


class IntentRouter:
    """Embeds the intent, searches the recipe index and routes.

    Parameters
    ----------
    embedder:
        A ready :class:`~agent.router.embedder.OnnxEmbedder` (or any object
        exposing ``embed_query(text)``), so tests can inject a stub.
    index:
        A :class:`~agent.router.index.RecipeIndex`. An empty index is legal
        and routes everything to Mode B with a ``matcher_index_missing``
        event, per contracts.md §5.2.
    config:
        The validated :class:`~agent.router.config.MatcherConfig` supplying
        ``similarity_threshold``.
    telemetry:
        Where routing-stage events go. Defaults to
        :class:`~agent.router.telemetry.JsonlTelemetrySink` writing
        ``logs/telemetry.jsonl`` (contracts.md §2).
    clock:
        Injectable timestamp factory for deterministic tests. Defaults to the
        real UTC clock, which §2.1 requires for production events.
    """

    def __init__(
        self,
        embedder: OnnxEmbedder,
        index: RecipeIndex,
        config: MatcherConfig,
        telemetry: TelemetrySink | None = None,
        *,
        clock: Callable[[], str] | None = None,
        top_k: int = TOP_K,
    ) -> None:
        if embedder.dim != index.dim:
            raise ValueError(
                f"embedder dim {embedder.dim} does not match index dim {index.dim}"
            )
        self._embedder = embedder
        self._index = index
        self._config = config
        self._top_k = int(top_k)
        self._clock = clock
        if telemetry is None:
            from agent.router.telemetry import JsonlTelemetrySink  # noqa: PLC0415

            telemetry = JsonlTelemetrySink()
        self._telemetry = telemetry

    # ------------------------------------------------------------------
    @property
    def index(self) -> RecipeIndex:
        return self._index

    @property
    def threshold(self) -> float:
        return self._config.similarity_threshold

    def replace_index(self, index: RecipeIndex) -> None:
        """Swap in a freshly built index (after a Mode B recipe compile)."""
        if index.dim != self._embedder.dim:
            raise ValueError(
                f"embedder dim {self._embedder.dim} does not match index dim {index.dim}"
            )
        self._index = index

    # ------------------------------------------------------------------
    def _event(self, *, execution_mode, intent, window_title, tree_snapshot_hash,
               status, error_category, fallback_attempted) -> dict:
        kwargs = {}
        if self._clock is not None:
            kwargs["timestamp"] = self._clock()
        return build_event(
            execution_mode=execution_mode,
            intent=intent,
            window_title=window_title,
            tree_snapshot_hash=tree_snapshot_hash,
            status=status,
            error_category=error_category,
            os_error_code=None,
            fallback_attempted=fallback_attempted,
            llm_output=None,
            resolved_target=None,
            **kwargs,
        )

    def route(
        self,
        intent: str,
        *,
        window_title: str,
        tree_snapshot_hash: str,
    ) -> RouteResult:
        """Route one intent. Never touches the network.

        Raises whatever the embedder raises — a matcher that cannot run is a
        real failure, not something to silently swallow (AGENTS.md,
        "Failure is data").
        """
        events: list[dict] = []

        query = self._embedder.embed_query(intent)
        candidates = tuple(
            Candidate(recipe_id=recipe_id, similarity=similarity)
            for recipe_id, similarity in self._index.search(query, self._top_k)
        )

        if not candidates:
            # contracts.md §5.2: empty/absent index -> Mode B with a
            # matcher_index_missing event, status fallback_applied.
            events.append(
                self._event(
                    execution_mode=MODE_B,
                    intent=intent,
                    window_title=window_title,
                    tree_snapshot_hash=tree_snapshot_hash,
                    status=ExecutionStatus.FALLBACK_APPLIED,
                    error_category="matcher_index_missing",
                    fallback_attempted=True,
                )
            )
            result = RouteResult(
                mode=MODE_B,
                intent=intent,
                threshold=self.threshold,
                similarity=None,
                recipe_id=None,
                candidates=candidates,
                telemetry_events=tuple(events),
            )
            append_all(self._telemetry, events)
            return result

        best = candidates[0]
        if best.similarity >= self.threshold:
            return RouteResult(
                mode=MODE_A,
                intent=intent,
                threshold=self.threshold,
                similarity=best.similarity,
                recipe_id=best.recipe_id,
                candidates=candidates,
                telemetry_events=(),
            )

        # contracts.md §2.2 matcher_below_threshold: the normal gateway to
        # Mode B -> status fallback_applied, fallback_attempted true.
        events.append(
            self._event(
                execution_mode=MODE_B,
                intent=intent,
                window_title=window_title,
                tree_snapshot_hash=tree_snapshot_hash,
                status=ExecutionStatus.FALLBACK_APPLIED,
                error_category="matcher_below_threshold",
                fallback_attempted=True,
            )
        )
        append_all(self._telemetry, events)
        return RouteResult(
            mode=MODE_B,
            intent=intent,
            threshold=self.threshold,
            similarity=best.similarity,
            recipe_id=None,
            candidates=candidates,
            telemetry_events=tuple(events),
        )

    # ------------------------------------------------------------------
    def build_index(self, recipe_dir: str | None = None) -> RecipeIndex:
        """Embed every recipe in ``recipe_dir`` and return a fresh index.

        Deterministic: recipe files are read in sorted order and the index
        rows follow the sorted recipe ids, so rebuilding an unchanged recipe
        directory always produces an identical index.
        """
        from agent.router.index import RecipeIndex as _RecipeIndex  # noqa: PLC0415

        directory = recipe_dir if recipe_dir is not None else self._config.recipe_dir
        metas, problems = load_recipe_metas(directory)
        if problems:
            # Surfaced, not swallowed: the caller logs them as recipe_invalid.
            self._recipe_problems = problems
        if not metas:
            raise IndexLoadError(
                f"no indexable recipes found in {directory!r} — the matcher needs "
                "at least one recipe with `id` and `name`"
            )
        vectors = self._embedder.embed_passages([index_text(m) for m in metas])
        return _RecipeIndex.build([m.id for m in metas], vectors)

    @property
    def recipe_problems(self) -> Sequence[object]:
        """Problems seen by the last :meth:`build_index` call."""
        return tuple(getattr(self, "_recipe_problems", ()))

    def save_index(self, index: RecipeIndex, path: str | None = None) -> str:
        target = path or self._config.recipe_index_path
        index.save(target)
        return target

    @classmethod
    def load_index(
        cls,
        path: str,
        dim: int,
    ) -> RecipeIndex:
        """Load the index or return an empty one — never raises.

        Any load failure (missing file, corrupt file, dimension drift after a
        model swap) becomes an empty index so startup still succeeds; the
        caller emits ``matcher_index_missing`` on the first execution that
        needs it, exactly as contracts.md §5.2 specifies.
        """
        try:
            return RecipeIndex.load(path, dim)
        except IndexLoadError:
            return RecipeIndex.empty(dim)
