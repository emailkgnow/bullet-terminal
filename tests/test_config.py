"""Tests for configuration management."""

from bute.config import (
    default_config,
    ensure_data_dirs,
    get_data_dir,
    load_config,
    save_config,
)


def test_default_config_has_required_sections():
    doc = default_config()
    assert "core" in doc
    assert "ai" in doc
    assert "habits" in doc


def test_default_config_ollama():
    doc = default_config(provider="ollama")
    assert doc["ai"]["provider"] == "ollama"
    assert "11434" in doc["ai"]["base_url"]


def test_default_config_anthropic():
    doc = default_config(provider="anthropic")
    assert doc["ai"]["provider"] == "anthropic"
    assert "anthropic" in doc["ai"]["base_url"]


def test_save_load_roundtrip(tmp_config):
    doc = default_config(provider="openai", model="gpt-4o")
    save_config(doc)
    loaded = load_config()
    assert loaded["ai"]["provider"] == "openai"
    assert loaded["ai"]["model"] == "gpt-4o"


def test_load_missing_config_returns_empty(tmp_config):
    doc = load_config()
    assert len(doc) == 0


def test_get_data_dir_default(tmp_data):
    assert get_data_dir(None) == tmp_data


def test_get_data_dir_from_config():
    doc = default_config()
    data_dir = get_data_dir(doc)
    assert str(data_dir).endswith("bullet-terminal")


def test_ensure_data_dirs_creates_structure(tmp_data):
    path = ensure_data_dirs(None)
    assert (path / "entries").is_dir()
    assert (path / ".index").is_dir()


def test_init_command_with_flags(runner, tmp_config, tmp_data):
    from bute.cli import main

    result = runner.invoke(main, ["init", "--provider", "ollama", "--model", "llama3"])
    assert result.exit_code == 0
    assert "Config saved" in result.output

    # Verify config was written
    loaded = load_config()
    assert loaded["ai"]["provider"] == "ollama"

    # Verify data dirs were created
    from bute.config import get_data_dir

    data_dir = get_data_dir(loaded)
    assert (data_dir / "entries").is_dir()
