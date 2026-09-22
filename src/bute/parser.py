"""Input parsing for bt capture commands."""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from bute.errors import InvalidSignifierError
from bute.models import REPEAT_VALUES

SIGNIFIER_RE = re.compile(r"^/?([tnjc])(!?)$")

# Full word to signifier mapping
WORD_TO_SIGNIFIER = {
    "task": "t", "note": "n", "journal": "j", "calendar": "c",
}
WORD_SIGNIFIER_RE = re.compile(r"^(task|note|journal|calendar)(!?)$")
# Key must start with a letter — prevents "1:1" from being parsed as key:value
KV_RE = re.compile(r"^([a-zA-Z]\w*):(.+)$")
TAG_RE = re.compile(r"^@([a-zA-Z0-9_-]+)$")
# Double-duty tag: @@word keeps the word in the body AND records it as a tag.
# Scanned inside tokens (so it survives quoting and glued punctuation); the
# preceding-character guard keeps emails and @@@ runs from matching.
DOUBLE_TAG_RE = re.compile(r"(?<![A-Za-z0-9_@])@@([a-zA-Z0-9_-]+)")

# Month name abbreviations for date parsing
MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
# The hyphen is the only date separator: jan-23, 01-23, 2026-01-23.
MONTH_DAY_RE = re.compile(rf"^({_MONTHS})-(\d{{1,2}})$", re.IGNORECASE)
MONTH_NUM_RE = re.compile(r"^(\d{1,2})-(\d{1,2})$")

# Short metadata keys removed in favour of full words — one spelling per
# concept, matching the frontmatter key each one writes. Kept here so a user
# typing the old spelling gets a pointer instead of silent extra_meta.
REMOVED_META_KEYS = {"d": "date", "t": "time", "r": "repeat"}

DAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]

DAY_ABBR = {
    "mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday",
    "fri": "friday", "sat": "saturday", "sun": "sunday",
}

# Spellings that were accepted once and now point at their replacement, so a
# typed habit fails loudly instead of resolving to something else or nothing.
RETIRED_DATE_WORDS = {
    "tod": "today",
    "tom": "tomorrow", "tmr": "tomorrow", "tmrw": "tomorrow",
}


@dataclass
class ParsedInput:
    """Structured result of parsing capture tokens."""

    signifier: str
    important: bool
    body_words: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        return " ".join(self.body_words)


def _add_tag(tags: list[str], name: str) -> None:
    """Append a tag, normalized to lowercase, skipping duplicates."""
    name = name.lower()
    if name not in tags:
        tags.append(name)


def parse_capture_tokens(tokens: tuple[str, ...] | list[str]) -> ParsedInput:
    """Parse capture input tokens into structured data.

    Args:
        tokens: Raw CLI tokens. First token must be a signifier (/t, /t!, /n, etc.)

    Returns:
        ParsedInput with extracted signifier, body, metadata, and tags.

    Raises:
        InvalidSignifierError: If first token isn't a valid signifier.
    """
    if not tokens:
        raise InvalidSignifierError("No input provided.")

    first = tokens[0]

    # Try short form: t, /t, t!, /t!
    match = SIGNIFIER_RE.match(first)
    if match:
        signifier = f"/{match.group(1)}"
        important = match.group(2) == "!"
    else:
        # Try full word: task, note, journal, calendar, task!, etc.
        word_match = WORD_SIGNIFIER_RE.match(first)
        if word_match:
            letter = WORD_TO_SIGNIFIER[word_match.group(1)]
            signifier = f"/{letter}"
            important = word_match.group(2) == "!"
        else:
            raise InvalidSignifierError(f"Unknown signifier: {first}")

    body_words = []
    metadata = {}
    tags = []

    for token in tokens[1:]:
        tag_match = TAG_RE.match(token)
        if tag_match:
            _add_tag(tags, tag_match.group(1))
            continue

        kv_match = KV_RE.match(token)
        if kv_match:
            key = kv_match.group(1).lower()
            value = kv_match.group(2)
            metadata[key] = value
            continue

        if DOUBLE_TAG_RE.search(token):
            for name in DOUBLE_TAG_RE.findall(token):
                _add_tag(tags, name)
            token = DOUBLE_TAG_RE.sub(r"\1", token)

        body_words.append(token)

    return ParsedInput(
        signifier=signifier,
        important=important,
        body_words=body_words,
        metadata=metadata,
        tags=tags,
    )


TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*(am|pm)?$", re.IGNORECASE)


def _time_hint(raw: str) -> str:
    """Build an error that names the replacement for a retired time spelling."""
    low = raw.strip().lower()
    bare = re.match(r"^(\d{1,2})$", low)
    if bare:
        return f"Invalid time: {raw}. Minutes are required — use {bare.group(1)}:00."
    bare_suffix = re.match(r"^(\d{1,2})\s*(am|pm)$", low)
    if bare_suffix:
        h, period = bare_suffix.groups()
        return f"Invalid time: {raw}. Minutes are required — use {h}:00{period}."
    dot = re.match(r"^(\d{1,2})\.(\d{2})\s*(am|pm)?$", low)
    if dot:
        h, m, period = dot.group(1), dot.group(2), dot.group(3) or ""
        return f"Invalid time: {raw}. Use ':' not '.' — {h}:{m}{period}."
    four = re.match(r"^(\d{2})(\d{2})$", low)
    if four:
        return f"Invalid time: {raw}. Use HH:MM — {four.group(1)}:{four.group(2)}."
    return f"Invalid time: {raw}. Use HH:MM (24-hour), or HH:MM with am/pm."


def resolve_time(value: str) -> str:
    """Resolve a time to the stored HH:MM 24-hour form.

    HH:MM is read as 24-hour unless an am/pm suffix is given, and minutes are
    always required:

        "14:30" → "14:30"    "9:00" → "09:00"
        "9:00pm" → "21:00"   "2:20PM" → "14:20"

    Input is case-insensitive. The hour must be 0-23 without a suffix and 1-12
    with one, so "13:00pm" is an error rather than a guess.
    """
    raw = value.strip()
    match = TIME_RE.match(raw)
    if not match:
        raise ValueError(_time_hint(raw))

    hour, minute = int(match.group(1)), int(match.group(2))
    period = (match.group(3) or "").lower()

    if minute > 59:
        raise ValueError(f"Invalid time: {raw}. Minutes must be 00-59.")

    if period:
        if not 1 <= hour <= 12:
            raise ValueError(
                f"Invalid time: {raw}. With {period}, the hour must be 1-12."
            )
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        raise ValueError(f"Invalid time: {raw}. Hours must be 00-23.")

    return f"{hour:02d}:{minute:02d}"


def format_time_display(time_24: str) -> str:
    """Convert 24h time (HH:MM) to display format (h:MM AM/PM).

    "14:30" → "2:30 PM", "09:00" → "9:00 AM"
    """
    try:
        parts = time_24.split(":")
        h, m = int(parts[0]), int(parts[1])
        period = "AM" if h < 12 else "PM"
        display_h = h % 12 or 12
        return f"{display_h}:{m:02d} {period}"
    except (ValueError, IndexError):
        return time_24


