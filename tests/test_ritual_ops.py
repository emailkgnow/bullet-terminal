"""Tests for ritual operations."""

import os
from datetime import date, datetime, timedelta, timezone

from bute.models import Entry, EntryType, TaskStatus
from bute.ritual_ops import (
    clear_daily_focus,
    clear_weekly_selection,
    get_all_active_tasks,
    get_tasks_done_today,
    get_tasks_dropped_today,
    get_today_captured,
    get_today_schedule,
    get_week_entries,
    get_yesterday_unresolved,
    process_dump_line,
    set_weekly_selection,
)
from bute.storage import entry_path, entry_path_from_id, load_entry, save_entry, update_entry


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
    from bute.ritual_ops import this_monday
    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.TASK, "task two")
    save_entry(e1)
    save_entry(e2)

    count = set_weekly_selection([e1.id, e2.id])
    assert count == 2

    loaded = load_entry(entry_path_from_id(e1.id))
    assert loaded.week_date == this_monday()


def test_clear_weekly_selection(tmp_data):
    from bute.ritual_ops import this_monday
    e = Entry.create(EntryType.TASK, "task", week_date=this_monday())
    save_entry(e)

    cleared = clear_weekly_selection()
    assert cleared == 1

    loaded = load_entry(entry_path_from_id(e.id))
    assert loaded.week_date is None


def test_clear_daily_focus(tmp_data):
    from datetime import date
    e = Entry.create(EntryType.TASK, "task", focus_date=date.today())
    save_entry(e)

    cleared = clear_daily_focus()
    assert cleared == 1

    loaded = load_entry(entry_path_from_id(e.id))
    assert loaded.focus_date is None


def test_get_week_entries(tmp_data):
    """Returns all entries from the current week."""
    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.JOURNAL, "a thought")
    e3 = Entry.create(EntryType.NOTE, "a fact")
    for e in [e1, e2, e3]:
        save_entry(e)

    result = get_week_entries()
    assert len(result) == 3
    bodies = [e.body for e in result]
    assert "task one" in bodies
    assert "a thought" in bodies
    assert "a fact" in bodies


def test_get_week_entries_includes_dropped(tmp_data):
    """Dropped entries are included in weekly spread."""
    e = Entry.create(EntryType.TASK, "dropped task")
    e.status = TaskStatus.DROPPED
    save_entry(e)

    result = get_week_entries()
    assert len(result) == 1
    assert result[0].body == "dropped task"


def test_get_tasks_done_today(tmp_data):
    """Tasks marked done with mtime today are returned."""
    e = Entry.create(EntryType.TASK, "finished task")
    save_entry(e)
    e.status = TaskStatus.DONE
    update_entry(e)

    result = get_tasks_done_today()
    assert len(result) == 1
    assert result[0].body == "finished task"


def test_get_tasks_done_today_excludes_old(tmp_data):
    """Tasks done yesterday (old mtime) are excluded."""
    e = Entry.create(EntryType.TASK, "old done task")
    save_entry(e)
    e.status = TaskStatus.DONE
    update_entry(e)

    # Backdate the file mtime to yesterday
    path = entry_path(e)
    yesterday_ts = (datetime.now() - timedelta(days=1)).timestamp()
    os.utime(path, (yesterday_ts, yesterday_ts))

    result = get_tasks_done_today()
    assert len(result) == 0


def test_get_tasks_done_today_excludes_active(tmp_data):
    """Active tasks are not returned even if modified today."""
    e = Entry.create(EntryType.TASK, "still active")
    save_entry(e)

    result = get_tasks_done_today()
    assert len(result) == 0


def test_get_tasks_dropped_today(tmp_data):
    """Tasks marked dropped with mtime today are returned."""
    e = Entry.create(EntryType.TASK, "dropped task")
    save_entry(e)
    e.status = TaskStatus.DROPPED
    update_entry(e)

    result = get_tasks_dropped_today()
    assert len(result) == 1
    assert result[0].body == "dropped task"


def test_get_tasks_dropped_today_excludes_old(tmp_data):
    """Tasks dropped yesterday are excluded."""
    e = Entry.create(EntryType.TASK, "old drop")
    save_entry(e)
    e.status = TaskStatus.DROPPED
    update_entry(e)

    path = entry_path(e)
    yesterday_ts = (datetime.now() - timedelta(days=1)).timestamp()
    os.utime(path, (yesterday_ts, yesterday_ts))

    result = get_tasks_dropped_today()
    assert len(result) == 0


def test_get_today_captured(tmp_data):
    """Returns non-task entries created today, grouped by type."""
    j = Entry.create(EntryType.JOURNAL, "feeling good")
    n = Entry.create(EntryType.NOTE, "a fact")
    c = Entry.create(EntryType.CALENDAR, "standup")
    t = Entry.create(EntryType.TASK, "a task")
    for e in [j, n, c, t]:
        save_entry(e)

    result = get_today_captured()
    assert len(result) == 3  # journal, note, calendar — no task
    bodies = [e.body for e in result]
    assert "feeling good" in bodies
    assert "a fact" in bodies
    assert "standup" in bodies
    assert "a task" not in bodies
