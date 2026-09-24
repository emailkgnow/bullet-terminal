"""State management — bridges views (numbered lists) and actions (by number)."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from bute.config import get_data_dir
from bute.errors import InvalidEntryNumberError, StateNotFoundError
from bute.fsutil import atomic_write_text


def state_path(config=None) -> Path:
    """Return the path to the state file."""
    return get_data_dir(config) / ".state.json"


def save_state(view_name: str, entry_ids: list[str], config=None, extra_entries: list[str] | None = None) -> Path:
    """Write the current view state (number-to-ULID mapping).

    extra_entries: entry IDs numbered after the main list (e.g. random journal whisper).
    """
    path = state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"view": view_name, "entries": entry_ids}
    if extra_entries:
        data["extra_entries"] = extra_entries
    atomic_write_text(path, json.dumps(data))
    return path


def load_state(config=None) -> dict:
    """Read the state file. Raises StateNotFoundError if missing."""
    path = state_path(config)
    if not path.exists():
        raise StateNotFoundError()
    return json.loads(path.read_text())


def mark_dp_done(config=None) -> None:
    """Record that daily plan was completed today."""
    path = get_data_dir(config) / ".dp_date"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, date.today().isoformat())
    # Append to history for streak tracking
    history_path = get_data_dir(config) / ".dp_history"
    today_iso = date.today().isoformat()
    existing = set()
    if history_path.exists():
        existing = set(history_path.read_text().strip().splitlines())
    if today_iso not in existing:
        lines = sorted(existing | {today_iso})
        atomic_write_text(history_path, "\n".join(lines) + "\n")


def get_dp_history(config=None) -> set[date]:
    """Read dp completion history as a set of dates."""
    path = get_data_dir(config) / ".dp_history"
    if not path.exists():
        return set()
    dates = set()
    for line in path.read_text().strip().splitlines():
        line = line.strip()
        if line:
            dates.add(date.fromisoformat(line))
    return dates


def is_dp_done_today(config=None) -> bool:
    """Check if daily plan was already completed today."""
    path = get_data_dir(config) / ".dp_date"
    if not path.exists():
        return False
    return path.read_text().strip() == date.today().isoformat()


def _wp_trigger_date(today: date, config=None) -> date:
    """The core.wp_day inside the bt week (core.week_start) containing today."""
    from bute.config import get_wp_day, week_bounds

    start = week_bounds(today, config)[0]
    return start + timedelta(days=(get_wp_day(config) - start.weekday()) % 7)


def mark_wp_done(config=None, today: date | None = None) -> None:
    """Record that weekly plan was completed this week (keyed by the bt week's first day)."""
    from bute.config import week_bounds

    path = get_data_dir(config) / ".wp_date"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, week_bounds(today or date.today(), config)[0].isoformat())


def is_wp_done_this_week(config=None, today: date | None = None) -> bool:
    """Check if weekly plan was already completed this bt week."""
    from bute.config import week_bounds

    today = today or date.today()
    path = get_data_dir(config) / ".wp_date"
    if not path.exists():
        return False
    marker = path.read_text().strip()
    if "-W" in marker:
        # Pre-fix marker, an ISO week: it covers the bt week whose trigger day it contains.
        return marker == _wp_trigger_date(today, config).strftime("%G-W%V")
    return marker == week_bounds(today, config)[0].isoformat()


def is_wp_due(config=None, today: date | None = None) -> bool:
    """True from this bt week's wp_day onward until the weekly plan is done.

    Keyed on the bt week, not the ISO week, so a missed trigger day is caught
    up the next time bt runs, and a mid-week manual `bt wp` can't count
    toward a week that starts later.
    """
    today = today or date.today()
    return today >= _wp_trigger_date(today, config) and not is_wp_done_this_week(config, today)



# Number of recently-shown journals kept out of the whisper rotation.
JOURNAL_HISTORY_LIMIT = 30


def _journal_history_path(config=None) -> Path:
    """Return the path to the recently-shown journal log."""
    return get_data_dir(config) / ".journal_history"


def get_journal_history(config=None) -> list[str]:
    """Read recently-shown journal IDs, oldest first."""
    path = _journal_history_path(config)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def record_journal_shown(entry_id: str, config=None) -> None:
    """Log a journal as shown, keeping the last JOURNAL_HISTORY_LIMIT."""
    history = [i for i in get_journal_history(config) if i != entry_id]
    history.append(entry_id)
    history = history[-JOURNAL_HISTORY_LIMIT:]
    path = _journal_history_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, "\n".join(history) + "\n")


def _undo_path(config=None) -> Path:
    """Return the path to the undo log."""
    return get_data_dir(config) / ".undo.json"


def record_undo(entry_id: str, action: str, prev: dict, config=None) -> None:
    """Append an undoable action to the log.

    prev: dict of previous values, e.g. {"status": "active"} or {"tag": "work"}.
    """
    path = _undo_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    log = json.loads(path.read_text()) if path.exists() else []
    log.append({
        "entry_id": entry_id,
        "action": action,
        "prev": prev,
        "ts": datetime.now().isoformat(),
    })
    # Keep last 50 actions
    atomic_write_text(path, json.dumps(log[-50:]))


def pop_undo(entry_id: str | None = None, config=None) -> dict | None:
    """Pop the last undoable action (optionally for a specific entry).

    Returns the action record or None if nothing to undo.
    """
    path = _undo_path(config)
    if not path.exists():
        return None
    log = json.loads(path.read_text())
    if not log:
        return None

    if entry_id is None:
        record = log.pop()
    else:
        # Find last action for this entry
        for i in range(len(log) - 1, -1, -1):
            if log[i]["entry_id"] == entry_id:
                record = log.pop(i)
                break
        else:
            return None

    atomic_write_text(path, json.dumps(log))
    return record


def resolve_numbers(numbers: list[int], config=None) -> list[str]:
    """Map 1-indexed display numbers to ULIDs from the last view state.

    Number mapping: entries (1..N), extra_entries (N+1..).

    Raises:
        StateNotFoundError: If no state file exists.
        InvalidEntryNumberError: If any number is out of range.
    """
    state = load_state(config)
    entries = state.get("entries", [])
    extra = state.get("extra_entries", [])
    total = len(entries) + len(extra)

    result = []
    for n in numbers:
        if n < 1 or n > total:
            raise InvalidEntryNumberError(
                f"Entry #{n} is out of range. Last view had {total} entries."
            )
        if n <= len(entries):
            result.append(entries[n - 1])
        else:
            result.append(extra[n - len(entries) - 1])
    return result
