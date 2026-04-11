"""Input parsing for bute capture commands."""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from bute.errors import InvalidSignifierError

SIGNIFIER_RE = re.compile(r"^/?([tnjc])(!?)$")

# Bullet signifier mapping: . = task, = = journal, - = note, o = calendar
BULLET_TO_SIGNIFIER = {".": "t", "=": "j", "-": "n", "o": "c"}
BULLET_RE = re.compile(r"^([.=\-o])(!?)$")

# Full word to signifier mapping
WORD_TO_SIGNIFIER = {
    "task": "t", "note": "n", "journal": "j", "calendar": "c",
}
WORD_SIGNIFIER_RE = re.compile(r"^(task|note|journal|calendar)(!?)$")
# Key must start with a letter — prevents "1:1" from being parsed as key:value
KV_RE = re.compile(r"^([a-zA-Z]\w*):(.+)$")
TAG_RE = re.compile(r"^@([a-zA-Z0-9_-]+)$")

# Month name abbreviations for date parsing
MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

MONTH_DAY_RE = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[- ]?(\d{1,2})$",
    re.IGNORECASE,
)
SLASH_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})$")

DAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]

DAY_ABBR = {
    "mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday",
    "fri": "friday", "sat": "saturday", "sun": "sunday",
}

DATE_ALIASES = {
    "tom": "tomorrow", "tmr": "tomorrow", "tmrw": "tomorrow",
    "tod": "today",
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
        # Try bullet form: . = - o (with optional !)
        bullet_match = BULLET_RE.match(first)
        if bullet_match:
            letter = BULLET_TO_SIGNIFIER[bullet_match.group(1)]
            signifier = f"/{letter}"
            important = bullet_match.group(2) == "!"
        else:
            # Try full word: task, note, journal, cal, task!, etc.
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
            tags.append(tag_match.group(1))
            continue

        kv_match = KV_RE.match(token)
        if kv_match:
            key = kv_match.group(1).lower()
            value = kv_match.group(2)
            metadata[key] = value
            continue

        body_words.append(token)

    return ParsedInput(
        signifier=signifier,
        important=important,
        body_words=body_words,
        metadata=metadata,
        tags=tags,
    )


def resolve_time(value: str) -> str:
    """Resolve time input to normalized HH:MM 24h format.

    Supports:
    - H or HH (hour only): "9" → "09:00", "14" → "14:00"
    - H.MM or HH.MM (dot separator): "9.30" → "09:30", "14.15" → "14:15"
    - Legacy HHMM (4 digits): "1430" → "14:30"
    - Legacy HH:MM: "14:30" → "14:30"
    - Legacy am/pm: "3pm" → "15:00"
    """
    value = value.strip().lower()

    # Dot separator: H.MM or HH.MM
    dot_match = re.match(r"^(\d{1,2})\.(\d{2})$", value)
    if dot_match:
        h, m = int(dot_match.group(1)), int(dot_match.group(2))
        if h > 23 or m > 59:
            raise ValueError(f"Invalid time: {value}")
        return f"{h:02d}:{m:02d}"

    # Hour only: "9", "14"
    if re.match(r"^\d{1,2}$", value) and int(value) < 24:
        return f"{int(value):02d}:00"

    # Legacy: 4-digit HHMM
    if re.match(r"^\d{4}$", value):
        h, m = int(value[:2]), int(value[2:])
        if h > 23 or m > 59:
            raise ValueError(f"Invalid time: {value}")
        return f"{h:02d}:{m:02d}"

    # Legacy: HH:MM
    if re.match(r"^\d{1,2}:\d{2}$", value):
        h, m = value.split(":")
        h, m = int(h), int(m)
        if h > 23 or m > 59:
            raise ValueError(f"Invalid time: {value}")
        return f"{h:02d}:{m:02d}"

    # Legacy: "3pm", "3:30pm", "11am", "12:30am"
    legacy = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", value)
    if legacy:
        h = int(legacy.group(1))
        m = int(legacy.group(2) or 0)
        period = legacy.group(3)
        if h < 1 or h > 12:
            raise ValueError(f"Invalid time: {value}")
        if m > 59:
            raise ValueError(f"Invalid time: {value}")
        if period == "pm" and h != 12:
            h += 12
        elif period == "am" and h == 12:
            h = 0
        return f"{h:02d}:{m:02d}"

    # No format matched — input is invalid
    raise ValueError(f"Invalid time: {value}")


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


def resolve_date(value: str, reference: date | None = None) -> date:
    """Resolve a date string to a date object.

    Supports:
    - MM.DD (dot separator): "01.03" → Jan 3, "12.25" → Dec 25
    - "today", "tomorrow"
    - Day names: "monday", "friday"
    - Month+day: "mar3", "jan15"
    - Legacy MMDD (4 digits): "0330" → Mar 30
    - Legacy slash: "3/29"
    - ISO format: "2026-03-29"
    """
    ref = reference or date.today()
    low = value.lower().strip()

    # Expand aliases and abbreviations
    if low in DATE_ALIASES:
        low = DATE_ALIASES[low]
    if low in DAY_ABBR:
        low = DAY_ABBR[low]

    # Dot separator: MM.DD
    dot_match = re.match(r"^(\d{1,2})\.(\d{1,2})$", low)
    if dot_match:
        month, day = int(dot_match.group(1)), int(dot_match.group(2))
        try:
            candidate = date(ref.year, month, day)
        except ValueError:
            raise ValueError(f"Invalid date: {value}")
        if candidate < ref:
            try:
                candidate = date(ref.year + 1, month, day)
            except ValueError:
                raise ValueError(f"Invalid date: {value}")
        return candidate

    if low == "today":
        return ref

    if low == "tomorrow":
        return ref + timedelta(days=1)

    # Day of week
    if low in DAY_NAMES:
        target = DAY_NAMES.index(low)
        current = ref.weekday()
        delta = (target - current) % 7
        if delta == 0:
            delta = 7  # next week's occurrence
        return ref + timedelta(days=delta)

    # Month+day: "mar29", "mar-29", "mar 29"
    month_match = MONTH_DAY_RE.match(low)
    if month_match:
        month = MONTH_ABBR[month_match.group(1).lower()]
        day = int(month_match.group(2))
        try:
            candidate = date(ref.year, month, day)
        except ValueError:
            raise ValueError(f"Invalid date: {value}")
        if candidate < ref:
            try:
                candidate = date(ref.year + 1, month, day)
            except ValueError:
                raise ValueError(f"Invalid date: {value}")
        return candidate

    # Legacy: 4-digit MMDD
    if re.match(r"^\d{4}$", low):
        month, day = int(low[:2]), int(low[2:])
        try:
            candidate = date(ref.year, month, day)
        except ValueError:
            raise ValueError(f"Invalid date: {value}")
        if candidate < ref:
            try:
                candidate = date(ref.year + 1, month, day)
            except ValueError:
                raise ValueError(f"Invalid date: {value}")
        return candidate

    # Legacy: slash format "3/29"
    slash_match = SLASH_DATE_RE.match(low)
    if slash_match:
        month = int(slash_match.group(1))
        day = int(slash_match.group(2))
        try:
            candidate = date(ref.year, month, day)
        except ValueError:
            raise ValueError(f"Invalid date: {value}")
        if candidate < ref:
            try:
                candidate = date(ref.year + 1, month, day)
            except ValueError:
                raise ValueError(f"Invalid date: {value}")
        return candidate

    # ISO format fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Invalid date: {value}")
