"""Pure query and action functions for rituals."""

from datetime import date, timedelta

from bute.models import Entry, EntryType, TaskStatus
from bute.parser import parse_capture_tokens
from bute.storage import (
    load_entries_by_date,
    save_entry,
    update_entry,
)


def this_monday(today: date | None = None) -> date:
    """Return Monday of the ISO week containing the given date (defaults to today)."""
    d = today or date.today()
    return d - timedelta(days=d.weekday())


def get_yesterday_unresolved(config=None) -> list[Entry]:
    """Active tasks from yesterday."""
    yesterday = date.today() - timedelta(days=1)
    return [
        e
        for e in load_entries_by_date(yesterday, config)
        if e.type == EntryType.TASK and e.status == TaskStatus.ACTIVE
    ]


def get_today_schedule(config=None) -> list[Entry]:
    """Calendar entries for today — both created today and scheduled for today."""
    today = date.today()
    # Entries created today that are calendar type
    today_entries = load_entries_by_date(today, config)
    today_calendar = [e for e in today_entries if e.type == EntryType.CALENDAR]

    # Entries scheduled for today but created on a different day
    from bute.storage import query_and_load
    scheduled_today = query_and_load(config, type="calendar", scheduled_date=today.isoformat())
    scheduled_today = [e for e in scheduled_today if e.created.date() != today]

    # Combine and deduplicate by ID
    seen = set()
    result = []
    for e in today_calendar + scheduled_today:
        if e.id not in seen:
            seen.add(e.id)
            result.append(e)
    return sorted(result, key=lambda e: (e.scheduled_time or "", not e.important, e.created))


def get_daily_log(config=None, include_all: bool = False) -> list[Entry]:
    """The Focus Log — what matters today.

    Shows:
    - Tasks with focus_date == today
    - Calendar events for today (created today or scheduled today)
    - All journals created today
    - All notes created today

    When include_all=True, also surfaces items filtered out of the curated
    Focus view: tasks captured today without focus_date, dropped-today tasks,
    and past timed calendar events.
    """
    today = date.today()
    today_entries = load_entries_by_date(today, config)

    result = []
    for e in today_entries:
        if e.type == EntryType.TASK:
            if e.is_recurring():
                continue
            if include_all:
                # Every task captured today, any status
                result.append(e)
            elif e.focus_date == today and e.status == TaskStatus.ACTIVE:
                result.append(e)
        elif e.type == EntryType.CALENDAR:
            # Calendar events created today with no scheduled_date, or scheduled for today
            if e.scheduled_date is None or e.scheduled_date == today:
                result.append(e)
        else:
            # Notes and journals — all of today's
            result.append(e)

    # Also include active tasks with focus_date == today but created on a different day
    from bute.storage import query_and_load
    today_tasks = query_and_load(config, type="task", status="active", focus_date=today.isoformat())
    today_tasks = [e for e in today_tasks if e.created.date() != today and not e.is_recurring()]
    seen = {e.id for e in result}
    for e in today_tasks:
        if e.id not in seen:
            seen.add(e.id)
            result.append(e)

    # Also include active tasks due today or overdue
    due_tasks = query_and_load(config, type="task", status="active", has_due=True)
    due_tasks = [e for e in due_tasks if e.due <= today]
    for e in due_tasks:
        if e.id not in seen:
            seen.add(e.id)
            result.append(e)

    # Also include any entries scheduled for today but created on a different day
    scheduled_today = query_and_load(config, scheduled_date=today.isoformat())
    scheduled_today = [e for e in scheduled_today if e.created.date() != today]
    for e in scheduled_today:
        if e.id not in seen:
            # Skip done/dropped tasks unless include_all
            if e.type == EntryType.TASK and e.status != TaskStatus.ACTIVE and not include_all:
                continue
            seen.add(e.id)
            result.append(e)

    # Include tasks completed today (crossed out for momentum)
    done_today = get_tasks_done_today(config)
    for e in done_today:
        if e.id not in seen:
            seen.add(e.id)
            result.append(e)

    # Include tasks dropped today when showing all
    if include_all:
        dropped_today = get_tasks_dropped_today(config)
        for e in dropped_today:
            if e.id not in seen:
                seen.add(e.id)
                result.append(e)

    # Filter out past timed calendar events — they're noise in the Focus Log
    # Unless include_all, which wants the full picture.
    if not include_all:
        from datetime import datetime
        now = datetime.now().strftime("%H:%M")
        result = [
            e for e in result
            if not (e.type == EntryType.CALENDAR and e.scheduled_time and e.scheduled_time < now)
        ]

    def _daily_sort_key(e):
        """Sort: tasks first (done at bottom), then calendar (timed→untimed), notes, journals.
        Important entries first within each type group."""
        type_order = {
            EntryType.TASK: 0,
            EntryType.CALENDAR: 1,
            EntryType.NOTE: 2,
            EntryType.JOURNAL: 3,
        }
        group = type_order.get(e.type, 4)
        # Done/dropped tasks sink to bottom of their type group
        is_resolved = 1 if e.status in (TaskStatus.DONE, TaskStatus.DROPPED) else 0
        time_key = e.scheduled_time if e.type == EntryType.CALENDAR and e.scheduled_time else ""
        return (group, is_resolved, not e.important, time_key, e.created)

    return sorted(result, key=_daily_sort_key)


