"""config.toml [matcher] validation — contracts.md §5.2, §5.3, §5.5."""

from __future__ import annotations

import pytest

from agent.router.config import (
    DEFAULT_SIMILARITY_THRESHOLD,
    MatcherConfigError,
    load_matcher_config,
)


def _write(tmp_path, body: str) -> str:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_defaults_are_the_frozen_values(tmp_path):
    path = _write(tmp_path, '[matcher]\nonnx_model_path = "models/x.onnx"\n')
    config = load_matcher_config(path, require_model_file=False)
    assert config.similarity_threshold == DEFAULT_SIMILARITY_THRESHOLD == 0.82
    assert config.recipe_dir == "recipes"
    assert config.recipe_index_path == "models/recipe_index.faiss"
    assert config.warnings == ()


def test_missing_config_file_is_fatal(tmp_path):
    with pytest.raises(MatcherConfigError) as excinfo:
        load_matcher_config(str(tmp_path / "nope.toml"))
    assert excinfo.value.error_category == "config_onnx_model_missing"


def test_missing_matcher_section_is_fatal(tmp_path):
    path = _write(tmp_path, '[app]\nlanguage = "ja"\n')
    with pytest.raises(MatcherConfigError) as excinfo:
        load_matcher_config(path)
    assert excinfo.value.error_category == "config_onnx_model_missing"


def test_missing_onnx_model_path_key_is_fatal(tmp_path):
    path = _write(tmp_path, '[matcher]\nsimilarity_threshold = 0.9\n')
    with pytest.raises(MatcherConfigError) as excinfo:
        load_matcher_config(path)
    assert excinfo.value.error_category == "config_onnx_model_missing"
    assert "onnx_model_path" in str(excinfo.value)


def test_empty_onnx_model_path_is_fatal(tmp_path):
    path = _write(tmp_path, '[matcher]\nonnx_model_path = "   "\n')
    with pytest.raises(MatcherConfigError) as excinfo:
        load_matcher_config(path)
    assert excinfo.value.error_category == "config_onnx_model_missing"


def test_model_file_must_exist_by_default(tmp_path):
    path = _write(tmp_path, '[matcher]\nonnx_model_path = "definitely-missing.onnx"\n')
    with pytest.raises(MatcherConfigError) as excinfo:
        load_matcher_config(path)
    assert excinfo.value.error_category == "config_onnx_model_missing"


def test_model_file_existence_can_be_relaxed_for_validation_only(tmp_path):
    path = _write(tmp_path, '[matcher]\nonnx_model_path = "definitely-missing.onnx"\n')
    config = load_matcher_config(path, require_model_file=False)
    assert config.onnx_model_path == "definitely-missing.onnx"


def test_out_of_range_threshold_is_clamped_with_a_warning(tmp_path):
    for raw, expected in ((1.7, 1.0), (-0.4, 0.0)):
        path = _write(
            tmp_path,
            f'[matcher]\nonnx_model_path = "x.onnx"\nsimilarity_threshold = {raw}\n',
        )
        config = load_matcher_config(path, require_model_file=False)
        assert config.similarity_threshold == expected
        assert len(config.warnings) == 1
        assert "clamped" in config.warnings[0].message


def test_non_numeric_threshold_is_fatal(tmp_path):
    path = _write(
        tmp_path, '[matcher]\nonnx_model_path = "x.onnx"\nsimilarity_threshold = "high"\n'
    )
    with pytest.raises(MatcherConfigError) as excinfo:
        load_matcher_config(path, require_model_file=False)
    assert excinfo.value.error_category is None
    assert "similarity_threshold" in str(excinfo.value)


def test_unknown_key_in_matcher_section_warns_and_is_ignored(tmp_path):
    path = _write(
        tmp_path,
        '[matcher]\nonnx_model_path = "x.onnx"\nsimilairty_threshold = 0.9\n',
    )
    config = load_matcher_config(path, require_model_file=False)
    assert config.similarity_threshold == 0.82
    assert [w.error_category for w in config.warnings] == ["config_unknown_key"]
    assert "similairty_threshold" in config.warnings[0].message


def test_unknown_key_in_app_section_warns(tmp_path):
    path = _write(
        tmp_path,
        '[app]\nlanguage = "ja"\nreciepe_dir = "recipes"\n[matcher]\nonnx_model_path = "x.onnx"\n',
    )
    config = load_matcher_config(path, require_model_file=False)
    assert [w.error_category for w in config.warnings] == ["config_unknown_key"]


def test_invalid_toml_is_fatal(tmp_path):
    path = _write(tmp_path, "[matcher\nonnx_model_path = ")
    with pytest.raises(MatcherConfigError) as excinfo:
        load_matcher_config(path)
    assert excinfo.value.error_category is None


def test_tokenizer_path_is_discovered_next_to_the_model(tmp_path):
    model = tmp_path / "m.onnx"
    model.write_bytes(b"")
    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    # TOML literal string (single quotes): Windows paths contain backslashes.
    path = _write(tmp_path, f"[matcher]\nonnx_model_path = '{model}'\n")
    config = load_matcher_config(path, require_model_file=False)
    assert config.tokenizer_path == str(tmp_path / "tokenizer.json")


def test_tokenizer_path_is_none_when_no_tokenizer_sits_next_to_the_model(tmp_path):
    model = tmp_path / "m.onnx"
    model.write_bytes(b"")
    path = _write(tmp_path, f"[matcher]\nonnx_model_path = '{model}'\n")
    config = load_matcher_config(path, require_model_file=False)
    assert config.tokenizer_path is None
