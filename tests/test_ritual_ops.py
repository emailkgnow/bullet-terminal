"""Tests for ritual operations."""

from datetime import date, datetime, timedelta, timezone

from bute.models import Entry, EntryType, TaskStatus
from bute.ritual_ops import (
    clear_daily_focus,
    clear_weekly_selection,
    get_all_active_tasks,
    get_today_schedule,
    get_yesterday_unresolved,
    process_dump_line,
    set_weekly_selection,
)
from bute.storage import entry_path_from_id, load_entry, save_entry


def test_get_yesterday_unresolved(tmp_data):
    """Yesterday's active tasks show up; done tasks and notes don't."""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    e1 = Entry.create(EntryType.TASK, "active task")
    e1.created = yesterday
    e2 = Entry.create(EntryType.TASK, "done task")
    e2.status = TaskStatus.DONE
    e2.created = yesterday
    e3 = Entry.create(EntryType.NOTE, "a note")
    e3.created = yesterday
    save_entry(e1)
    save_entry(e2)
    save_entry(e3)

    result = get_yesterday_unresolved()
    assert len(result) == 1
    assert result[0].body == "active task"


def test_get_today_schedule(tmp_data):
    e1 = Entry.create(EntryType.CALENDAR, "standup")
    e2 = Entry.create(EntryType.TASK, "a task")
    save_entry(e1)
    save_entry(e2)

    result = get_today_schedule()
    assert len(result) == 1
    assert result[0].body == "standup"


def test_get_all_active_tasks(tmp_data):
    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.TASK, "task two")
    e3 = Entry.create(EntryType.TASK, "done task")
    e3.status = TaskStatus.DONE
    save_entry(e1)
    save_entry(e2)
    save_entry(e3)

    result = get_all_active_tasks()
    assert len(result) == 2


def test_process_dump_line_with_signifier(tmp_data):
    entry = process_dump_line("t call dentist")
    assert entry is not None
    assert entry.type == EntryType.TASK
    assert entry.body == "call dentist"


def test_process_dump_line_defaults_to_journal(tmp_data):
    entry = process_dump_line("feeling anxious about deadline")
    assert entry is not None
    assert entry.type == EntryType.JOURNAL
    assert "feeling anxious" in entry.body


def test_process_dump_line_empty(tmp_data):
    result = process_dump_line("")
    assert result is None


def test_set_weekly_selection(tmp_data):
    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.TASK, "task two")
    save_entry(e1)
    save_entry(e2)

    count = set_weekly_selection([e1.id, e2.id])
    assert count == 2

    loaded = load_entry(entry_path_from_id(e1.id))
    assert "thisweek" in loaded.tags


def test_clear_weekly_selection(tmp_data):
    e = Entry.create(EntryType.TASK, "task", tags=["thisweek"])
    save_entry(e)

    cleared = clear_weekly_selection()
    assert cleared == 1

    loaded = load_entry(entry_path_from_id(e.id))
    assert "thisweek" not in loaded.tags


def test_clear_daily_focus(tmp_data):
    e = Entry.create(EntryType.TASK, "task", tags=["today"])
    save_entry(e)

    cleared = clear_daily_focus()
    assert cleared == 1

    loaded = load_entry(entry_path_from_id(e.id))
    assert "today" not in loaded.tags
