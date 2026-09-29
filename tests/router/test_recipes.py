"""Recipe metadata loading — the matcher's read-only view of recipes."""

from __future__ import annotations

import os

import pytest

from agent.router.recipes import (
    RecipeMetaError,
    index_text,
    load_recipe_meta,
    load_recipe_metas,
)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "recipes")


def _write(directory, filename, body):
    path = os.path.join(str(directory), filename)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def test_fixture_recipes_all_load():
    metas, problems = load_recipe_metas(FIXTURES)
    assert problems == []
    assert [m.id for m in metas] == [
        "kara-bugyo-expense-register",
        "kara-sap-gui-post-voucher",
        "kara-yayoi-invoice-print",
        "kara-yayoi-journal-new",
    ]
    assert all(m.description for m in metas)


def test_ids_are_sorted_for_a_stable_index_order():
    first, _ = load_recipe_metas(FIXTURES)
    second, _ = load_recipe_metas(FIXTURES)
    assert [m.id for m in first] == [m.id for m in second]
    assert [m.id for m in first] == sorted(m.id for m in first)


def test_index_text_prefers_name_plus_description():
    metas, _ = load_recipe_metas(FIXTURES)
    meta = metas[0]
    text = index_text(meta)
    assert text == f"{meta.name}\n{meta.description}"


def test_index_text_falls_back_to_name_without_description(tmp_path):
    path = _write(
        tmp_path,
        "a.yaml",
        'version: 1\nid: kara-a\nname: "レシピ A"\ntarget_app:\n  process_name: "x"\n'
        "steps:\n  - action: finish\n",
    )
    meta = load_recipe_meta(path)
    assert meta.description == ""
    assert index_text(meta) == meta.name


def test_missing_id_is_reported_not_raised(tmp_path):
    _write(tmp_path, "bad.yaml", 'version: 1\nname: "id なし"\n')
    _write(tmp_path, "good.yaml", 'version: 1\nid: kara-good\nname: "OK"\n')
    metas, problems = load_recipe_metas(str(tmp_path))
    assert [m.id for m in metas] == ["kara-good"]
    assert len(problems) == 1
    assert problems[0].error_category == "recipe_invalid"
    assert "no `id`" in str(problems[0])


def test_duplicate_ids_keep_the_first_and_report(tmp_path):
    _write(tmp_path, "a-first.yaml", 'version: 1\nid: kara-dup\nname: "first"\n')
    _write(tmp_path, "b-second.yaml", 'version: 1\nid: kara-dup\nname: "second"\n')
    metas, problems = load_recipe_metas(str(tmp_path))
    assert len(metas) == 1
    assert metas[0].name == "first"
    assert len(problems) == 1
    assert "duplicate recipe id" in str(problems[0])


def test_invalid_yaml_is_reported_not_raised(tmp_path):
    _write(tmp_path, "broken.yaml", "version: 1\nid: [unclosed\n")
    metas, problems = load_recipe_metas(str(tmp_path))
    assert metas == []
    assert len(problems) == 1
    assert problems[0].error_category == "recipe_invalid"


def test_missing_directory_yields_no_recipes(tmp_path):
    metas, problems = load_recipe_metas(str(tmp_path / "nope"))
    assert metas == []
    assert problems == []


def test_non_mapping_root_is_rejected(tmp_path):
    path = _write(tmp_path, "list.yaml", "- just\n- a list\n")
    with pytest.raises(RecipeMetaError):
        load_recipe_meta(path)


def test_non_string_description_is_rejected(tmp_path):
    path = _write(tmp_path, "d.yaml", "version: 1\nid: kara-d\nname: n\ndescription: 42\n")
    with pytest.raises(RecipeMetaError):
        load_recipe_meta(path)
