"""Tests for action commands."""

import pytest

from bute.cli import main
from bute.commands.action import parse_action_tokens
from bute.errors import InvalidActionError
from bute.models import Entry, EntryType, TaskStatus
from bute.storage import entry_path_from_id, load_entry, save_entry
from bute.state import save_state


# --- Token parsing tests ---

class TestParseActionTokens:
    def test_single_number_done(self):
        nums, action, args = parse_action_tokens(("2", "done"))
        assert nums == [2]
        assert action == "done"
        assert args == []

    def test_multiple_numbers_migrate(self):
        nums, action, args = parse_action_tokens(("1", "3", "migrate", "tomorrow"))
        assert nums == [1, 3]
        assert action == "migrate"
        assert args == ["tomorrow"]

    def test_toggle_important(self):
        nums, action, args = parse_action_tokens(("5", "!"))
        assert nums == [5]
        assert action == "!"

    def test_add_tag(self):
        nums, action, args = parse_action_tokens(("3", "+backend"))
        assert nums == [3]
        assert action == "+backend"

    def test_no_numbers_raises(self):
        with pytest.raises(InvalidActionError):
            parse_action_tokens(("done",))

    def test_no_action_raises(self):
        with pytest.raises(InvalidActionError):
            parse_action_tokens(("2",))


# --- Handler tests (via CLI end-to-end) ---

def test_done_marks_task(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.TASK, "test task")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "done"])
    assert result.exit_code == 0
    assert "done" in result.output

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.status == TaskStatus.DONE


def test_drop_marks_task(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.TASK, "test task")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "drop"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.status == TaskStatus.DROPPED


def test_toggle_important_on(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "test note")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "!"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.important is True


def test_toggle_important_off(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.TASK, "test", important=True)
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "!"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.important is False


def test_add_tag(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "test note")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "@work"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert "work" in loaded.tags


def test_add_tag_no_duplicate(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "test", tags=["work"])
    save_entry(entry)
    save_state("ls", [entry.id])

    runner.invoke(main, ["1", "@work"])
    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.tags.count("work") == 1


def test_untag(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "test note", tags=["work", "urgent"])
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "untag", "@work"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert "work" not in loaded.tags
    assert "urgent" in loaded.tags


def test_untag_without_at(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "test", tags=["backend"])
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "untag", "backend"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert "backend" not in loaded.tags


def test_migrate_tomorrow(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.TASK, "test task")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "migrate", "tomorrow"])
    assert result.exit_code == 0
    assert "migrate" in result.output

    # Original should be migrated
    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.status == TaskStatus.MIGRATED

    # New entry should exist
    from bute.storage import load_entries_by_filter
    new_entries = load_entries_by_filter(
        lambda e: e.body == "test task" and e.status == TaskStatus.ACTIVE
    )
    assert len(new_entries) == 1


def test_done_on_note_errors(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "test note")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "done"])
    assert result.exit_code == 0  # command runs, per-entry error printed
    assert "note" in result.output.lower()


def test_batch_action(runner, tmp_config, tmp_data):
    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.TASK, "task two")
    save_entry(e1)
    save_entry(e2)
    save_state("ls", [e1.id, e2.id])

    result = runner.invoke(main, ["1", "2", "done"])
    assert result.exit_code == 0

    assert load_entry(entry_path_from_id(e1.id)).status == TaskStatus.DONE
    assert load_entry(entry_path_from_id(e2.id)).status == TaskStatus.DONE
