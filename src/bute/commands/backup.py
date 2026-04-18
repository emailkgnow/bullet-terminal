"""Automatic daily backup of user data as a zip file."""

import zipfile
from datetime import date, timedelta
from pathlib import Path

from bute.config import DEMO_DATA_DIR, get_data_dir

BACKUP_DIR_NAME = "backups"
BACKUP_PREFIX = "bt-"
RETENTION_DAYS = 30


def _backup_dir(data_dir: Path) -> Path:
    return data_dir / BACKUP_DIR_NAME


def _collect_entry_files(data_dir: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return files
    for p in sorted(entries_dir.rglob("*")):
        if p.is_file():
            files.append((p, str(p.relative_to(data_dir))))
    return files


def _write_backup(data_dir: Path, iso_date: str) -> Path | None:
    files = _collect_entry_files(data_dir)
    if not files:
        return None
    backups = _backup_dir(data_dir)
    backups.mkdir(parents=True, exist_ok=True)
    zip_path = backups / f"{BACKUP_PREFIX}{iso_date}.zip"
    tmp_path = zip_path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path, arcname in files:
            zf.write(file_path, arcname)
    tmp_path.replace(zip_path)
    return zip_path


def _prune_old_backups(data_dir: Path, retention_days: int = RETENTION_DAYS) -> int:
    backups = _backup_dir(data_dir)
    if not backups.exists():
        return 0
    cutoff = date.today() - timedelta(days=retention_days)
    removed = 0
    for p in backups.glob(f"{BACKUP_PREFIX}*.zip"):
        stem = p.stem.removeprefix(BACKUP_PREFIX)
        try:
            backup_date = date.fromisoformat(stem)
        except ValueError:
            continue
        if backup_date < cutoff:
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def run_daily_backup_if_needed(config) -> None:
    """Create a dated zip backup of entries/ if one for today doesn't exist.

    Silent on success and failure — never blocks bt launch. Pruning keeps
    only the last RETENTION_DAYS of backups. Skipped in demo mode.
    """
    try:
        data_dir = get_data_dir(config)
        if data_dir.resolve() == DEMO_DATA_DIR.resolve():
            return
        if not data_dir.exists():
            return
        today = date.today().isoformat()
        zip_path = _backup_dir(data_dir) / f"{BACKUP_PREFIX}{today}.zip"
        if zip_path.exists():
            return
        if _write_backup(data_dir, today) is None:
            return
        _prune_old_backups(data_dir)
    except Exception:
        pass