def _next_occurrence(ref: date, month: int, day: int, raw: str) -> date:
    """The next month/day on or after ref, rolling into next year if it's past."""
    for year in (ref.year, ref.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            raise ValueError(f"Invalid date: {raw}. No such day.")
        if candidate >= ref:
            return candidate
    raise ValueError(f"Invalid date: {raw}.")


def _date_hint(raw: str) -> str:
    """Build an error that names the replacement for a retired date spelling."""
    low = raw.strip().lower()
    if low in RETIRED_DATE_WORDS:
        return f"Invalid date: {raw}. Use '{RETIRED_DATE_WORDS[low]}'."
    if re.match(r"^next[- .]?[a-z]+$", low):
        return (
            f"Invalid date: {raw}. 'next-<day>' was removed because English "
            "disagrees about what it means — use a weekday, jan-23, or 2026-01-23."
        )
    dot = re.match(r"^(\d{1,2})\.(\d{1,2})$", low)
    if dot:
        m, d = int(dot.group(1)), int(dot.group(2))
        return f"Invalid date: {raw}. Use '-' not '.' — {m:02d}-{d:02d}."
    slash = re.match(r"^(\d{1,2})/(\d{1,2})$", low)
    if slash:
        m, d = int(slash.group(1)), int(slash.group(2))
        return f"Invalid date: {raw}. Use '-' not '/' — {m:02d}-{d:02d}."
    four = re.match(r"^(\d{2})(\d{2})$", low)
    if four:
        return f"Invalid date: {raw}. Use MM-DD — {four.group(1)}-{four.group(2)}."
    glued = re.match(rf"^({_MONTHS})[ ]?(\d{{1,2}})$", low)
    if glued:
        return (
            f"Invalid date: {raw}. The hyphen is required — "
            f"use {glued.group(1)}-{int(glued.group(2)):02d}."
        )
    return (
        f"Invalid date: {raw}. Use today, tomorrow, a weekday, "
        "jan-23, 01-23, or 2026-01-23."
    )


def resolve_date(value: str, reference: date | None = None) -> date:
    """Resolve a date string to a date.

    Four forms, all case-insensitive, with the hyphen as the only separator:

        today, tomorrow                relative words
        friday / fri                   the next such weekday
        jan-23  /  01-23               the next such month/day, rolling a year
        2026-01-23                     full ISO — exact, never rolls

    Everything but full ISO resolves forward, so a month/day that has already
    passed this year means next year's. Use ISO to name a date in the past.
    """
    ref = reference or date.today()
    low = value.strip().lower()

    if low == "today":
        return ref
    if low == "tomorrow":
        return ref + timedelta(days=1)

    # Weekday, full or three-letter — always the *next* such day, never today
    day_name = DAY_ABBR.get(low, low)
    if day_name in DAY_NAMES:
        delta = (DAY_NAMES.index(day_name) - ref.weekday()) % 7
        return ref + timedelta(days=delta or 7)

    # jan-23
    month_match = MONTH_DAY_RE.match(low)
    if month_match:
        month = MONTH_ABBR[month_match.group(1).lower()]
        return _next_occurrence(ref, month, int(month_match.group(2)), value)

    # 01-23 — the ISO tail, same month-day order as full ISO
    num_match = MONTH_NUM_RE.match(low)
    if num_match:
        month, day = int(num_match.group(1)), int(num_match.group(2))
        if not 1 <= month <= 12:
            raise ValueError(f"Invalid date: {value}. Month must be 01-12.")
        return _next_occurrence(ref, month, day, value)

    # Full ISO
    try:
        return date.fromisoformat(low)
    except ValueError:
        raise ValueError(_date_hint(value))


def resolve_repeat(value: str) -> str:
    """Validate a recurrence rule, returning it lowercased.

    Only the four rules ``Entry.recurs_on`` understands are accepted — an
    unrecognised rule used to save fine and then silently never fire.
    """
    low = str(value).lower().strip()
    if low not in REPEAT_VALUES:
        allowed = " | ".join(sorted(REPEAT_VALUES))
        raise ValueError(f"Invalid repeat: {value}. Use: {allowed}")
    return low


def check_due_is_task_only(entry_type: str, meta: dict) -> None:
    """Raise if due: is set on a non-task — no view reads it there.

    An empty or 'none' value is a clear, not a set, so it stays allowed.
    """
    raw = meta.get("due")
    if entry_type == "task" or not raw or raw.lower() == "none":
        return
    raise ValueError(
        f"'due:' is a task deadline — use 'date:' to schedule a {entry_type} "
        f"(e.g. date:{raw})."
    )


def check_removed_meta_keys(meta: dict) -> None:
    """Raise if a removed short key (d:/t:/r:) was used, naming its replacement."""
    for short, full in REMOVED_META_KEYS.items():
        if short in meta:
            raise ValueError(
                f"'{short}:' was removed — use '{full}:' instead "
                f"(e.g. {full}:{meta[short] or 'friday'})."
            )
