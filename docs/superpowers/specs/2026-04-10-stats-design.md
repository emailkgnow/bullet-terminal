# bt stats — Momentum Dashboard

## Overview

A `bt stats` command that surfaces motivating momentum metrics: streaks, daily closure trends, and period comparisons. Pure motivation — no goal tracking, no tag breakdowns. Three views with different time windows.

## Command Grammar

```
bt stats          # default: this week/month vs last week/month, 14-day chart
bt stats week     # deeper weekly view, 7-day chart (current week)
bt stats month    # rolling 30-day view, 30-day chart
```

## Display Layout

All three views share the same structure — streaks at top, closure chart in the middle, period comparisons at bottom. Only the time windows change.

### Default View (`bt stats`)

```
                     ── Momentum ──

  🔥 Task Streak: 5 days
  📋 Daily Plan Streak: 3 days

  Daily closures (last 14 days):
  M  T  W  T  F  S  S  M  T  W  T  F  S  S
  2  ·  3  1  4  ·  ·  3  2  1  3  2  ·  ·
  ▂  ▁  ▄  ▂  █  ▁  ▁  ▄  ▃  ▂  ▄  ▃  ▁  ▁

  This week: 8 done · 1 dropped
  Last week: 6 done · 2 dropped
  This month: 22 done · 5 dropped
  Last month: 31 done · 3 dropped
```

### Week View (`bt stats week`)

Same streaks at top. Chart shows 7 days (Mon–Sun of current week). Comparisons show this week vs last week only.

### Month View (`bt stats month`)

Same streaks at top. Chart stretches to 30 days. Comparisons show rolling 30-day vs previous 30-day window.

## Metrics

### Task Streak

Consecutive days (backward from today) where at least 1 task was marked done. A day counts if any task's file was modified on that date and has `status: done`.

Calculation approach:
- Query all done tasks
- Group by file mtime date (the date the task was marked done)
- Walk backward from today counting consecutive days with at least 1 done task

### Daily Plan Streak

Consecutive days where `bt dp` was completed. Uses the existing `.dp_date` mechanism in state.py.

Problem: `.dp_date` only stores the most recent date, not a history. To support streaks, we need to track dp completion history.

**Solution:** Add a `.dp_history` file (one ISO date per line, appended by `mark_dp_done()`). On first run, seed it with today's date if `.dp_date` matches today. The streak walks backward through this file.

### Daily Closure Chart

A 2-row visual per day:
- **Row 1:** Number of tasks done that day (`·` if zero)
- **Row 2:** Block character proportional to the count (▁▂▃▄▅▆▇█), scaled relative to the max in the window

Day labels use single-letter weekday abbreviations (M T W T F S S).

### Period Comparisons

Done and dropped counts for each period pair:
- Default: this week vs last week, this month vs last month
- Week: this week vs last week
- Month: rolling 30 days vs previous 30 days

"This week" = Monday through today. "Last week" = previous Mon–Sun. "This month" = 1st of current month through today. "Last month" = full previous calendar month.

## Data Sources

| Metric | Source | Query |
|--------|--------|-------|
| Tasks done per day | SQLite index | `status=done`, group by mtime date |
| Tasks dropped per day | SQLite index | `status=dropped`, group by mtime date |
| Task streak | Derived from done-per-day | Walk backward from today |
| DP streak | `.dp_history` file | Walk backward from today |

### Missing: Status Change Timestamp

The current data model has no field for when a task was marked done/dropped. The `created` field is the capture date. File mtime is the best proxy — it's updated when `update_entry()` writes the file.

**Approach:** Use file mtime from the filesystem. When querying via SQLite, we'll need to join against file paths or add an `updated` column. For the initial implementation, load entries via `query_and_load()` and check `Path.stat().st_mtime` on each file.

Future improvement: add an `updated` timestamp to the Entry model and SQLite schema, set on every `update_entry()` call. This would make stats queries faster and more reliable.

## Implementation

### New Module: `commands/stats.py`

Pure functions for data aggregation + a Click command group.

**Functions:**
- `get_done_per_day(config, start: date, end: date) -> dict[date, int]` — count of tasks done (by mtime) per day
- `get_dropped_per_day(config, start: date, end: date) -> dict[date, int]` — same for dropped
- `calc_task_streak(done_per_day: dict, today: date) -> int` — consecutive days with done > 0
- `calc_dp_streak(config, today: date) -> int` — consecutive days in dp history
- `build_closure_chart(done_per_day: dict, days: list[date]) -> tuple[list[str], list[str]]` — day labels + bar characters

**Click Commands:**
- `@main.command("stats")` with optional `period` argument (`week` or `month`)

### Display

Use Rich `Text` objects with manual styling — no Panel borders, no Table. Section headers centered with `── Title ──` pattern. Content left-aligned with consistent indentation.

### State Changes

- `mark_dp_done()` in state.py: also append today's date to `.dp_history`
- New `get_dp_history(config) -> set[date]`: read `.dp_history` into a set of dates

### CLI Registration

Add `stats` to `cli.py` command group. No letter shortcut needed — `bt stats` is clear enough.

## Edge Cases

- **No tasks done yet:** Show "Task Streak: 0 days" and empty chart (all `·`)
- **First day using bt:** All comparisons show 0 for prior periods
- **DP history doesn't exist yet:** DP streak shows 0, file created on next `bt dp`
- **Weekend gaps:** Streak breaks on weekends if no tasks done — this is intentional (motivation to stay consistent)

## What This Is NOT

- Not a goals tracker — `bt goals` already does that
- Not a tag breakdown — tags are visible in other views
- Not a productivity report — no averages, no projections, no scores
- Just momentum: am I showing up, and is the number going up
