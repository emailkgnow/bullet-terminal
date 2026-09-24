"""Markdown file I/O for bt entries."""

import re
from datetime import date, datetime, time
from pathlib import Path

import frontmatter

from bute.config import get_data_dir
from bute.fsutil import atomic_write_text
from bute.models import Entry, EntryType, TaskStatus, expand_date_runs


def entry_path(entry: Entry, config=None) -> Path:
    """Compute the file path for an entry: entries/{type}/YYYY-MM/<ulid>.md"""
    data_dir = get_data_dir(config)
    month_dir = data_dir / "entries" / entry.type.value / entry.created.strftime("%Y-%m")
    filename = f"{entry.id}.md"
    return month_dir / filename


def save_entry(entry: Entry, config=None) -> Path:
    """Write an entry to disk as a Markdown file with YAML frontmatter."""
    path = entry_path(entry, config)
    path.parent.mkdir(parents=True, exist_ok=True)

    post = frontmatter.Post(
        content=entry.body,
        **entry.to_frontmatter_dict(),
    )
    atomic_write_text(path, frontmatter.dumps(post))

    # Write-through to SQLite index
    try:
        from bute.db import upsert_entry
        upsert_entry(entry, config)
    except Exception:
        import logging
        logging.getLogger(__name__).debug(
            "Index write failed for %s", entry.id[:8], exc_info=True
        )

    return path


def _normalize_tags(raw: list) -> list[str]:
    """Coerce each tag to a lowercase plain string.

    Handles malformed frontmatter where a tag entry is a dict
    (e.g. ``- vacation: true``) instead of a bare scalar. Lowercasing here
    covers files written directly by external agents (BYOAI), so a tag can
    never split into ``Elham``/``elham`` variants.
    """
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            result.append(item.lower())
        elif isinstance(item, dict):
            result.extend(str(k).lower() for k in item)
        else:
            result.append(str(item).lower())
    return result


def load_entry(path: Path) -> Entry:
    """Read a Markdown file and reconstruct an Entry."""
    post = frontmatter.load(str(path))

    # Known frontmatter keys — everything else goes to extra_meta.
    # "events" is accepted (dropped) for back-compat with legacy .md files
    # written before the event log was removed.
    known_keys = {
        "id", "type", "created", "status", "important",
        "due", "date", "time", "repeat", "tags", "completions",
        "focus_date", "week_date", "completed_date", "events",
    }
    extra_meta = {
        k: v for k, v in post.metadata.items() if k not in known_keys
    }

    raw_completions = post.metadata.get("completions", [])
    completions = expand_date_runs(raw_completions) if raw_completions else []

    return Entry(
        id=post["id"],
        type=EntryType(post["type"]),
        body=post.content.strip(),
        created=_parse_created(post["created"]),
        status=_parse_status(post.metadata.get("status")),
        important=post.metadata.get("important", False),
        due=_parse_date(post.metadata.get("due")),
        scheduled_date=_parse_date(post.metadata.get("date")),
        scheduled_time=_normalize_time(post.metadata.get("time")),
        repeat=post.metadata.get("repeat"),
        focus_date=_parse_date(post.metadata.get("focus_date")),
        week_date=_parse_date(post.metadata.get("week_date")),
        completed_date=_parse_date(post.metadata.get("completed_date")),
        tags=_normalize_tags(post.metadata.get("tags", [])),
        extra_meta=extra_meta,
        completions=completions,
    )


def update_entry(entry: Entry, config=None) -> Path:
    """Re-save a modified entry to its existing path."""
    return save_entry(entry, config)


ENTRY_TYPE_DIRS = ["task", "note", "journal", "calendar"]


def load_entries_by_date(target_date: date, config=None) -> list[Entry]:
    """Load all entries created on a specific date, sorted chronologically."""
    data_dir = get_data_dir(config)
    month = target_date.strftime("%Y-%m")
    entries = []
    for type_name in ENTRY_TYPE_DIRS:
        month_dir = data_dir / "entries" / type_name / month
        if not month_dir.exists():
            continue
        for path in month_dir.glob("*.md"):
            entry = load_entry(path)
            if entry.created.date() == target_date:
                entries.append(entry)
    return sorted(entries, key=lambda e: e.created)


