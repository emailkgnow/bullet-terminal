"""One-time migration: convert @today/@thisweek tags into focus_date/week_date fields.

Preserves file mtime so get_tasks_done_today (which uses mtime) isn't corrupted.
Safe to run multiple times — idempotent.
"""

import os
from datetime import date, timedelta

from bute.config import load_config
from bute.storage import entry_path, query_and_load, update_entry


def main() -> None:
    config = load_config()
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())

    # Migrate @today → focus_date=today
    tagged_today = query_and_load(config, tag="today")
    for e in tagged_today:
        if "today" in e.tags:
            e.tags.remove("today")
        if e.focus_date is None:
            e.focus_date = today
        p = entry_path(e, config)
        mtime = p.stat().st_mtime
        update_entry(e, config)
        os.utime(p, (mtime, mtime))
    print(f"Migrated {len(tagged_today)} @today → focus_date")

    # Migrate @thisweek → week_date=this_monday
    tagged_week = query_and_load(config, tag="thisweek")
    for e in tagged_week:
        if "thisweek" in e.tags:
            e.tags.remove("thisweek")
        if e.week_date is None:
            e.week_date = this_monday
        p = entry_path(e, config)
        mtime = p.stat().st_mtime
        update_entry(e, config)
        os.utime(p, (mtime, mtime))
    print(f"Migrated {len(tagged_week)} @thisweek → week_date")


if __name__ == "__main__":
    main()
