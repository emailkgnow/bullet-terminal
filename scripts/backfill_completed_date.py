"""One-time migration: backfill `completed_date` on legacy done/dropped tasks.

Before commit 43914a6 (2026-04-17), bt didn't track `completed_date` — it
read the file's mtime to determine when a task was completed. The mtime
approach is now unreliable because yesterday's focus_date/week_date migration
rewrote every file, clobbering real mtimes.

Best-available proxy: use `focus_date` if set (≈ "last day this was on your
radar"), else fall back to `created.date()`. Imprecise but makes legacy
done/dropped tasks visible in `bt m`'s retrospective.

Dry-run by default; pass --apply to actually write.

Usage:
    uv run scripts/backfill_completed_date.py            # dry run
    uv run scripts/backfill_completed_date.py --apply    # write changes
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import frontmatter


def iter_task_files(entries_root: Path):
    task_root = entries_root / "task"
    if not task_root.exists():
        return
    yield from task_root.rglob("*.md")


def needs_backfill(post: frontmatter.Post) -> bool:
    status = post.metadata.get("status")
    if status not in ("done", "dropped"):
        return False
    return post.metadata.get("completed_date") is None


def best_completion_date(post: frontmatter.Post) -> date:
    """Pick the best-available proxy for completion date.

    focus_date is the "last day this was on your radar" signal. If missing,
    fall back to created date (wrong, but visible is better than invisible).
    """
    focus = post.metadata.get("focus_date")
    if focus:
        return _coerce_date(focus)
    created = post.metadata.get("created")
    return _coerce_date(created).date() if isinstance(_coerce_date(created), datetime) else _coerce_date(created)


def _coerce_date(value):
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return date.fromisoformat(value[:10])
    raise TypeError(f"can't coerce {value!r} to date")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Actually write changes (default: dry run)")
    ap.add_argument(
        "--entries-root",
        type=Path,
        default=Path.home() / "bullet-terminal" / "entries",
        help="Path to the entries directory",
    )
    args = ap.parse_args()

    entries_root: Path = args.entries_root
    if not entries_root.exists():
        print(f"error: entries root not found: {entries_root}", file=sys.stderr)
        return 1

    to_update: list[tuple[Path, date]] = []
    for path in iter_task_files(entries_root):
        try:
            post = frontmatter.load(str(path))
        except Exception as exc:
            print(f"warn: could not parse {path}: {exc}", file=sys.stderr)
            continue
        if needs_backfill(post):
            to_update.append((path, best_completion_date(post)))

    if not to_update:
        print("Nothing to backfill — every done/dropped task already has completed_date.")
        return 0

    print(f"Found {len(to_update)} done/dropped tasks without completed_date.")
    print()
    print("Sample (first 10):")
    for path, d in to_update[:10]:
        print(f"  {path.name}  ->  completed_date: {d.isoformat()}")
    print()

    if not args.apply:
        print("DRY RUN — no files written. Re-run with --apply to commit changes.")
        return 0

    updated = 0
    for path, d in to_update:
        post = frontmatter.load(str(path))
        post.metadata["completed_date"] = d.isoformat()
        path.write_text(frontmatter.dumps(post))
        updated += 1

    print(f"Wrote completed_date on {updated} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
