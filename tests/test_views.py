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


def test_list_view_shows_extra_meta(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"project": "alpha"}))
    result = runner.invoke(main, ["b"])
    assert result.exit_code == 0, result.output
    assert "project:alpha" in result.output


def test_list_view_safe_with_unmatched_rich_tag_in_extra_meta(runner, tmp_config, tmp_data):
    """Verify list view (table) doesn't crash when extra_meta contains unmatched Rich markup."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    # Unmatched closing tag [/] would crash Rich table without escaping
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"key": "[/]"}))
    result = runner.invoke(main, ["b"])
    assert result.exit_code == 0, result.output
    # Literal value should appear in output
    assert "key:[/]" in result.output


def test_list_view_renders_literal_text_with_styling_markup_in_extra_meta(runner, tmp_config, tmp_data):
    """Verify that styling markup like [bold] is rendered literally, not consumed as styling."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    # [bold]x should render as literal text, not as bold x
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"key": "[bold]x"}))
    result = runner.invoke(main, ["b"])
    assert result.exit_code == 0, result.output
    # Literal value should appear (without being consumed as markup)
    assert "key:[bold]x" in result.output


def test_show_entry_safe_with_rich_markup_in_extra_meta(runner, tmp_config, tmp_data, monkeypatch):
    """Verify bt <n> show (display_entry_full) doesn't crash with markup in extra_meta."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    from bute.state import save_state
    from bute.cli import main

    # Mock shutil.which to disable glow, forcing Rich fallback
    import shutil
    real_which = shutil.which
    monkeypatch.setattr(
        shutil, "which",
        lambda cmd, *a, **kw: None if cmd == "glow" else real_which(cmd, *a, **kw),
    )

    # Create entry and save it
    entry = Entry.create(EntryType.TASK, "call bank", extra_meta={"key": "[/]"})
    save_entry(entry)
    # Set up state so entry is in the display list
    save_state("tasks", [entry.id])
    # Show the entry
    result = runner.invoke(main, ["1", "show"])
    assert result.exit_code == 0, result.output
    # Literal value should appear in the output
    assert "key:[/]" in result.output