def get_week_entries(target_date: date | None = None, config=None) -> list[Entry]:
    """All entries for the week containing target_date.

    Week start is configurable via core.week_start (default Monday).
    Includes all statuses (done, dropped, active) — the full picture.
    """
    from bute.config import week_bounds
    d = target_date or date.today()
    start, end = week_bounds(d, config)
    today = date.today()

    from bute.storage import query_and_load
    entries = query_and_load(config, created_since=start.isoformat(), created_until=min(end, today).isoformat())
    return sorted(entries, key=lambda e: e.created)


def get_tasks_done_today(config=None) -> list[Entry]:
    """Tasks marked done today (completed_date == today)."""
    today = date.today()
    from bute.storage import query_and_load
    return query_and_load(
        config, type="task", status="done", completed_date=today.isoformat()
    )


def get_tasks_dropped_today(config=None) -> list[Entry]:
    """Tasks marked dropped today (completed_date == today)."""
    today = date.today()
    from bute.storage import query_and_load
    return query_and_load(
        config, type="task", status="dropped", completed_date=today.isoformat()
    )


def get_today_captured(config=None) -> list[Entry]:
    """Non-task entries created today (journals, notes, events)."""
    today = date.today()
    entries = load_entries_by_date(today, config)
    return [e for e in entries if e.type != EntryType.TASK]


def get_all_active_tasks(config=None) -> list[Entry]:
    """All active tasks across all dates."""
    from bute.storage import query_and_load
    return query_and_load(config, type="task", status="active")


def get_weekly_active_tasks(config=None) -> list[Entry]:
    """Active tasks selected for this week (week_date == this Monday).

    Falls back to all active tasks if none have week_date set
    (e.g. user hasn't run bt wp yet). Excludes recurring tasks — they have
    their own view (bt streak).
    """
    from bute.storage import query_and_load
    weekly = query_and_load(
        config, type="task", status="active", week_date=this_monday().isoformat()
    )
    weekly = [e for e in weekly if not e.is_recurring()]
    if weekly:
        return weekly
    fallback = get_all_active_tasks(config)
    return [e for e in fallback if not e.is_recurring()]


def process_dump_line(line: str, config=None) -> Entry | None:
    """Parse a dump line and save it. Defaults to j if no signifier.

    Tasks captured during rituals automatically get week_date set to this Monday.
    """
    from bute.parser import SIGNIFIER_RE, WORD_SIGNIFIER_RE

    line = line.strip()
    if not line:
        return None

    # If line doesn't start with a recognized signifier, prepend j
    tokens = line.split()
    first = tokens[0]
    if not (SIGNIFIER_RE.match(first) or WORD_SIGNIFIER_RE.match(first)):
        tokens = ["j"] + tokens

    parsed = parse_capture_tokens(tuple(tokens))

    from bute.models import SIGNIFIER_MAP
    from bute.parser import resolve_date

    entry_type = SIGNIFIER_MAP[parsed.signifier]
    meta = dict(parsed.metadata)
    due = resolve_date(meta.pop("due")) if "due" in meta else None
    scheduled_date = resolve_date(meta.pop("date")) if "date" in meta else None
    scheduled_time = meta.pop("time", None)

    entry = Entry.create(
        entry_type=entry_type,
        body=parsed.body,
        important=parsed.important,
        tags=parsed.tags,
        due=due,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        extra_meta=meta,
    )

    # Set week_date on tasks captured during rituals
    if entry.type == EntryType.TASK:
        entry.week_date = this_monday()

    save_entry(entry, config)
    from bute.ai import embed_entry
    embed_entry(entry.id, entry.body, config)
    return entry


def set_weekly_selection(entry_ids: list[str], config=None) -> int:
    """Set week_date=this_monday on entries. Returns count updated."""
    from bute.storage import entry_path_from_id, load_entry

    monday = this_monday()
    count = 0
    for eid in entry_ids:
        path = entry_path_from_id(eid, config)
        if path is None:
            continue
        entry = load_entry(path)
        if entry.week_date != monday:
            entry.week_date = monday
        update_entry(entry, config)
        count += 1
    return count


def clear_weekly_selection(config=None) -> int:
    """Clear week_date from all entries. Returns count cleared."""
    from bute.storage import query_and_load
    entries = query_and_load(config, has_week_date=True)
    for entry in entries:
        entry.week_date = None
        update_entry(entry, config)
    return len(entries)


def clear_daily_focus(config=None) -> int:
    """Clear focus_date from all entries. Returns count cleared."""
    from bute.storage import query_and_load
    entries = query_and_load(config, has_focus_date=True)
    for entry in entries:
        entry.focus_date = None
        update_entry(entry, config)
    return len(entries)
