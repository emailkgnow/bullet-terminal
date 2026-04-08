"""Storage migration — moves entries from month-first to type-first layout."""

import re
import zipfile
from datetime import date
from pathlib import Path

import frontmatter as fm

from bute.config import get_data_dir

MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def needs_migration(config=None) -> bool:
    """Check if entries/ contains old-style YYYY-MM dirs at the top level."""
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return False
    for child in entries_dir.iterdir():
        if child.is_dir() and MONTH_PATTERN.match(child.name):
            if any(child.glob("*.md")):
                return True
    return False


def migrate_entries(config=None) -> dict:
    """Move entries from entries/YYYY-MM/ to entries/{type}/YYYY-MM/.

    Returns a dict with counts: {"task": N, "note": N, ..., "total": N}
    """
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"

    # Backup first
    _backup_entries(data_dir, entries_dir)

    counts = {"task": 0, "note": 0, "journal": 0, "calendar": 0, "total": 0}

    # Find old-style month dirs
    old_month_dirs = [
        d for d in sorted(entries_dir.iterdir())
        if d.is_dir() and MONTH_PATTERN.match(d.name)
    ]

    for month_dir in old_month_dirs:
        for md_file in month_dir.glob("*.md"):
            try:
                post = fm.load(str(md_file))
                entry_type = post.metadata.get("type", "note")
                if entry_type not in counts:
                    entry_type = "note"
            except Exception:
                entry_type = "note"

            new_dir = entries_dir / entry_type / month_dir.name
            new_dir.mkdir(parents=True, exist_ok=True)
            new_path = new_dir / md_file.name
            md_file.rename(new_path)

            counts[entry_type] += 1
            counts["total"] += 1

        # Remove empty old month dir
        if not any(month_dir.iterdir()):
            month_dir.rmdir()

    return counts


def _backup_entries(data_dir: Path, entries_dir: Path) -> Path:
    """Zip the entries directory before migration."""
    today = date.today().isoformat()
    backup_path = data_dir / f"entries-backup-{today}.zip"
    counter = 1
    while backup_path.exists():
        counter += 1
        backup_path = data_dir / f"entries-backup-{today}-{counter}.zip"

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(entries_dir.rglob("*")):
            if file_path.is_file():
                arcname = str(file_path.relative_to(data_dir))
                zf.write(file_path, arcname)

    return backup_path
