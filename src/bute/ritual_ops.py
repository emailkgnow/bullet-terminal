"""Pure query and action functions for rituals."""

from datetime import date, timedelta

from bute.models import Entry, EntryType, TaskStatus
from bute.parser import parse_capture_tokens
from bute.storage import (
    load_entries_by_date,
    load_entries_by_filter,
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
    scheduled_today = load_entries_by_filter(
        lambda e: (
            e.type == EntryType.CALENDAR
            and e.scheduled_date == today
            and e.created.date() != today
        ),
        config,
    )

    # Combine and deduplicate by ID
    seen = set()
    result = []
    for e in today_calendar + scheduled_today:
        if e.id not in seen:
            seen.add(e.id)
            result.append(e)
    return sorted(result, key=lambda e: (e.scheduled_time or "", e.created))


def get_daily_log(config=None) -> list[Entry]:
    """The daily log — today's focus view.

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
            # Only tasks tagged @today
            if "today" in e.tags:
                result.append(e)
        elif e.type == EntryType.CALENDAR:
            # Calendar events created today with no scheduled_date, or scheduled for today
            if e.scheduled_date is None or e.scheduled_date == today:
                result.append(e)
        else:
            # Notes and journals — all of today's
            result.append(e)

    # Also include tasks tagged @today but created on a different day
    today_tasks = load_entries_by_filter(
        lambda e: (
            e.type == EntryType.TASK
            and "today" in e.tags
            and e.created.date() != today
        ),
        config,
    )
    seen = {e.id for e in result}
    for e in today_tasks:
        if e.id not in seen:
            seen.add(e.id)
            result.append(e)

    # Also include calendar events scheduled for today but created on a different day
    scheduled_today = load_entries_by_filter(
        lambda e: (
            e.type == EntryType.CALENDAR
            and e.scheduled_date == today
            and e.created.date() != today
        ),
        config,
    )
    for e in scheduled_today:
        if e.id not in seen:
            seen.add(e.id)
            result.append(e)

    def _daily_sort_key(e):
        """Sort: timed events first (by time), then everything else by creation."""
        if e.type == EntryType.CALENDAR and e.scheduled_time:
            return (0, e.scheduled_time, e.created)
        if e.type == EntryType.CALENDAR:
            return (1, "", e.created)
        return (2, "", e.created)

    return sorted(result, key=_daily_sort_key)


def get_tasks_done_today(config=None) -> list[Entry]:
    """Tasks marked done with file mtime today (proxy for status-change date)."""
    today = date.today()
    from bute.storage import entry_path as _entry_path

    done = load_entries_by_filter(
        lambda e: e.type == EntryType.TASK and e.status == TaskStatus.DONE,
        config,
    )
    return [
        e for e in done
        if date.fromtimestamp(_entry_path(e, config).stat().st_mtime) == today
    ]


def get_tasks_dropped_today(config=None) -> list[Entry]:
    """Tasks marked dropped with file mtime today."""
    today = date.today()
    from bute.storage import entry_path as _entry_path

    dropped = load_entries_by_filter(
        lambda e: e.type == EntryType.TASK and e.status == TaskStatus.DROPPED,
        config,
    )
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
    return load_entries_by_filter(
        lambda e: e.type == EntryType.TASK and e.status == TaskStatus.ACTIVE,
        config,
    )


def get_weekly_active_tasks(config=None) -> list[Entry]:
    """Active tasks selected for this week (@thisweek tag).

    Falls back to all active tasks if none are tagged @thisweek
    (e.g. user hasn't run bt wp yet).
    """
    weekly = load_entries_by_filter(
        lambda e: (
            e.type == EntryType.TASK
            and e.status == TaskStatus.ACTIVE
            and "thisweek" in e.tags
        ),
        config,
    )
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
    entries = load_entries_by_filter(
        lambda e: "thisweek" in e.tags,
        config,
    )
    for entry in entries:
        entry.tags.remove("thisweek")
        update_entry(entry, config)
    return len(entries)


def clear_daily_focus(config=None) -> int:
    """Remove +today tag from all entries. Returns count cleared."""
    entries = load_entries_by_filter(
        lambda e: "today" in e.tags,
        config,
    )
    for entry in entries:
        entry.tags.remove("today")
        update_entry(entry, config)
    return len(entries)
