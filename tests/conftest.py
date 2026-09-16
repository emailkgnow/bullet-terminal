"""Shared test fixtures for dwn."""

from datetime import date

import pytest
from click.testing import CliRunner

from bute.models import Entry, EntryType
from bute.storage import save_entry


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def populated_data(tmp_data):
    """Create sample entries for testing views and actions."""
    entries = [
        Entry.create(EntryType.TASK, "call dentist", tags=["health"], due=date.today()),
        Entry.create(EntryType.TASK, "fix bug", important=True, tags=["backend"]),
        Entry.create(EntryType.NOTE, "OAuth2 tokens last 30 days", tags=["api-v2"]),
        Entry.create(EntryType.JOURNAL, "feeling good today"),
    ]
    for e in entries:
        save_entry(e)
    return entries


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect config to a temp directory."""
    config_dir = tmp_path / ".config" / "dwn"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.toml"
    monkeypatch.setattr("bute.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("bute.config.CONFIG_FILE", config_file)
    monkeypatch.setattr("bute.config.TOUR_DONE", config_dir / ".tour_done")
    return config_dir


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """Redirect data directory to a temp directory and reset DB connection after."""
    data_dir = tmp_path / "dwn"
    monkeypatch.setattr("bute.config.DATA_DIR_DEFAULT", data_dir)
    yield data_dir
    from bute.db import close
    close()


@pytest.fixture(autouse=True)
def _never_migrate_the_real_config_dir(tmp_path, monkeypatch):
    """Point the legacy-config lookup at a path that does not exist.

    load_config() copies ~/.config/bute/ → ~/.config/bt/ on first call. No test may
    ever trigger that against the user's real home directory.
    """
    monkeypatch.setattr(
        "bute.config.LEGACY_CONFIG_DIR", tmp_path / "no-legacy-config", raising=False
    )
