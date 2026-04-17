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
