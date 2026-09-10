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

    def test_range_expands(self):
        nums, action, args = parse_action_tokens(("1-4", "done"))
        assert nums == [1, 2, 3, 4]
        assert action == "done"

    def test_range_with_bare_numbers(self):
        nums, action, args = parse_action_tokens(("1-4", "12", "done"))
        assert nums == [1, 2, 3, 4, 12]

    def test_range_after_bare_number(self):
        nums, action, args = parse_action_tokens(("2", "4-6", "done"))
        assert nums == [2, 4, 5, 6]

    def test_single_element_range(self):
        nums, action, args = parse_action_tokens(("3-3", "drop"))
        assert nums == [3]

    def test_descending_range_raises(self):
        with pytest.raises(InvalidActionError):
            parse_action_tokens(("4-1", "done"))

    def test_zero_range_raises(self):
        with pytest.raises(InvalidActionError):
            parse_action_tokens(("0-3", "done"))

    def test_oversized_range_raises(self):
        with pytest.raises(InvalidActionError):
            parse_action_tokens(("1-200", "done"))


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


def test_range_marks_multiple_done(runner, tmp_config, tmp_data):
    entries = [Entry.create(EntryType.TASK, f"task {i}") for i in range(5)]
    for e in entries:
        save_entry(e)
    save_state("ls", [e.id for e in entries])

    result = runner.invoke(main, ["1-3", "done"])
    assert result.exit_code == 0

    for i, e in enumerate(entries):
        loaded = load_entry(entry_path_from_id(e.id))
        if i < 3:
            assert loaded.status == TaskStatus.DONE, f"task {i} should be done"
        else:
            assert loaded.status == TaskStatus.ACTIVE, f"task {i} should be untouched"


def test_range_plus_bare_marks_done(runner, tmp_config, tmp_data):
    entries = [Entry.create(EntryType.TASK, f"task {i}") for i in range(6)]
    for e in entries:
        save_entry(e)
    save_state("ls", [e.id for e in entries])

    # bt 1-2 5 done → entries 1, 2, 5 (indices 0, 1, 4)
    result = runner.invoke(main, ["1-2", "5", "done"])
    assert result.exit_code == 0

    expected_done = {0, 1, 4}
    for i, e in enumerate(entries):
        loaded = load_entry(entry_path_from_id(e.id))
        if i in expected_done:
            assert loaded.status == TaskStatus.DONE
        else:
            assert loaded.status == TaskStatus.ACTIVE


def test_descending_range_errors(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.TASK, "task")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["4-1", "done"])
    assert result.exit_code != 0
    assert "descending" in result.output.lower() or "4-1" in result.output


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


def test_add_multiple_tags(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "test note")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "@home", "@urgent", "@backend"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert "home" in loaded.tags
    assert "urgent" in loaded.tags
    assert "backend" in loaded.tags


def test_add_tag_no_duplicate(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "test", tags=["work"])
    save_entry(entry)
    save_state("ls", [entry.id])

    runner.invoke(main, ["1", "@work"])
    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.tags.count("work") == 1


def test_clear_tag(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "test note", tags=["work", "urgent"])
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "clear", "@work"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert "work" not in loaded.tags
    assert "urgent" in loaded.tags


def test_clear_tag_without_at(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "test", tags=["backend"])
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "clear", "backend"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert "backend" not in loaded.tags


def test_clear_important(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "important note", important=True)
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "clear", "!"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.important is False


def test_clear_due(runner, tmp_config, tmp_data):
    from datetime import date
    entry = Entry.create(EntryType.TASK, "task with due", due=date(2026, 5, 1))
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "clear", "due"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.due is None


def test_clear_scheduled_date(runner, tmp_config, tmp_data):
    from datetime import date
    entry = Entry.create(EntryType.NOTE, "scheduled note", scheduled_date=date(2026, 5, 1))
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "clear", "d"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.scheduled_date is None


def test_clear_time(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.CALENDAR, "meeting", scheduled_time="14:30")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "clear", "t"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.scheduled_time is None


def test_clear_repeat(runner, tmp_config, tmp_data):
    entry = Entry.create(EntryType.TASK, "daily task", repeat="daily")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "clear", "repeat"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.repeat is None



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


def test_handle_delete_removes_from_db(tmp_data):
    from bute.commands.action import handle_delete
    from bute.db import close, get_connection

    entry = Entry.create(EntryType.TASK, "to delete")
    save_entry(entry)

    handle_delete(entry, [], None)

    conn = get_connection()
    row = conn.execute(
        "SELECT entry_id FROM entries WHERE entry_id = ?", (entry.id,)
    ).fetchone()
    assert row is None
    close()


# --- focus_date / week_date behavior tests ---


def test_later_clears_focus_date(runner, tmp_config, tmp_data):
    """bt <n> later should clear focus_date but leave week_date."""
    from datetime import date
    from bute.ritual_ops import week_anchor
    entry = Entry.create(
        EntryType.TASK, "focused task",
        focus_date=date.today(),
        week_date=week_anchor(),
    )
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "later"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.focus_date is None
    assert loaded.week_date == week_anchor()


def test_focus_sets_both_dates(runner, tmp_config, tmp_data):
    """bt <n> focus sets focus_date=today and week_date=monday."""
    from datetime import date
    from bute.ritual_ops import week_anchor
    entry = Entry.create(EntryType.TASK, "backlog task")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "focus"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.focus_date == date.today()
    assert loaded.week_date == week_anchor()


