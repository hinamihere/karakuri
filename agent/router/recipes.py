"""Recipe metadata for the embedding index.

Scope-limited on purpose: this reads **only** the three fields the matcher
needs — ``id``, ``name``, ``description`` — from ``contracts.md §1.1``.
Schema validation of ``steps``, ``target_app``, selectors and template vars
belongs to the recipe engine (KARA-11); duplicating it here would create two
authoritative validators for one frozen schema.

``description`` is "additional embedding context for the matcher" per §1.1,
so the indexed text is ``name`` + ``description`` when a description exists
and ``name`` alone otherwise. Without the name, a recipe whose ``description``
happens to be empty would be invisible to the matcher.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

RECIPE_EXTENSIONS = (".yaml", ".yml")


class RecipeMetaError(RuntimeError):
    """A recipe file could not be read as metadata.

    ``error_category`` mirrors contracts.md §2.2: ``recipe_invalid`` when the
    file is not a usable recipe at all.
    """

    def __init__(self, message: str, error_category: str = "recipe_invalid") -> None:
        super().__init__(message)
        self.error_category = error_category


@dataclass(frozen=True)
class RecipeMeta:
    """The subset of a recipe the matcher indexes."""

    id: str
    name: str
    description: str = ""
    source_path: str = ""

    @property
    def embedding_text(self) -> str:
        return index_text(self)


def index_text(meta: RecipeMeta) -> str:
    """Text that gets embedded for this recipe (see module docstring)."""
    description = (meta.description or "").strip()
    name = (meta.name or "").strip()
    if description and name:
        return f"{name}\n{description}"
    return description or name


def _load_yaml(path: str) -> object:
    try:
        import yaml  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment specific
        raise RecipeMetaError(
            "the `pyyaml` package is required to read recipes "
            f"(pip/uv install pyyaml): {exc}"
        ) from exc
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except FileNotFoundError as exc:
        raise RecipeMetaError(f"recipe file disappeared while reading: {path}") from exc
    except OSError as exc:
        raise RecipeMetaError(f"recipe file unreadable: {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RecipeMetaError(f"recipe is not valid YAML: {path}: {exc}") from exc


def load_recipe_meta(path: str) -> RecipeMeta:
    """Read one recipe's ``id`` / ``name`` / ``description``."""
    data = _load_yaml(path)
    if not isinstance(data, dict):
        raise RecipeMetaError(f"recipe root must be a mapping: {path}")
    recipe_id = data.get("id")
    name = data.get("name")
    if not isinstance(recipe_id, str) or not recipe_id.strip():
        raise RecipeMetaError(f"recipe has no `id`: {path}")
    if not isinstance(name, str) or not name.strip():
        raise RecipeMetaError(f"recipe {recipe_id!r} has no `name`: {path}")
    description = data.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise RecipeMetaError(
            f"recipe {recipe_id!r} has a non-string `description`: {path}"
        )
    return RecipeMeta(
        id=recipe_id.strip(),
        name=name.strip(),
        description=description.strip(),
        source_path=path,
    )


def iter_recipe_paths(recipe_dir: str) -> list[str]:
    """Recipe files in ``recipe_dir``, sorted for a stable iteration order."""
    if not os.path.isdir(recipe_dir):
        return []
    paths = []
    for entry in os.listdir(recipe_dir):
        if entry.lower().endswith(RECIPE_EXTENSIONS):
            full = os.path.join(recipe_dir, entry)
            if os.path.isfile(full):
                paths.append(full)
    paths.sort(key=lambda p: os.path.basename(p).lower())
    return paths


def load_recipe_metas(recipe_dir: str) -> tuple[list[RecipeMeta], list[RecipeMetaError]]:
    """Load every readable recipe's metadata.

    Returns ``(metas, problems)``: unreadable or id-less files are collected
    as problems instead of aborting the index build, so one broken recipe
    cannot stop the matcher from seeing the rest. Problems carry
    ``error_category: recipe_invalid`` so the caller can log them.
    """
    metas: list[RecipeMeta] = []
    problems: list[RecipeMetaError] = []
    seen: dict[str, str] = {}
    for path in iter_recipe_paths(recipe_dir):
        try:
            meta = load_recipe_meta(path)
        except RecipeMetaError as exc:
            problems.append(exc)
            continue
        if meta.id in seen:
            problems.append(
                RecipeMetaError(
                    f"duplicate recipe id {meta.id!r}: {path} ignored, "
                    f"first seen at {seen[meta.id]}"
                )
            )
            continue
        seen[meta.id] = path
        metas.append(meta)
    metas.sort(key=lambda m: (m.id, os.path.basename(m.source_path)))
    return metas, problems


