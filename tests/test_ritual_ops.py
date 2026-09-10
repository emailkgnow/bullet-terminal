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
    from bute.ritual_ops import week_anchor
    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.TASK, "task two")
    save_entry(e1)
    save_entry(e2)

    count = set_weekly_selection([e1.id, e2.id])
    assert count == 2

    loaded = load_entry(entry_path_from_id(e1.id))
    assert loaded.week_date == week_anchor()


def test_clear_weekly_selection(tmp_data):
    from bute.ritual_ops import week_anchor
    e = Entry.create(EntryType.TASK, "task", week_date=week_anchor())
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
    """Tasks with completed_date == today are returned."""
    e = Entry.create(EntryType.TASK, "finished task", completed_date=date.today())
    e.status = TaskStatus.DONE
    save_entry(e)

    result = get_tasks_done_today()
    assert len(result) == 1
    assert result[0].body == "finished task"


def test_get_tasks_done_today_excludes_old(tmp_data):
    """Tasks with completed_date in the past are excluded."""
    yesterday = date.today() - timedelta(days=1)
    e = Entry.create(EntryType.TASK, "old done task", completed_date=yesterday)
    e.status = TaskStatus.DONE
    save_entry(e)

    result = get_tasks_done_today()
    assert len(result) == 0


def test_get_tasks_done_today_excludes_active(tmp_data):
    """Active tasks are never returned."""
    e = Entry.create(EntryType.TASK, "still active")
    save_entry(e)

    result = get_tasks_done_today()
    assert len(result) == 0


def test_get_tasks_dropped_today(tmp_data):
    """Tasks with completed_date == today and status dropped are returned."""
    e = Entry.create(EntryType.TASK, "dropped task", completed_date=date.today())
    e.status = TaskStatus.DROPPED
    save_entry(e)

    result = get_tasks_dropped_today()
    assert len(result) == 1
    assert result[0].body == "dropped task"


def test_get_tasks_dropped_today_excludes_old(tmp_data):
    """Tasks dropped on a previous day are excluded."""
    yesterday = date.today() - timedelta(days=1)
    e = Entry.create(EntryType.TASK, "old drop", completed_date=yesterday)
    e.status = TaskStatus.DROPPED
    save_entry(e)

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


def test_focus_log_excludes_recurring_tasks(tmp_data):
    """Recurring tasks are surfaced via the Habits section, not the main Focus Log."""
    from datetime import date
    from bute.models import Entry, EntryType
    from bute.ritual_ops import get_daily_log
    from bute.storage import save_entry

    # Regular task in today's focus — should show
    regular = Entry.create(
        entry_type=EntryType.TASK,
        body="call dentist",
        focus_date=date.today(),
    )
    save_entry(regular)

    # Recurring task (no @habit tag) — should be excluded from main log
    recurring = Entry.create(
        entry_type=EntryType.TASK,
        body="meditate",
        repeat="daily",
        focus_date=date.today(),
    )
    save_entry(recurring)

    bodies = {e.body for e in get_daily_log(None)}
    assert "call dentist" in bodies
    assert "meditate" not in bodies


def test_weekly_active_tasks_excludes_recurring(tmp_data):
    """Weekly task selection skips recurring tasks even without @habit tag."""
    from datetime import date
    from bute.models import Entry, EntryType
    from bute.ritual_ops import get_weekly_active_tasks, week_anchor
    from bute.storage import save_entry

    monday = week_anchor()
    planned = Entry.create(
        entry_type=EntryType.TASK, body="write report", week_date=monday
    )
    save_entry(planned)

    recurring = Entry.create(
        entry_type=EntryType.TASK, body="meditate", repeat="daily", week_date=monday
    )
    save_entry(recurring)

    bodies = {e.body for e in get_weekly_active_tasks(None)}
    assert "write report" in bodies
    assert "meditate" not in bodies


# --- week anchor honours core.week_start ---

SUNDAY_CONFIG = {"core": {"week_start": "sunday"}}
MONDAY_CONFIG = {"core": {"week_start": "monday"}}


def test_week_anchor_honours_sunday_week_start():
    """With week_start=sunday the anchor is the preceding Sunday, not Monday."""
    from datetime import date
    from bute.ritual_ops import week_anchor

    thursday = date(2026, 9, 10)
    assert week_anchor(thursday, SUNDAY_CONFIG) == date(2026, 9, 6)
    assert week_anchor(thursday, MONDAY_CONFIG) == date(2026, 9, 7)


def test_week_anchor_defaults_to_monday_without_config():
    """No config means ISO weeks — Monday, matching the previous behaviour."""
    from datetime import date
    from bute.ritual_ops import week_anchor

    assert week_anchor(date(2026, 9, 10)) == date(2026, 9, 7)


def test_week_anchor_matches_week_bounds_start():
    """The anchor must equal the start week_bounds reports for the same config."""
    from datetime import date, timedelta
    from bute.config import week_bounds
    from bute.ritual_ops import week_anchor

    for offset in range(14):
        day = date(2026, 9, 1) + timedelta(days=offset)
        for cfg in (SUNDAY_CONFIG, MONDAY_CONFIG, None):
            assert week_anchor(day, cfg) == week_bounds(day, cfg)[0]


def test_weekly_selection_roundtrips_under_sunday_week_start(tmp_data):
    """A task selected for the week is found again by the weekly view."""
    from bute.models import Entry, EntryType
    from bute.ritual_ops import get_weekly_active_tasks, set_weekly_selection
    from bute.storage import save_entry

    picked = Entry.create(entry_type=EntryType.TASK, body="write report")
    save_entry(picked, SUNDAY_CONFIG)
    other = Entry.create(entry_type=EntryType.TASK, body="unpicked")
    save_entry(other, SUNDAY_CONFIG)

    set_weekly_selection([picked.id], SUNDAY_CONFIG)

    bodies = {e.body for e in get_weekly_active_tasks(SUNDAY_CONFIG)}
    assert bodies == {"write report"}
