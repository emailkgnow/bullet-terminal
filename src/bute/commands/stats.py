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


_WEEKDAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"]
_BAR_CHARS = " ▁▂▃▄▅▆▇█"


def build_closure_chart(
    done_per_day: dict[date, int], days: list[date]
) -> tuple[list[str], list[str], list[str]]:
    """Build closure chart data for a list of days.

    Returns (day_labels, count_strings, bar_characters).
    """
    labels = [_WEEKDAY_LABELS[d.weekday()] for d in days]
    raw_counts = [done_per_day.get(d, 0) for d in days]
    max_count = max(raw_counts) if raw_counts else 0

    counts_row = [str(c) if c > 0 else "·" for c in raw_counts]

    bars = []
    for c in raw_counts:
        if max_count == 0 or c == 0:
            bars.append(" ")
        else:
            idx = max(1, round(c / max_count * 8))
            bars.append(_BAR_CHARS[idx])

    return labels, counts_row, bars


def get_period_ranges(
    view: str, today: date
) -> dict[str, tuple[date, date]]:
    """Compute date ranges for period comparisons.

    view: "default", "week", or "month".
    """
    # This week = Monday..today, last week = prev Mon..Sun
    monday = today - timedelta(days=today.weekday())
    last_monday = monday - timedelta(days=7)
    last_sunday = monday - timedelta(days=1)

    # This month = 1st..today, last month = full prev month
    first_of_month = today.replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    if view == "week":
        return {
            "this_week": (monday, today),
            "last_week": (last_monday, last_sunday),
        }
    elif view == "month":
        # Rolling 30-day windows
        period_start = today - timedelta(days=29)
        prev_end = period_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=29)
        return {
            "this_period": (period_start, today),
            "last_period": (prev_start, prev_end),
        }
    else:
        return {
            "this_week": (monday, today),
            "last_week": (last_monday, last_sunday),
            "this_month": (first_of_month, today),
            "last_month": (last_month_start, last_month_end),
        }
