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
    assert "habits" in doc


def test_default_config_core_defaults():
    doc = default_config()
    assert doc["core"]["data_dir"] == "~/bullet-terminal"
    assert doc["core"]["wp_day"] == "sunday"
    assert doc["core"]["week_start"] == "monday"


def test_save_load_roundtrip(tmp_config):
    doc = default_config()
    doc["core"]["wp_day"] = "monday"
    save_config(doc)
    loaded = load_config()
    assert loaded["core"]["wp_day"] == "monday"


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


def test_init_command_creates_config_and_dirs(runner, tmp_config, tmp_data):
    from bute.cli import main

    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0
    assert "Config saved" in result.output

    loaded = load_config()
    assert "core" in loaded

    data_dir = get_data_dir(loaded)
    assert (data_dir / "entries").is_dir()
