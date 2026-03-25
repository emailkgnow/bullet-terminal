"""YAML-based habit tracking storage for bute."""

from datetime import date
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
    data[date_key][name] = done

    _save_month(target, data, config)


def get_habit_summary(
    target_date: date, configured_habits: list[str], config=None
) -> dict[str, bool | None]:
    """Get today's status for all configured habits.

    Returns {name: True/False/None} where None = not tracked yet.
    """
    logged = load_habits_for_date(target_date, config)
    return {name: logged.get(name) for name in configured_habits}
