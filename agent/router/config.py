"""``config.toml`` loader for the matcher (contracts.md §5.2, §5.3, §5.5).

Reads only the keys this module needs:

* ``[app] recipe_dir`` — where recipe YAML lives (default ``recipes``)
* ``[app] recipe_index_path`` — on-disk embedding index
  (default ``models/recipe_index.faiss``)
* ``[matcher] onnx_model_path`` — **required**, no default
* ``[matcher] similarity_threshold`` — default ``0.82``, clamped to ``[0, 1]``

Unknown keys inside those two sections are ignored with a
``config_unknown_key`` warning (§5.5). Sections this module does not use
(``[llm]``) are not inspected here — the LLM client owns them.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from typing import Mapping

DEFAULT_SIMILARITY_THRESHOLD = 0.82
DEFAULT_RECIPE_DIR = "recipes"
DEFAULT_RECIPE_INDEX_PATH = "models/recipe_index.faiss"

KNOWN_APP_KEYS = frozenset({"language", "hotkey", "recipe_dir", "recipe_index_path"})
KNOWN_MATCHER_KEYS = frozenset({"onnx_model_path", "similarity_threshold"})


class MatcherConfigError(RuntimeError):
    """Fatal configuration failure.

    ``error_category`` carries the contracts.md §5 category so the caller can
    log it. ``None`` means the contract defines no category for this failure
    (see ``agent/router/README.md`` → "Known contract gaps").
    """

    def __init__(self, message: str, error_category: str | None = None) -> None:
        super().__init__(message)
        self.error_category = error_category


@dataclass(frozen=True)
class ConfigWarning:
    """A non-fatal §5.5 warning, surfaced so the caller can log it once."""

    error_category: str | None
    message: str


@dataclass(frozen=True)
class MatcherConfig:
    """Validated matcher settings."""

    onnx_model_path: str
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    recipe_dir: str = DEFAULT_RECIPE_DIR
    recipe_index_path: str = DEFAULT_RECIPE_INDEX_PATH
    tokenizer_path: str | None = None
    config_path: str | None = None
    warnings: tuple[ConfigWarning, ...] = field(default_factory=tuple)

    @property
    def threshold(self) -> float:
        """Alias kept short for the hot routing path."""
        return self.similarity_threshold


def _read_toml(path: str) -> Mapping[str, Mapping[str, object]]:
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise MatcherConfigError(
            f"config file not found: {path} — [matcher].onnx_model_path is required "
            "(contracts.md §5.5)",
            error_category="config_onnx_model_missing",
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise MatcherConfigError(
            f"config file is not valid TOML: {path}: {exc}",
            error_category=None,
        ) from exc
    if not isinstance(data, dict):
        raise MatcherConfigError(f"config root must be a table: {path}", error_category=None)
    return data


def _section(data: Mapping[str, Mapping[str, object]], name: str) -> Mapping[str, object]:
    section = data.get(name, {})
    if section is None:
        return {}
    if not isinstance(section, Mapping):
        raise MatcherConfigError(
            f"config section [{name}] must be a table", error_category=None
        )
    return section


def _unknown_key_warnings(
    section_name: str, section: Mapping[str, object], known: frozenset[str]
) -> list[ConfigWarning]:
    warnings = []
    for key in sorted(section):
        if key not in known:
            warnings.append(
                ConfigWarning(
                    error_category="config_unknown_key",
                    message=f"unknown config key [{section_name}] {key} ignored",
                )
            )
    return warnings


def _as_float(section_name: str, key: str, raw: object) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise MatcherConfigError(
            f"[{section_name}] {key} must be a number (got {raw!r})",
            error_category=None,
        )
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise MatcherConfigError(
            f"[{section_name}] {key} must be a number (got {raw!r})",
            error_category=None,
        ) from exc


def _resolve_tokenizer_path(onnx_model_path: str, explicit: str | None) -> str | None:
    """``tokenizer.json`` next to the ONNX weights, if it exists."""
    if explicit:
        return explicit
    candidate = os.path.join(os.path.dirname(os.path.abspath(onnx_model_path)), "tokenizer.json")
    return candidate if os.path.exists(candidate) else None


def load_matcher_config(
    path: str | os.PathLike[str] = "config.toml",
    *,
    require_model_file: bool = True,
) -> MatcherConfig:
    """Load and validate the matcher's share of ``config.toml``.

    Raises :class:`MatcherConfigError` for the fatal §5.3/§5.5 cases:

    * ``[matcher]`` missing or ``onnx_model_path`` absent/empty →
      ``config_onnx_model_missing``
    * the referenced model file does not exist → ``config_onnx_model_missing``
    * a non-numeric ``similarity_threshold`` → no category (contract gap)

    Out-of-range thresholds are clamped to ``[0, 1]`` with a warning, exactly
    as §5.3 requires — they are not an error.
    """
    path = str(path)
    data = _read_toml(path)
    app = _section(data, "app")
    matcher = _section(data, "matcher")

    warnings: list[ConfigWarning] = []
    warnings += _unknown_key_warnings("app", app, KNOWN_APP_KEYS)
    warnings += _unknown_key_warnings("matcher", matcher, KNOWN_MATCHER_KEYS)

    raw_model = matcher.get("onnx_model_path")
    if isinstance(raw_model, str):
        onnx_model_path = raw_model.strip()
    elif raw_model is None:
        onnx_model_path = ""
    else:
        raise MatcherConfigError(
            f"[matcher] onnx_model_path must be a string (got {raw_model!r})",
            error_category="config_onnx_model_missing",
        )
    if not onnx_model_path:
        raise MatcherConfigError(
            "[matcher] onnx_model_path is required and has no default "
            "(contracts.md §5.3)",
            error_category="config_onnx_model_missing",
        )
    if require_model_file and not os.path.exists(onnx_model_path):
        raise MatcherConfigError(
            f"[matcher] onnx_model_path does not exist: {onnx_model_path}",
            error_category="config_onnx_model_missing",
        )

    threshold = DEFAULT_SIMILARITY_THRESHOLD
    if "similarity_threshold" in matcher:
        threshold = _as_float("matcher", "similarity_threshold", matcher["similarity_threshold"])
        if not 0.0 <= threshold <= 1.0:
            warnings.append(
                ConfigWarning(
                    error_category=None,
                    message=(
                        f"[matcher] similarity_threshold {threshold} outside 0.0–1.0 "
                        f"clamped to {min(max(threshold, 0.0), 1.0)}"
                    ),
                )
            )
            threshold = min(max(threshold, 0.0), 1.0)

    recipe_dir = app.get("recipe_dir", DEFAULT_RECIPE_DIR)
    if not isinstance(recipe_dir, str):
        raise MatcherConfigError(
            f"[app] recipe_dir must be a string (got {recipe_dir!r})",
            error_category=None,
        )
    recipe_index_path = app.get("recipe_index_path", DEFAULT_RECIPE_INDEX_PATH)
    if not isinstance(recipe_index_path, str):
        raise MatcherConfigError(
            f"[app] recipe_index_path must be a string (got {recipe_index_path!r})",
            error_category=None,
        )

    return MatcherConfig(
        onnx_model_path=onnx_model_path,
        similarity_threshold=threshold,
        recipe_dir=recipe_dir,
        recipe_index_path=recipe_index_path,
        tokenizer_path=_resolve_tokenizer_path(onnx_model_path, None),
        config_path=path,
        warnings=tuple(warnings),
    )
