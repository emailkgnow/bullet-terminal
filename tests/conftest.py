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
def _isolate_the_real_config_dir(request, tmp_path_factory, monkeypatch):
    """No test may read or write the real ~/.config/bt/.

    save_config() writes CONFIG_FILE unconditionally and `bt -j` touches
    CONFIG_DIR/.no-journal, so a test reaching either without the tmp_config
    fixture would write into the user's own config dir — where data_dir lives.
    Redirect all three paths for every test; tests needing particular values
    re-patch them in their own body, which wins.

    The directory comes from tmp_path_factory rather than tmp_path so it never
    appears in tests that assert on the contents of their own tmp_path. The tour
    marker is pre-created so no test can drop into the first-run tour's REPL.

    Opt out with @pytest.mark.real_config_paths for tests that assert on the
    default constants themselves and never touch the filesystem.
    """
    if "real_config_paths" in request.keywords:
        return
    config_dir = tmp_path_factory.mktemp("config")
    (config_dir / ".tour_done").touch()
    monkeypatch.setattr("bute.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("bute.config.CONFIG_FILE", config_dir / "config.toml")
    monkeypatch.setattr("bute.config.TOUR_DONE", config_dir / ".tour_done")
