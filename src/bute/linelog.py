"""Line log storage — compressed daily journal summaries."""

from datetime import date
from pathlib import Path

from bute.config import get_data_dir


def _linelog_path(target_date: date, config=None) -> Path:
    """Return path to <data_dir>/linelog/YYYY-MM.md"""
    data_dir = get_data_dir(config)
    return data_dir / "linelog" / f"{target_date.strftime('%Y-%m')}.md"


def append_line(line: str, target_date: date, config=None) -> None:
    """Append a compressed journal line for a given date."""
    path = _linelog_path(target_date, config)
    path.parent.mkdir(parents=True, exist_ok=True)

    day_num = target_date.day
    entry = f"{day_num:2d}  ~ {line.strip()}\n"

    # Append to file
    with open(path, "a") as f:
        f.write(entry)


def has_entry_for_date(target_date: date, config=None) -> bool:
    """Check if a linelog entry already exists for a given date."""
    text = load_month(target_date, config)
    if not text:
        return False
    prefix = f"{target_date.day:2d}  "
    return any(line.startswith(prefix) for line in text.splitlines())


def load_month(target_date: date, config=None) -> str:
    """Load the entire month's line log as text."""
    path = _linelog_path(target_date, config)
    if not path.exists():
        return ""
    return path.read_text()
