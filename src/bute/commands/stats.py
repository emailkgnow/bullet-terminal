"""Stats command — bt stats momentum dashboard."""

from datetime import date, timedelta
from pathlib import Path

from bute.storage import entry_path, query_and_load


def get_done_per_day(
    config, start: date, end: date
) -> dict[date, int]:
    """Count tasks marked done per day (by file mtime) in [start, end]."""
    entries = query_and_load(config, type="task", status="done")
    counts: dict[date, int] = {}
    for entry in entries:
        path = entry_path(entry, config)
        if not path.exists():
            continue
        mtime_date = date.fromtimestamp(path.stat().st_mtime)
        if start <= mtime_date <= end:
            counts[mtime_date] = counts.get(mtime_date, 0) + 1
    return counts


def get_dropped_per_day(
    config, start: date, end: date
) -> dict[date, int]:
    """Count tasks marked dropped per day (by file mtime) in [start, end]."""
    entries = query_and_load(config, type="task", status="dropped")
    counts: dict[date, int] = {}
    for entry in entries:
        path = entry_path(entry, config)
        if not path.exists():
            continue
        mtime_date = date.fromtimestamp(path.stat().st_mtime)
        if start <= mtime_date <= end:
            counts[mtime_date] = counts.get(mtime_date, 0) + 1
    return counts


def calc_task_streak(done_per_day: dict[date, int], today: date) -> int:
    """Consecutive days with at least 1 task done, backward from today."""
    if done_per_day.get(today, 0) == 0:
        return 0
    streak = 1
    d = today - timedelta(days=1)
    while done_per_day.get(d, 0) > 0:
        streak += 1
        d -= timedelta(days=1)
    return streak


def calc_dp_streak(config, today: date) -> int:
    """Consecutive days with daily plan completed, backward from today."""
    from bute.state import get_dp_history

    history = get_dp_history(config)
    if today not in history:
        return 0
    streak = 1
    d = today - timedelta(days=1)
    while d in history:
        streak += 1
        d -= timedelta(days=1)
    return streak
