"""contracts.md §5.4 / §5.5 — the [llm] config section."""

import pytest

from agent.llm_client import LlmConfig, LlmConfigError, load_llm_config, llm_config_from_document
from agent.llm_client.config import TIMEOUT_MAX_MS, TIMEOUT_MIN_MS


def test_defaults_match_contract():
    cfg = LlmConfig(base_url="http://localhost:11434/v1")
    assert cfg.api_key == ""
    assert cfg.model == "llama3"
    assert cfg.timeout_ms == 5000
    assert cfg.temperature == 0.0
    assert cfg.chat_completions_url == "http://localhost:11434/v1/chat/completions"


def test_base_url_suffix_handling():
    # §5.4's example already contains /v1 — never append /v1 again.
    assert LlmConfig(base_url="http://host:8080/v1/").chat_completions_url == (
        "http://host:8080/v1/chat/completions"
    )
    # An already-complete endpoint URL is used verbatim.
    assert LlmConfig(base_url="http://host/v1/chat/completions").chat_completions_url == (
        "http://host/v1/chat/completions"
    )
    # Cloud endpoints without a version prefix are the caller's choice, not ours.
    assert LlmConfig(base_url="https://api.example.com").chat_completions_url == (
        "https://api.example.com/chat/completions"
    )


def test_temperature_must_be_zero():
    with pytest.raises(LlmConfigError) as excinfo:
        LlmConfig(base_url="http://localhost:11434/v1", temperature=0.7)
    assert excinfo.value.error_category == "config_non_zero_temperature"
    assert excinfo.value.phase == "startup"


def test_temperature_wrong_type_is_a_startup_error():
    with pytest.raises(LlmConfigError) as excinfo:
        LlmConfig(base_url="http://localhost:11434/v1", temperature="0")
    assert excinfo.value.error_category is None


@pytest.mark.parametrize("ms", [500, 999, 1])
def test_timeout_clamped_low(ms):
    assert LlmConfig(base_url="http://h/v1", timeout_ms=ms).timeout_ms == TIMEOUT_MIN_MS


@pytest.mark.parametrize("ms", [60001, 10_000_000])
def test_timeout_clamped_high(ms):
    assert LlmConfig(base_url="http://h/v1", timeout_ms=ms).timeout_ms == TIMEOUT_MAX_MS


def test_timeout_in_range_untouched():
    assert LlmConfig(base_url="http://h/v1", timeout_ms=2500).timeout_ms == 2500


@pytest.mark.parametrize("url", ["localhost:11434/v1", "ftp://host/v1", "http://", ""])
def test_invalid_base_url_is_routing_stage_llm_unreachable(url):
    with pytest.raises(LlmConfigError) as excinfo:
        LlmConfig(base_url=url)
    assert excinfo.value.error_category == "llm_unreachable"
    assert excinfo.value.phase == "routing"


def test_missing_llm_section_is_mode_b_unavailable():
    with pytest.raises(LlmConfigError) as excinfo:
        llm_config_from_document({"app": {"language": "ja"}})
    assert excinfo.value.error_category == "llm_unreachable"
    assert excinfo.value.phase == "routing"


def test_unknown_keys_warn_and_are_ignored():
    warnings = []
    cfg = llm_config_from_document(
        {"llm": {"base_url": "http://h/v1", "proxy": "http://proxy", "max_tokens": 512}},
        on_warning=lambda cat, msg: warnings.append((cat, msg)),
    )
    assert cfg.base_url == "http://h/v1"
    assert len(warnings) == 2  # proxy, max_tokens
    assert {cat for cat, _ in warnings} == {"config_unknown_key"}
    assert all("[llm]." in msg for _, msg in warnings)


def test_missing_optional_keys_fall_back_to_defaults():
    cfg = llm_config_from_document({"llm": {"base_url": "http://h/v1"}})
    assert (cfg.model, cfg.timeout_ms, cfg.temperature) == ("llama3", 5000, 0.0)


def test_repr_never_contains_the_api_key():
    cfg = LlmConfig(base_url="http://h/v1", api_key="sk-super-secret-value")
    assert "sk-super-secret-value" not in repr(cfg)
    assert "***" in repr(cfg)
    # ...but the value itself is intact for the Authorization header.
    assert cfg.api_key == "sk-super-secret-value"


def test_load_llm_config_reads_a_toml_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[app]\nlanguage = "ja"\n\n'
        '[llm]\nbase_url = "http://localhost:11434/v1"\n'
        'api_key = "sk-from-file"\nmodel = "qwen3"\ntimeout_ms = 2500\n'
        "temperature = 0.0\n",
        encoding="utf-8",
    )
    cfg = load_llm_config(str(path))
    assert cfg.model == "qwen3"
    assert cfg.timeout_ms == 2500
    assert cfg.api_key == "sk-from-file"


def test_load_llm_config_missing_file_propagates(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_llm_config(str(tmp_path / "nope.toml"))
