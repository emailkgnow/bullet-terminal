"""State management — bridges views (numbered lists) and actions (by number)."""

import json
from datetime import date, datetime
from pathlib import Path

from bute.config import get_data_dir
from bute.errors import InvalidEntryNumberError, StateNotFoundError


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
    path.write_text(json.dumps(data))
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
    path.write_text(date.today().isoformat())
    # Append to history for streak tracking
    history_path = get_data_dir(config) / ".dp_history"
    today_iso = date.today().isoformat()
    existing = set()
    if history_path.exists():
        existing = set(history_path.read_text().strip().splitlines())
    if today_iso not in existing:
        with open(history_path, "a") as f:
            f.write(today_iso + "\n")


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


def mark_wp_done(config=None) -> None:
    """Record that weekly plan was completed this week."""
    path = get_data_dir(config) / ".wp_date"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(date.today().strftime("%G-W%V"))


def is_wp_done_this_week(config=None) -> bool:
    """Check if weekly plan was already completed this week."""
    path = get_data_dir(config) / ".wp_date"
    if not path.exists():
        return False
    return path.read_text().strip() == date.today().strftime("%G-W%V")



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
    path.write_text(json.dumps(log[-50:]))


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

    path.write_text(json.dumps(log))
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
