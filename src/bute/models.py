"""Entry data models for bt."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from ulid import ULID


def compact_date_runs(dates: list[str]) -> list[str]:
    """Run-length-encode a list of ISO dates into ranges.

    Consecutive dates collapse to "YYYY-MM-DD..YYYY-MM-DD"; isolated dates
    stay as "YYYY-MM-DD". Input may be unsorted or contain duplicates;
    output is always sorted with unique days.
    """
    if not dates:
        return []
    sorted_dates = sorted({str(d) for d in dates})
    runs: list[str] = []
    run_start = sorted_dates[0]
    prev = run_start
    for current in sorted_dates[1:]:
        if (date.fromisoformat(current) - date.fromisoformat(prev)).days == 1:
            prev = current
            continue
        runs.append(run_start if run_start == prev else f"{run_start}..{prev}")
        run_start = current
        prev = current
    runs.append(run_start if run_start == prev else f"{run_start}..{prev}")
    return runs


def expand_date_runs(runs: list) -> list[str]:
    """Expand RLE-encoded date ranges back into a sorted flat list of ISO dates.

    Accepts both "YYYY-MM-DD" and "YYYY-MM-DD..YYYY-MM-DD" forms. Duplicate
    days across runs collapse to one. A plain legacy list of dates (no
    ".." ranges) round-trips unchanged.
    """
    if not runs:
        return []
    days: set[str] = set()
    for run in runs:
        text = str(run).strip()
        if ".." in text:
            start_s, end_s = text.split("..", 1)
            start = date.fromisoformat(start_s.strip())
            end = date.fromisoformat(end_s.strip())
            current = start
            while current <= end:
                days.add(current.isoformat())
                current += timedelta(days=1)
        else:
            date.fromisoformat(text)  # validate
            days.add(text)
    return sorted(days)


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
# @habit drives bt streak; hidden from default tag rendering.
SYSTEM_TAGS = {"habit"}


@dataclass
class Entry:
    """A single bt entry — task, note, journal, or calendar event."""

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
        entry = cls(
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
        return entry

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
            d["completions"] = compact_date_runs(self.completions)
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
