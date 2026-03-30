# bt streak — Habit Streaks & Trends

## Overview

Read-only view showing all configured habits with a 7-day grid, current streak, and 30-day completion rate.

## CLI Interface

```
bt streak
```

## Output Format

```
Habits — Last 7 Days

              Mon Tue Wed Thu Fri Sat Sun
  quran        ●   ●   ●   ●   ●   ○   ○    streak: 5   22/30 (73%)
  walking      ●   ○   ●   ●   ○   ○   ○    streak: 0   14/30 (47%)
```

Rendered as a Rich Table.

## Data Logic

- **7-day grid:** Last 7 days ending today. `●` = done (true), `○` = not done (false/missing/null).
- **Streak:** Count consecutive `true` days backwards from yesterday (today excluded since the day isn't over). Streak = 0 if yesterday was missed.
- **30-day rate:** Count of `true` days out of last 30. Displayed as `N/30 (X%)`.

## Data Queries

### get_habit_history(days, configured_habits, config)

New function in `habit_storage.py`. Scans YYYY-MM.yml files for the date range (handles month boundaries by loading both months when needed). Returns `dict[str, dict[date, bool | None]]` — keyed by habit name, inner dict keyed by date.

### compute_streak(history, name)

New function in `habit_storage.py`. Takes the history dict and a habit name. Counts consecutive `true` values backwards from yesterday. Returns int. Today is excluded (day isn't over). If yesterday is not `true`, returns 0.

## Edge Cases

- **No habits configured** → print "No habits configured. Add with bt habit <name>"
- **No history at all** → grid shows all `○`, streak 0, 0/30 (0%)
- **Month boundary** → `get_habit_history` scans across multiple YYYY-MM.yml files as needed (e.g., if today is March 2, the 30-day lookback reaches into February)
- **Habit added recently** → days before the habit existed show as `○` (same as not done)

## Files to Modify

| File | Change |
|------|--------|
| `habit_storage.py` | Add `get_habit_history()` and `compute_streak()` |
| `commands/rituals.py` | Add `streak_cmd` |
| `cli.py` | Import, register `streak_cmd`, add to Habits section of help text |

## Design Decisions

- **Read-only**: no interactive prompts, just display.
- **Today excluded from streak**: the day isn't over, so not counting it avoids penalizing you mid-day.
- **30-day window is fixed**: not configurable. Keeps it simple.
- **No per-habit detail view**: all habits shown in one table. YAGNI.
