"""Event log for entry lifecycle (capture, focus, schedule, complete, etc.).

Events are stored as a list of dicts on each Entry; this module defines
the action constants and pure helpers for synthesis (legacy entries)
and replay (state-at-a-given-day).
"""

from datetime import date
from typing import Iterable

from bute.models import Entry, EntryType, TaskStatus


# --- Action constants ---
CAPTURED = "captured"
FOCUSED = "focused"
UNFOCUSED = "unfocused"
SCHEDULED = "scheduled"
UNSCHEDULED = "unscheduled"
DONE = "done"
DROPPED = "dropped"
UNDROPPED = "undropped"
WEEK_PLANNED = "week_planned"
MODIFIED = "modified"
DUE_SET = "due_set"
DUE_CLEARED = "due_cleared"


ALL_ACTIONS = {
    CAPTURED, FOCUSED, UNFOCUSED, SCHEDULED, UNSCHEDULED,
    DONE, DROPPED, UNDROPPED, WEEK_PLANNED, MODIFIED,
    DUE_SET, DUE_CLEARED,
}


def synthesize_events(entry: Entry) -> list[dict]:
    """Return an event list for an entry.

    If the entry has stored events, return them unchanged. Otherwise,
    synthesize events from existing date fields (created, scheduled_date,
    focus_date, completed_date + status) — used for legacy entries from
    before the event-log feature shipped.

    Returned list is sorted by date (ascending).
    """
    if entry.events:
        return entry.events

    created_date = entry.created.date()
    synth: list[dict] = [
        {"date": created_date.isoformat(), "action": CAPTURED}
    ]

    if entry.scheduled_date is not None and entry.scheduled_date != created_date:
        synth.append({
            "date": entry.scheduled_date.isoformat(),
            "action": SCHEDULED,
            "scheduled_date": entry.scheduled_date.isoformat(),
        })

    if entry.focus_date is not None and entry.focus_date != created_date:
        synth.append({
            "date": entry.focus_date.isoformat(),
            "action": FOCUSED,
            "focus_date": entry.focus_date.isoformat(),
        })

    if entry.completed_date is not None:
        if entry.status == TaskStatus.DONE:
            synth.append({"date": entry.completed_date.isoformat(), "action": DONE})
        elif entry.status == TaskStatus.DROPPED:
            synth.append({"date": entry.completed_date.isoformat(), "action": DROPPED})

    synth.sort(key=lambda x: x["date"])
    return synth
