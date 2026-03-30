"""Tests for view commands."""

import json
from datetime import datetime
from unittest.mock import patch

from bute.cli import main
from bute.config import default_config, save_config
from bute.state import state_path


def _setup_config(tmp_config, tmp_data):
    doc = default_config(provider="ollama")
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


def test_ls_today(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["ls"])
    assert result.exit_code == 0
    assert "call dentist" in result.output
    assert "fix bug" in result.output
    assert "OAuth2 tokens" in result.output
    assert "feeling good" in result.output


def test_ls_today_empty(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["ls"])
    assert result.exit_code == 0
    assert "No entries found" in result.output


def test_ls_tasks(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["ls", "tasks"])
    assert result.exit_code == 0
    assert "call dentist" in result.output
    assert "fix bug" in result.output
    # Notes and journals should not appear
    assert "OAuth2 tokens" not in result.output
    assert "feeling good" not in result.output


def test_active(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["active"])
    assert result.exit_code == 0
    assert "This Week" in result.output


def test_tag_filter(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["+backend"])
    assert result.exit_code == 0
    assert "fix bug" in result.output
    assert "call dentist" not in result.output


def test_tag_filter_empty(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["+nonexistent"])
    assert result.exit_code == 0
    assert "No entries found" in result.output


def test_ls_writes_state(runner, tmp_config, populated_data):
    runner.invoke(main, ["ls"])
    path = state_path()
    assert path.exists()
    state = json.loads(path.read_text())
    assert state["view"] == "ls"
    assert len(state["entries"]) == 4


def test_ls_tasks_writes_state(runner, tmp_config, populated_data):
    runner.invoke(main, ["ls", "tasks"])
    path = state_path()
    state = json.loads(path.read_text())
    assert len(state["entries"]) == 2  # only active tasks


def test_ls_shows_recap_reminder_in_evening(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    e = Entry.create(EntryType.JOURNAL, "a thought")
    e.tags.append("today")
    save_entry(e)

    evening = datetime(2026, 3, 30, 19, 0, 0)
    with patch("bute.commands.views.datetime") as mock_dt:
        mock_dt.now.return_value = evening
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = runner.invoke(main, ["ls"])

    assert result.exit_code == 0
    assert "bt recap" in result.output


def test_ls_no_reminder_before_6pm(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    e = Entry.create(EntryType.JOURNAL, "a thought")
    e.tags.append("today")
    save_entry(e)

    afternoon = datetime(2026, 3, 30, 14, 0, 0)
    with patch("bute.commands.views.datetime") as mock_dt:
        mock_dt.now.return_value = afternoon
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = runner.invoke(main, ["ls"])

    assert result.exit_code == 0
    assert "bt recap" not in result.output


def test_ls_no_reminder_if_recap_done(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    from bute.state import mark_recap_done
    e = Entry.create(EntryType.JOURNAL, "a thought")
    e.tags.append("today")
    save_entry(e)
    mark_recap_done()

    evening = datetime(2026, 3, 30, 20, 0, 0)
    with patch("bute.commands.views.datetime") as mock_dt:
        mock_dt.now.return_value = evening
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = runner.invoke(main, ["ls"])

    assert result.exit_code == 0
    assert "bt recap" not in result.output