def test_backlog_clears_both_dates(runner, tmp_config, tmp_data):
    """bt <n> backlog clears focus_date and week_date."""
    from datetime import date
    from bute.ritual_ops import week_anchor
    entry = Entry.create(
        EntryType.TASK, "focused task",
        focus_date=date.today(),
        week_date=week_anchor(),
    )
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "backlog"])
    assert result.exit_code == 0

    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.focus_date is None
    assert loaded.week_date is None


def test_entry_roundtrip_with_focus_week_dates(tmp_data):
    """Entry with focus_date and week_date should round-trip through YAML."""
    from datetime import date
    entry = Entry.create(
        EntryType.TASK, "dated task",
        focus_date=date(2026, 4, 16),
        week_date=date(2026, 4, 13),
    )
    save_entry(entry)
    loaded = load_entry(entry_path_from_id(entry.id))
    assert loaded.focus_date == date(2026, 4, 16)
    assert loaded.week_date == date(2026, 4, 13)


def test_get_daily_log_filters_by_focus_date(tmp_data):
    """get_daily_log should only return tasks with focus_date == today."""
    from datetime import date, timedelta
    from bute.ritual_ops import get_daily_log, week_anchor

    today = date.today()
    yesterday = today - timedelta(days=1)

    focused = Entry.create(EntryType.TASK, "today task", focus_date=today, week_date=week_anchor())
    stale = Entry.create(EntryType.TASK, "yesterday task", focus_date=yesterday, week_date=week_anchor())
    unfocused = Entry.create(EntryType.TASK, "no focus")

    for e in [focused, stale, unfocused]:
        save_entry(e)

    log = get_daily_log(None)
    ids = {e.id for e in log}
    assert focused.id in ids
    assert stale.id not in ids
    assert unfocused.id not in ids


def test_get_weekly_active_tasks_filters_by_week_date(tmp_data):
    """get_weekly_active_tasks should only return tasks with week_date == this Monday."""
    from datetime import date, timedelta
    from bute.ritual_ops import get_weekly_active_tasks, week_anchor

    monday = week_anchor()
    last_monday = monday - timedelta(days=7)

    current = Entry.create(EntryType.TASK, "current", week_date=monday)
    old = Entry.create(EntryType.TASK, "old", week_date=last_monday)

    for e in [current, old]:
        save_entry(e)

    tasks = get_weekly_active_tasks(None)
    ids = {e.id for e in tasks}
    assert current.id in ids
    assert old.id not in ids


# --- Event emission tests ---


def test_action_done_sets_status_and_completed_date(runner, tmp_config, tmp_data):
    """bt <n> done should set status=done and completed_date=today."""
    from datetime import date
    from bute.models import TaskStatus
    entry = Entry.create(EntryType.TASK, "ship it")
    save_entry(entry)
    save_state("tasks", [entry.id])

    result = runner.invoke(main, ["1", "done"])
    assert result.exit_code == 0

    reloaded = load_entry(entry_path_from_id(entry.id))
    assert reloaded.status == TaskStatus.DONE
    assert reloaded.completed_date == date.today()


def test_action_drop_sets_status_dropped(runner, tmp_config, tmp_data):
    """bt <n> drop should set status=dropped and completed_date=today."""
    from datetime import date
    from bute.models import TaskStatus
    entry = Entry.create(EntryType.TASK, "nope")
    save_entry(entry)
    save_state("tasks", [entry.id])

    result = runner.invoke(main, ["1", "drop"])
    assert result.exit_code == 0

    reloaded = load_entry(entry_path_from_id(entry.id))
    assert reloaded.status == TaskStatus.DROPPED
    assert reloaded.completed_date == date.today()


def test_action_later_clears_focus_date(runner, tmp_config, tmp_data):
    """bt <n> later should clear focus_date so the task drops off today's log."""
    from datetime import date
    entry = Entry.create(EntryType.TASK, "meh", focus_date=date.today())
    save_entry(entry)
    save_state("tasks", [entry.id])

    result = runner.invoke(main, ["1", "later"])
    assert result.exit_code == 0

    reloaded = load_entry(entry_path_from_id(entry.id))
    assert reloaded.focus_date is None


def test_show_renders_markdown_body(runner, tmp_config, tmp_data):
    """bt <n> show renders the body as formatted markdown without raw symbols."""
    body = "# My Heading\n\nSome **bold** text and a list:\n\n- one\n- two\n"
    entry = Entry.create(EntryType.NOTE, body, tags=["retirement"])
    save_entry(entry)
    save_state("notes", [entry.id])

    result = runner.invoke(main, ["1", "show"])
    assert result.exit_code == 0
    # Header surfaces type label, tag, and short id
    assert "note" in result.output
    assert "@retirement" in result.output
    assert entry.id[:8] in result.output
    # Rendered markdown contains the words but not the raw '#' / '**' symbols
    assert "My Heading" in result.output
    assert "bold" in result.output
    assert "one" in result.output
    assert "two" in result.output
    assert "**bold**" not in result.output
    assert "# My Heading" not in result.output


def test_read_aliases_show(runner, tmp_config, tmp_data):
    """`read` is an alias for `show`."""
    entry = Entry.create(EntryType.NOTE, "# Hi\n\nbody text")
    save_entry(entry)
    save_state("notes", [entry.id])

    result = runner.invoke(main, ["1", "read"])
    assert result.exit_code == 0
    assert "Hi" in result.output
    assert "body text" in result.output
