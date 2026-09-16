"""Markdown file I/O for bt entries."""

from datetime import date, datetime
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
    """Coerce each tag to a plain string.

    Handles malformed frontmatter where a tag entry is a dict
    (e.g. ``- vacation: true``) instead of a bare scalar.
    """
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.extend(str(k) for k in item)
        else:
            result.append(str(item))
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
        created=datetime.fromisoformat(post["created"]),
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
    """Find an entry file by ULID. Checks all type dirs for the entry."""
    from ulid import ULID

    ulid = ULID.from_str(entry_id)
    ts = ulid.datetime
    data_dir = get_data_dir(config)
    month = ts.strftime("%Y-%m")
    for type_name in ENTRY_TYPE_DIRS:
        candidate = data_dir / "entries" / type_name / month / f"{entry_id}.md"
        if candidate.exists():
            return candidate
    return None


def _normalize_time(value) -> str | None:
    """Normalize stored time to HH:MM format."""
    if value is None:
        return None
    from bute.parser import resolve_time
    return resolve_time(str(value))


def _parse_status(value) -> TaskStatus | None:
    """Parse status, treating legacy 'migrated' as 'active'."""
    if value is None:
        return None
    if value == "migrated":
        return TaskStatus.ACTIVE
    return TaskStatus(value)


def _parse_date(value) -> date | None:
    """Parse a date from frontmatter — could be a date object or ISO string."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


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
    try:
        from bute.ai.vectors import is_available, delete as vec_delete
        if is_available():
            vec_delete(entry_id, config)
    except Exception:
        pass
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
