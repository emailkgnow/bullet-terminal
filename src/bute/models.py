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
SYSTEM_TAGS = {"goal", "habit"}


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
    focus_date: Optional[date] = None
    week_date: Optional[date] = None
    completed_date: Optional[date] = None
    tags: list[str] = field(default_factory=list)
    extra_meta: dict = field(default_factory=dict)
    completions: list[str] = field(default_factory=list)

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
        focus_date: date | None = None,
        week_date: date | None = None,
        completed_date: date | None = None,
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
            focus_date=focus_date,
            week_date=week_date,
            completed_date=completed_date,
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
        if self.focus_date is not None:
            d["focus_date"] = self.focus_date.isoformat()
        if self.week_date is not None:
            d["week_date"] = self.week_date.isoformat()
        if self.completed_date is not None:
            d["completed_date"] = self.completed_date.isoformat()
        if self.tags:
            d["tags"] = self.tags
        if self.extra_meta:
            d.update(self.extra_meta)
        if self.completions:
            d["completions"] = self.completions
        return d

    def is_recurring(self) -> bool:
        """Check if this entry has a recurrence rule."""
        return self.repeat is not None

    def is_completed_for_date(self, target: date) -> bool:
        """Check if this recurring entry was completed for a given date."""
        return target.isoformat() in self.completions

    def recurs_on(self, target: date) -> bool:
        """Check if this recurring entry should show on the given date."""
        if not self.repeat:
            return False
        anchor = self.scheduled_date or self.created.date()
        if self.repeat == "daily":
            return True
        elif self.repeat == "weekly":
            return target.weekday() == anchor.weekday()
        elif self.repeat == "monthly":
            return target.day == anchor.day
        elif self.repeat == "yearly":
            return target.month == anchor.month and target.day == anchor.day
        return False
