"""Tests for view commands."""

import json

from bute.cli import main
from bute.config import default_config, save_config
from bute.state import state_path


def _setup_config(tmp_config, tmp_data):
    doc = default_config()
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


def test_tasks_view(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["tasks"])
    assert result.exit_code == 0
    assert "call dentist" in result.output


def test_tasks_view_empty(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["tasks"])
    assert result.exit_code == 0


def test_backlog_view(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["backlog"])
    assert result.exit_code == 0
    assert "call dentist" in result.output
    assert "fix bug" in result.output


def test_notes_view(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["notes"])
    assert result.exit_code == 0
    assert "OAuth2 tokens" in result.output


def test_tag_filter(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["@backend"])
    assert result.exit_code == 0
    assert "fix bug" in result.output
    assert "call dentist" not in result.output


def test_tag_filter_empty(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["@nonexistent"])
    assert result.exit_code == 0
    assert "No entries found" in result.output


def test_tasks_writes_state(runner, tmp_config, populated_data):
    runner.invoke(main, ["tasks"])
    path = state_path()
    assert path.exists()
    state = json.loads(path.read_text())
    assert state["view"] == "tasks"
    assert len(state["entries"]) > 0


def test_backlog_writes_state(runner, tmp_config, populated_data):
    runner.invoke(main, ["backlog"])
    path = state_path()
    state = json.loads(path.read_text())
    assert state["view"] == "backlog"
    assert len(state["entries"]) == 2  # both active tasks


def test_tasks_view_excludes_recurring(tmp_config, tmp_data, runner):
    """bt t / bt b exclude recurring tasks regardless of @habit tag."""
    from bute.cli import main
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    regular = Entry.create(entry_type=EntryType.TASK, body="call dentist")
    save_entry(regular)

    recurring = Entry.create(entry_type=EntryType.TASK, body="meditate", repeat="daily")
    save_entry(recurring)

    result = runner.invoke(main, ["b"])
    assert "call dentist" in result.output
    assert "meditate" not in result.output
