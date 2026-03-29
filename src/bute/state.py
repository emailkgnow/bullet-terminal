"""State management — bridges views (numbered lists) and actions (by number)."""

import json
from datetime import date, datetime
from pathlib import Path

from bute.config import get_data_dir
from bute.errors import InvalidEntryNumberError, StateNotFoundError


def state_path(config=None) -> Path:
    """Return the path to the state file."""
    return get_data_dir(config) / ".state.json"


def save_state(view_name: str, entry_ids: list[str], config=None, habits: list[str] | None = None) -> Path:
    """Write the current view state (number-to-ULID mapping, optional habits)."""
    path = state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"view": view_name, "entries": entry_ids}
    if habits:
        data["habits"] = habits
    path.write_text(json.dumps(data))
    return path


def load_state(config=None) -> dict:
    """Read the state file. Raises StateNotFoundError if missing."""
    path = state_path(config)
    if not path.exists():
        raise StateNotFoundError()
    return json.loads(path.read_text())


def mark_dyts_done(config=None) -> None:
    """Record that DYTS was completed today."""
    path = get_data_dir(config) / ".dyts_date"
    path.write_text(date.today().isoformat())


def is_dyts_done_today(config=None) -> bool:
    """Check if DYTS was already completed today."""
    path = get_data_dir(config) / ".dyts_date"
    if not path.exists():
        return False
    return path.read_text().strip() == date.today().isoformat()


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

    Raises:
        StateNotFoundError: If no state file exists.
        InvalidEntryNumberError: If any number is out of range.
    """
    state = load_state(config)
    entries = state.get("entries", [])

    result = []
    for n in numbers:
        if n < 1 or n > len(entries):
            raise InvalidEntryNumberError(
                f"Entry #{n} is out of range. Last view had {len(entries)} entries."
            )
        result.append(entries[n - 1])  # 1-indexed to 0-indexed
    return result
