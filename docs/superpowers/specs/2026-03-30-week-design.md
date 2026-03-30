# bt week — Weekly Spread

## Overview

Full weekly spread across all dimensions (tasks, journals, notes, events) for Mon-Sun of the current week. Like linelog but with all entry types and full detail.

## CLI Interface

```
bt week           # this week (Mon-Sun)
bt week last      # last week
```

## Output Format

Grouped by date using existing `display_entry_list_grouped`. Includes all entry types, all statuses (done/dropped shown with styling). Numbered for actions.

## Data Query

For each day Mon-Sun of the target week:
- `load_entries_by_date(day, config)` for entries created that day
- Also include tasks tagged @today for that day (created on other days) — actually, skip this. Keep it simple: entries created that day, period.
- Include ALL statuses (done, dropped, active) — override `load_entries_by_date`'s default dropped-exclusion by using `load_entries_by_filter` with date check instead.

## Edge Cases

- **Mid-week**: days after today show nothing (no future entries)
- **Empty day**: skip it (no "No entries" row)
- **No entries all week**: "No entries this week."

## Files to Modify

| File | Change |
|------|--------|
| `ritual_ops.py` | Add `get_week_entries(target_date, config)` |
| `commands/views.py` | Add `week_cmd` |
| `cli.py` | Register, add to Views help section |
