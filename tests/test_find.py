"""Tests for bt find command — FTS5 keyword search + tag search."""

from bute.cli import main
from bute.models import Entry, EntryType
from bute.storage import save_entry


def test_find_by_body(runner, tmp_config, tmp_data):
    """bt find should match entries by body text."""
    e1 = Entry.create(EntryType.TASK, "call the dentist tomorrow")
    e2 = Entry.create(EntryType.NOTE, "buy groceries")
    save_entry(e1)
    save_entry(e2)

    result = runner.invoke(main, ["find", "dentist"])
    assert result.exit_code == 0
    assert "dentist" in result.output
    assert "groceries" not in result.output


def test_find_by_tag(runner, tmp_config, tmp_data):
    """bt find should also match entries by tag."""
    e1 = Entry.create(EntryType.TASK, "some task", tags=["backend"])
    e2 = Entry.create(EntryType.TASK, "other task", tags=["frontend"])
    save_entry(e1)
    save_entry(e2)

    result = runner.invoke(main, ["find", "backend"])
    assert result.exit_code == 0
    assert "some task" in result.output
    assert "other task" not in result.output


def test_find_type_filter(runner, tmp_config, tmp_data):
    """bt find -t should only return tasks."""
    e1 = Entry.create(EntryType.TASK, "fix the dentist appointment")
    e2 = Entry.create(EntryType.NOTE, "dentist office hours")
    save_entry(e1)
    save_entry(e2)

    result = runner.invoke(main, ["find", "-t", "dentist"])
    assert result.exit_code == 0
    assert "fix the" in result.output
    assert "office hours" not in result.output


def test_find_no_results(runner, tmp_config, tmp_data):
    """bt find with no matches shows message."""
    e1 = Entry.create(EntryType.TASK, "something else")
    save_entry(e1)

    result = runner.invoke(main, ["find", "xyznonexistent"])
    assert result.exit_code == 0
    assert "No entries found" in result.output


def test_find_saves_state(runner, tmp_config, tmp_data):
    """bt find should save state for number-action follow-up."""
    e1 = Entry.create(EntryType.TASK, "call the dentist")
    save_entry(e1)

    runner.invoke(main, ["find", "dentist"])

    from bute.state import load_state
    state = load_state()
    assert state["view"] == "find"


def test_find_deduplicates_body_and_tag(runner, tmp_config, tmp_data):
    """Entry matching both body and tag should appear only once."""
    e1 = Entry.create(EntryType.TASK, "fix backend api", tags=["backend"])
    save_entry(e1)

    result = runner.invoke(main, ["find", "backend"])
    assert result.exit_code == 0
    # Should appear once, not twice
    assert result.output.count("fix backend api") == 1
