"""Markdown file I/O for bute entries."""

from datetime import date, datetime
from pathlib import Path

import frontmatter

from bute.config import get_data_dir
from bute.models import Entry, EntryType, TaskStatus


def entry_path(entry: Entry, config=None) -> Path:
    """Compute the file path for an entry: ~/bute/entries/YYYY-MM/<ulid>.md"""
    data_dir = get_data_dir(config)
    month_dir = data_dir / "entries" / entry.created.strftime("%Y-%m")
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
    path.write_text(frontmatter.dumps(post))
    return path


def load_entry(path: Path) -> Entry:
    """Read a Markdown file and reconstruct an Entry."""
    post = frontmatter.load(str(path))

    # Known frontmatter keys — everything else goes to extra_meta
    known_keys = {
        "id", "type", "created", "status", "important",
        "due", "date", "time", "repeat", "tags",
    }
    extra_meta = {
        k: v for k, v in post.metadata.items() if k not in known_keys
    }

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
        tags=post.metadata.get("tags", []),
        extra_meta=extra_meta,
    )


def update_entry(entry: Entry, config=None) -> Path:
    """Re-save a modified entry to its existing path."""
    return save_entry(entry, config)


def load_entries_by_date(target_date: date, config=None) -> list[Entry]:
    """Load all entries created on a specific date, sorted chronologically."""
    data_dir = get_data_dir(config)
    month_dir = data_dir / "entries" / target_date.strftime("%Y-%m")
    if not month_dir.exists():
        return []
    entries = []
    for path in month_dir.glob("*.md"):
        entry = load_entry(path)
        if entry.created.date() == target_date and entry.status != TaskStatus.DROPPED:
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
    for month_dir in sorted(entries_dir.iterdir()):
        if not month_dir.is_dir():
            continue
        for path in month_dir.glob("*.md"):
            entry = load_entry(path)
            if predicate(entry):
                entries.append(entry)
    return sorted(entries, key=lambda e: e.created, reverse=True)


def entry_path_from_id(entry_id: str, config=None) -> Path | None:
    """Find an entry file by ULID. Derives month from ULID timestamp."""
    from ulid import ULID

    ulid = ULID.from_str(entry_id)
    ts = ulid.datetime
    data_dir = get_data_dir(config)
    month_dir = data_dir / "entries" / ts.strftime("%Y-%m")
    candidate = month_dir / f"{entry_id}.md"
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
