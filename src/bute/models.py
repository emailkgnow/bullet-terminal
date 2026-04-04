"""Entry data models for bute."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from ulid import ULID


class EntryType(str, Enum):
    TASK = "task"
    NOTE = "note"
    JOURNAL = "journal"
    CALENDAR = "calendar"


class TaskStatus(str, Enum):
    ACTIVE = "active"
    DONE = "done"
    DROPPED = "dropped"


# Map CLI signifier to entry type
SIGNIFIER_MAP = {
    "/t": EntryType.TASK,
    "/n": EntryType.NOTE,
    "/j": EntryType.JOURNAL,
    "/c": EntryType.CALENDAR,
}

# Tags that bt interprets as instructions, not labels.
# Used by goals view to filter connected tags.
SYSTEM_TAGS = frozenset({"goal", "today", "thisweek"})


@dataclass
class Entry:
    """A single bute entry — task, note, journal, or calendar event."""

    id: str
    type: EntryType
    body: str
    created: datetime
    status: Optional[TaskStatus] = None
    important: bool = False
    due: Optional[date] = None
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[str] = None
    repeat: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    extra_meta: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        entry_type: EntryType,
        body: str,
        important: bool = False,
        tags: list[str] | None = None,
        due: date | None = None,
        scheduled_date: date | None = None,
        scheduled_time: str | None = None,
        repeat: str | None = None,
        extra_meta: dict | None = None,
    ) -> "Entry":
        """Factory that generates a ULID and sets the created timestamp."""
        now = datetime.now(timezone.utc).astimezone()
        return cls(
            id=str(ULID()),
            type=entry_type,
            body=body,
            created=now,
            status=TaskStatus.ACTIVE if entry_type == EntryType.TASK else None,
            important=important,
            due=due,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            repeat=repeat,
            tags=tags or [],
            extra_meta=extra_meta or {},
        )

    def to_frontmatter_dict(self) -> dict:
        """Convert to dict for YAML frontmatter. Omits None/empty values."""
        d: dict = {
            "id": self.id,
            "type": self.type.value,
            "created": self.created.isoformat(),
        }
        if self.status is not None:
            d["status"] = self.status.value
        if self.important:
            d["important"] = True
        if self.due is not None:
            d["due"] = self.due.isoformat()
        if self.scheduled_date is not None:
            d["date"] = self.scheduled_date.isoformat()
        if self.scheduled_time is not None:
            d["time"] = self.scheduled_time
        if self.repeat is not None:
            d["repeat"] = self.repeat
        if self.tags:
            d["tags"] = self.tags
        if self.extra_meta:
            d.update(self.extra_meta)
        return d