def load_entries_by_filter(
    predicate: "Callable[[Entry], bool]", config=None
) -> list[Entry]:
    """Load all entries matching a predicate, sorted newest first."""
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return []
    entries = []
    for type_name in ENTRY_TYPE_DIRS:
        type_dir = entries_dir / type_name
        if not type_dir.exists():
            continue
        for month_dir in sorted(type_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for path in month_dir.glob("*.md"):
                entry = load_entry(path)
                if predicate(entry):
                    entries.append(entry)
    return sorted(entries, key=lambda e: e.created, reverse=True)


def query_and_load(config=None, sort_key=None, reverse=False, **kwargs) -> list[Entry]:
    """Query the SQLite index and load matched entries from .md files.

    Falls back to load_entries_by_filter if the DB is unavailable.
    Keyword args are passed to db.query_entries().

    Reconciles the index with the entries/ directory on first call per
    process so externally-added .md files (e.g., from a BYOAI agent) are
    picked up without requiring `bt rebuild`.
    """
    try:
        from bute.db import query_entries, reconcile_index
        reconcile_index(config)
        results = query_entries(config=config, **kwargs)
    except Exception:
        import logging
        logging.getLogger(__name__).debug("DB query failed, falling back to file scan", exc_info=True)
        return load_entries_by_filter(lambda e: True, config)

    entries = []
    for entry_id, _ in results:
        path = entry_path_from_id(entry_id, config)
        if path:
            try:
                entries.append(load_entry(path))
            except Exception:
                continue
    if sort_key:
        entries.sort(key=sort_key, reverse=reverse)
    return entries


def entry_path_from_id(entry_id: str, config=None) -> Path | None:
    """Find an entry file by ULID. Checks all type dirs for the entry.

    The ULID's timestamp is UTC, but save_entry files by the local month of
    `created`. Near midnight on the 1st those differ by a month either way
    (UTC+3 at 01:30 Oct 1 is Sep 30 UTC), so the UTC month is probed first,
    then its neighbours.
    """
    from ulid import ULID

    ts = ULID.from_str(entry_id).datetime
    data_dir = get_data_dir(config)
    for month in _months_around(ts.year, ts.month):
        for type_name in ENTRY_TYPE_DIRS:
            candidate = data_dir / "entries" / type_name / month / f"{entry_id}.md"
            if candidate.exists():
                return candidate
    return None


def _months_around(year: int, month: int) -> list[str]:
    """['YYYY-MM'] for the given month, then the next and the previous one."""
    def fmt(y: int, m: int) -> str:
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        return f"{y:04d}-{m:02d}"

    return [fmt(year, month), fmt(year, month + 1), fmt(year, month - 1)]


_READ_TIME_RE = re.compile(r"^(\d{1,2})[:.]?(\d{2})\s*(am|pm)?$", re.IGNORECASE)
_READ_HOUR_RE = re.compile(r"^(\d{1,2})\s*(am|pm)?$", re.IGNORECASE)


def _normalize_time(value) -> str | None:
    """Read a stored time into the canonical HH:MM, tolerantly.

    Reading is deliberately looser than the CLI input grammar and does not
    call resolve_time(): the input grammar is opinionated and changes, while
    files on disk are forever, and a file must never become unreadable because
    the CLI tightened. bt always writes a quoted ``'HH:MM'``; everything else
    here exists for files written by hand or by an external agent (BYOAI).

    Two cases are worth naming:
      - an *unquoted* ``time: 14:30`` is sexagesimal in YAML 1.1, so it
        arrives as the integer 870 and is converted back;
      - retired input spellings (``3pm``, ``14.30``, ``1430``) still read.

    Anything unrecognisable returns None rather than raising, so one bad field
    cannot hide the whole entry from every view.
    """
    if value is None:
        return None

    # YAML sexagesimal: unquoted "14:30" parses as 14*60+30
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if 0 <= value < 24 * 60:
            return f"{value // 60:02d}:{value % 60:02d}"
        return None
    if isinstance(value, time):
        return f"{value.hour:02d}:{value.minute:02d}"

    raw = str(value).strip()
    match = _READ_TIME_RE.match(raw) or _READ_HOUR_RE.match(raw)
    if not match:
        return None

    groups = match.groups()
    hour = int(groups[0])
    minute = int(groups[1]) if len(groups) == 3 and groups[1] else 0
    period = (groups[-1] or "").lower()

    if minute > 59:
        return None
    if period:
        if not 1 <= hour <= 12:
            return None
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        return None
    return f"{hour:02d}:{minute:02d}"


def _parse_status(value) -> TaskStatus | None:
    """Parse status, treating legacy 'migrated' as 'active'."""
    if value is None:
        return None
    if value == "migrated":
        return TaskStatus.ACTIVE
    return TaskStatus(value)


def _parse_date(value) -> date | None:
    """Parse a date from frontmatter — could be a date object or ISO string.

    An unquoted value with a time (`due: 2026-10-02T17:00:00`) arrives from YAML
    as a datetime, which is a date subclass that can't be compared with one, so
    it is cut down to its date.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _parse_created(value) -> datetime:
    """Parse `created` whichever form it arrives in.

    bt writes a quoted ISO string, but a file written by an external agent may
    leave it unquoted, and YAML then hands over a datetime (or a date, if there
    is no time). An offset is converted to local time and dropped, since every
    other `created` bt compares and sorts against is naive local time.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


# ---------------------------------------------------------------------------
# Trash — delete moves files here; restore moves them back
# ---------------------------------------------------------------------------


def trash_dir(config=None) -> Path:
    """Return the trash folder: <data_dir>/.trash (beside entries/, never inside)."""
    return get_data_dir(config) / ".trash"


def trash_entry(entry_id: str, config=None) -> Path | None:
    """Move an entry's .md file into .trash/ and drop it from the index.

    Returns the new path, or None if the entry file does not exist.
    Raises DwnError if a trashed copy of this ULID already exists — never
    silently clobbers an older trashed file.
    """
    import shutil

    from bute.errors import DwnError

    src = entry_path_from_id(entry_id, config)
    if src is None:
        return None
    dest_dir = trash_dir(config)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{entry_id}.md"
    if dest.exists():
        raise DwnError(
            f"A trashed copy of {entry_id[:8]} already exists at {dest}. "
            "Restore or empty the trash before deleting it again."
        )
    shutil.move(str(src), str(dest))
    try:
        from bute.db import delete_entry
        delete_entry(entry_id, config)
    except Exception:
        import logging
        logging.getLogger(__name__).debug("Index delete failed for %s", entry_id[:8], exc_info=True)
    return dest


def restore_entry(entry_id: str, config=None) -> Entry:
    """Move a trashed entry back to entries/{type}/YYYY-MM/ and re-index it.

    Raises DwnError if the entry is not in the trash, or if a live file
    already occupies the destination path (never silently overwritten).
    """
    import shutil

    from bute.errors import DwnError

    src = trash_dir(config) / f"{entry_id}.md"
    if not src.exists():
        raise DwnError(f"Entry {entry_id[:8]} is not in the trash.")
    entry = load_entry(src)
    dest = entry_path(entry, config)
    if dest.exists():
        raise DwnError(f"{entry_id[:8]} already exists at {dest} — remove it first.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    try:
        from bute.db import upsert_entry
        upsert_entry(entry, config)
    except Exception:
        import logging
        logging.getLogger(__name__).debug("Index write failed for %s", entry_id[:8], exc_info=True)
    return entry


def list_trash(config=None) -> list[Entry]:
    """Load every trashed entry, newest-trashed (file mtime) first."""
    folder = trash_dir(config)
    if not folder.exists():
        return []
    paths = sorted(folder.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    entries: list[Entry] = []
    for path in paths:
        try:
            entries.append(load_entry(path))
        except Exception:
            continue
    return entries
