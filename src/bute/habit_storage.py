"""YAML-based habit tracking storage for bute."""

from datetime import date, timedelta
from pathlib import Path

import yaml

from bute.config import get_data_dir


def _habit_file_path(target_date: date, config=None) -> Path:
    """Return path to ~/bute/habits/YYYY-MM.yml"""
    data_dir = get_data_dir(config)
    return data_dir / "habits" / f"{target_date.strftime('%Y-%m')}.yml"


def _load_month(target_date: date, config=None) -> dict:
    """Load the entire month's habit data."""
    path = _habit_file_path(target_date, config)
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data or {}


def _save_month(target_date: date, data: dict, config=None) -> None:
    """Write the month's habit data."""
    path = _habit_file_path(target_date, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=True)


def load_habits_for_date(target_date: date, config=None) -> dict[str, bool]:
    """Get one day's habits. Returns {name: done}."""
    data = _load_month(target_date, config)
    date_key = target_date.isoformat()
    return data.get(date_key, {})


def save_habit(
    name: str, done: bool, target_date: date | None = None, config=None
) -> None:
    """Write one habit check-in. Creates file/date entry if needed."""
    target = target_date or date.today()
    data = _load_month(target, config)
    date_key = target.isoformat()

    if date_key not in data:
        data[date_key] = {}
    data[date_key][str(name)] = done

    _save_month(target, data, config)


def remove_habit_entry(
    name: str, target_date: date | None = None, config=None
) -> None:
    """Remove a habit's entry for a specific day (undo)."""
    target = target_date or date.today()
    data = _load_month(target, config)
    date_key = target.isoformat()

    if date_key in data and name in data[date_key]:
        del data[date_key][name]
        if not data[date_key]:
            del data[date_key]
        _save_month(target, data, config)


def get_habit_summary(
    target_date: date, configured_habits: list[str], config=None
) -> dict[str, bool | None]:
    """Get today's status for all configured habits.

    Returns {name: True/False/None} where None = not tracked yet.
    """
    logged = load_habits_for_date(target_date, config)
    return {name: logged.get(name) for name in configured_habits}


def get_habit_history(
    days: int, configured_habits: list[str], target_date: date | None = None, config=None
) -> dict[str, dict[date, bool | None]]:
    """Get habit data for the last N days ending on target_date.

    Returns {habit_name: {date: True/False/None}} for each configured habit.
    None means no data recorded for that day.
    """
    end = target_date or date.today()
    start = end - timedelta(days=days - 1)

    # Collect all months we need to load
    months_needed: set[tuple[int, int]] = set()
    d = start
    while d <= end:
        months_needed.add((d.year, d.month))
        if d.month == 12:
            d = d.replace(year=d.year + 1, month=1, day=1)
        else:
            d = d.replace(month=d.month + 1, day=1)

    # Load all needed months
    month_data: dict[str, dict] = {}
    for year, month in months_needed:
        target = date(year, month, 1)
        month_data[target.strftime("%Y-%m")] = _load_month(target, config)

    # Build history per habit
    history: dict[str, dict[date, bool | None]] = {}
    for name in configured_habits:
        history[name] = {}
        d = start
        while d <= end:
            date_key = d.isoformat()
            month_key = d.strftime("%Y-%m")
            day_data = month_data.get(month_key, {}).get(date_key, {})
            history[name][d] = day_data.get(name)
            d += timedelta(days=1)

    return history


def compute_streak(
    history: dict[str, dict[date, bool | None]], name: str, target_date: date | None = None
) -> int:
    """Count consecutive true days backwards from yesterday.

    Today is excluded (day isn't over). Streak = 0 if yesterday was not true.
    """
    end = target_date or date.today()
    yesterday = end - timedelta(days=1)
    habit_data = history.get(name, {})

    streak = 0
    d = yesterday
    while True:
        if habit_data.get(d) is not True:
            break
        streak += 1
        d -= timedelta(days=1)

    return streak
