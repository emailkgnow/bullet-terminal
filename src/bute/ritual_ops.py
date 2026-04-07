"""Pure query and action functions for rituals."""

from datetime import date, timedelta

from bute.models import Entry, EntryType, TaskStatus
from bute.parser import parse_capture_tokens
from bute.storage import (
    load_entries_by_date,
    save_entry,
    update_entry,
)


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


def get_daily_log(config=None) -> list[Entry]:
    """The Focus Log — what matters today.

    Shows:
    - Tasks tagged @today only
    - Calendar events for today (created today or scheduled today)
    - All journals created today
    - All notes created today
    """
    today = date.today()
    today_entries = load_entries_by_date(today, config)

    result = []
    for e in today_entries:
        if e.type == EntryType.TASK:
            # Only active tasks tagged @today (exclude habits — shown separately)
            if "today" in e.tags and e.status == TaskStatus.ACTIVE and "habit" not in e.tags:
                result.append(e)
        elif e.type == EntryType.CALENDAR:
            # Calendar events created today with no scheduled_date, or scheduled for today
            if e.scheduled_date is None or e.scheduled_date == today:
                result.append(e)
        else:
            # Notes and journals — all of today's
            result.append(e)

    # Also include active tasks tagged @today but created on a different day
    from bute.storage import query_and_load
    today_tasks = query_and_load(config, type="task", status="active", tag="today")
    today_tasks = [e for e in today_tasks if e.created.date() != today and "habit" not in e.tags]
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
            # Skip done/dropped tasks
            if e.type == EntryType.TASK and e.status != TaskStatus.ACTIVE:
                continue
            seen.add(e.id)
            result.append(e)

    # Also include recurring entries that match today (excluding @habit — shown separately)
    recurring = query_and_load(config, has_repeat=True, status="active")
    for e in recurring:
        if e.id not in seen and e.recurs_on(today) and "habit" not in e.tags:
            seen.add(e.id)
            result.append(e)

    # Filter out past timed calendar events — they're noise in the Focus Log
    from datetime import datetime
    now = datetime.now().strftime("%H:%M")
    result = [
        e for e in result
        if not (e.type == EntryType.CALENDAR and e.scheduled_time and e.scheduled_time < now)
    ]

    def _daily_sort_key(e):
        """Sort: tasks first, then calendar (timed→untimed), notes, journals.
        Important entries first within each type group."""
        type_order = {
            EntryType.TASK: 0,
            EntryType.CALENDAR: 1,
            EntryType.NOTE: 2,
            EntryType.JOURNAL: 3,
        }
        group = type_order.get(e.type, 4)
        time_key = e.scheduled_time if e.type == EntryType.CALENDAR and e.scheduled_time else ""
        return (group, not e.important, time_key, e.created)

    return sorted(result, key=_daily_sort_key)


def get_week_entries(target_date: date | None = None, config=None) -> list[Entry]:
    """All entries for the Mon-Sun week containing target_date.

    Includes all statuses (done, dropped, active) — the full picture.
    """
    d = target_date or date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    today = date.today()

    from bute.storage import query_and_load
    entries = query_and_load(config, created_since=monday.isoformat(), created_until=min(sunday, today).isoformat())
    return sorted(entries, key=lambda e: e.created)


def get_tasks_done_today(config=None) -> list[Entry]:
    """Tasks marked done with file mtime today (proxy for status-change date)."""
    today = date.today()
    from bute.storage import entry_path as _entry_path

    from bute.storage import query_and_load
    done = query_and_load(config, type="task", status="done")
    return [
        e for e in done
        if date.fromtimestamp(_entry_path(e, config).stat().st_mtime) == today
    ]


def get_tasks_dropped_today(config=None) -> list[Entry]:
    """Tasks marked dropped with file mtime today."""
    today = date.today()
    from bute.storage import entry_path as _entry_path

    from bute.storage import query_and_load
    dropped = query_and_load(config, type="task", status="dropped")
    return [
        e for e in dropped
        if date.fromtimestamp(_entry_path(e, config).stat().st_mtime) == today
    ]


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
    """Active tasks selected for this week (@thisweek tag).

    Falls back to all active tasks if none are tagged @thisweek
    (e.g. user hasn't run bt wp yet).
    """
    from bute.storage import query_and_load
    weekly = query_and_load(config, type="task", status="active", tag="thisweek")
    if weekly:
        return weekly
    return get_all_active_tasks(config)


def process_dump_line(line: str, config=None, auto_tags: list[str] | None = None) -> Entry | None:
    """Parse a dump line and save it. Defaults to j if no signifier.

    auto_tags: tags to auto-add to task entries (e.g. ["thisweek"]).
    """
    from bute.parser import BULLET_RE, SIGNIFIER_RE, WORD_SIGNIFIER_RE

    line = line.strip()
    if not line:
        return None

    # If line doesn't start with a recognized signifier, prepend j
    tokens = line.split()
    first = tokens[0]
    if not (SIGNIFIER_RE.match(first) or BULLET_RE.match(first) or WORD_SIGNIFIER_RE.match(first)):
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

    # Auto-tag tasks (e.g. @thisweek during rituals)
    if auto_tags and entry.type == EntryType.TASK:
        for tag in auto_tags:
            if tag not in entry.tags:
                entry.tags.append(tag)

    save_entry(entry, config)
    from bute.ai import embed_entry
    embed_entry(entry.id, entry.body, config)
    return entry


def set_weekly_selection(entry_ids: list[str], config=None) -> int:
    """Tag entries with +thisweek. Returns count tagged."""
    from bute.storage import entry_path_from_id, load_entry

    count = 0
    for eid in entry_ids:
        path = entry_path_from_id(eid, config)
        if path is None:
            continue
        entry = load_entry(path)
        if "thisweek" not in entry.tags:
            entry.tags.append("thisweek")
        update_entry(entry, config)
        count += 1
    return count


def clear_weekly_selection(config=None) -> int:
    """Remove +thisweek tag from all entries. Returns count cleared."""
    from bute.storage import query_and_load
    entries = query_and_load(config, tag="thisweek")
    for entry in entries:
        entry.tags.remove("thisweek")
        update_entry(entry, config)
    return len(entries)


def clear_daily_focus(config=None) -> int:
    """Remove +today tag from all entries. Returns count cleared."""
    from bute.storage import query_and_load
    entries = query_and_load(config, tag="today")
    for entry in entries:
        entry.tags.remove("today")
        update_entry(entry, config)
    return len(entries)
