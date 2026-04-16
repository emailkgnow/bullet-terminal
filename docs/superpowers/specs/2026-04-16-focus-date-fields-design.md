# Replace @today/@thisweek Tags with Date Fields

**Date:** 2026-04-16
**Status:** Approved

## Problem

`@today` and `@thisweek` are system tags that encode temporal state as dumb text. They have no timestamp, no expiry, and no memory of when they were set. The system relies on rituals (`bt dp`, `bt wp`) to manage their lifecycle, but:

- If a ritual is skipped, the tags rot — `@today` from last Tuesday still reads as "today"
- Capture auto-tags every new task with both, so they accumulate on every task ever created
- The daily log (`bt d`) cannot show a retrospective for past days because there's no record of which day a task was focused on
- `clear_daily_focus()` exists in `ritual_ops.py` but is never called — the cleanup was never wired up
- Both tags are hidden from the user (`SYSTEM_TAGS`, `hide_tags`) — they're purely internal state masquerading as user-facing tags

## Solution

Replace both tags with proper `Optional[date]` fields on `Entry`:

- **`focus_date`** — the date this task was selected for daily focus. Replaces `@today`.
- **`week_date`** — the Monday of the week this task was selected for. Replaces `@thisweek`.

Old dates expire naturally. `focus_date: 2026-04-15` won't match tomorrow's Focus Log. No clearing step needed. No rot possible.

## Field Semantics

| Field | Set by | Cleared by | Filtered by |
|-------|--------|------------|-------------|
| `focus_date` | `bt dp` (daily plan picker), `bt focus`, capture (auto, today) | `bt later`, `bt backlog`, `bt clear d` (if we want) | Focus Log (`bt`): `focus_date == today`. Daily Log (`bt d <date>`): `focus_date == target` |
| `week_date` | `bt wp` (weekly plan picker), `bt focus`, capture (auto, this Monday) | `bt backlog` | Task Log (`bt t`): `week_date == this Monday` |

### Date values

- `focus_date` stores a plain `date` (e.g., `2026-04-16`)
- `week_date` stores the Monday of the ISO week (e.g., `2026-04-14` for week 16)
- Both are `None` when unset (task is in backlog — no focus scope)

### Auto-tagging on capture

Current: capture adds `@today` + `@thisweek` to every new task (unless `--later` or `--backlog` flags, or future date).

New: capture sets `focus_date = today` and `week_date = this_monday` under the same conditions. Same behavior, different storage.

## Changes by File

### models.py
- Add `focus_date: Optional[date] = None` and `week_date: Optional[date] = None` to `Entry`
- Add both to `Entry.create()` parameters and factory
- Add both to `to_dict()` serialization
- Remove `"today"` and `"thisweek"` from `SYSTEM_TAGS`

### storage.py
- Read `focus_date` and `week_date` from YAML frontmatter in `load_entry()`
- Write them in `save_entry()` / `update_entry()` (omit from YAML when None)

### capture.py
- Replace `entry.tags.append("today")` with `entry.focus_date = date.today()`
- Replace `entry.tags.append("thisweek")` with `entry.week_date = _this_monday()`
- Same conditions (not --later, not --backlog, not future-dated)

### ritual_ops.py
- `get_daily_log()`: filter tasks on `focus_date == today` instead of `"today" in tags`
- `get_weekly_active_tasks()`: filter on `week_date == this_monday` instead of `"thisweek" in tags`
- Remove `clear_daily_focus()` and `clear_weekly_selection()` — no longer needed
- `set_weekly_selection()`: set `week_date` instead of appending tag

### rituals.py (dp_cmd)
- Picker pre-checks: `checked=(e.focus_date == today)` instead of `"today" in e.tags`
- On selection: set `entry.focus_date = today` instead of `entry.tags.append("today")`
- On deselection: set `entry.focus_date = None` instead of `entry.tags.remove("today")`

### rituals.py (wp_cmd)
- Carryover detection: `"thisweek" in e.tags` becomes `e.week_date is not None and e.week_date >= last_monday` (or similar — carry over from recent weeks)
- Selection: set `week_date = this_monday`
- No batch clear needed — old `week_date` values are just old

### action.py
- `handle_later()`: set `entry.focus_date = None` instead of removing tag
- `handle_backlog()`: set both to `None` instead of removing tags
- `handle_focus()`: set `entry.focus_date = today`, `entry.week_date = this_monday` instead of appending tags
- Undo records: store previous `focus_date`/`week_date` values instead of tag names
- `handle_clear()`: already supports date fields — add `focus_date` and `week_date` as clearable if desired

### display.py
- Remove `"today"` and `"thisweek"` from SYSTEM_TAGS import usage in `confirm_capture()` and `_build_entry_row()` — they won't appear in tags anymore, so no filtering needed
- Remove or simplify SYSTEM_TAGS to just `{"goal", "habit"}`

### cli.py
- Focus Log display: remove `hide_tags={"today", "thisweek"}` — nothing to hide
- No other changes — the view still calls `get_daily_log()` which now filters by date

### tour.py
- Remove `hide_tags={"today", "thisweek"}` from Focus Log display
- `_get_used_tags()`: SYSTEM_TAGS no longer includes today/thisweek, so filtering shrinks naturally

### views.py
- `goals_cmd()` / `goal_drill_cmd()`: SYSTEM_TAGS is smaller, filtering still works
- Daily log (`daily_log_cmd`): can now include `focus_date == target` query for retrospectives (future enhancement, not required for this change)

### query_and_load (storage.py or db.py)
- Add `focus_date` and `week_date` filter support if using DB queries
- If file-based: filter in Python after load

## Migration

One-time script run at the end of implementation:

1. Find all entries with `"today"` in tags → set `focus_date = date.today()`, remove tag
2. Find all entries with `"thisweek"` in tags → set `week_date = this_monday`, remove tag
3. Preserve file mtime after writing (use `os.utime`) to avoid the mtime corruption issue we hit earlier

The migration is imperfect — we don't know the original date these tags were set. Setting them to today/this-week is the best approximation. After the first `bt dp` / `bt wp` cycle, the data will be accurate.

## What Doesn't Change

- `@goal` and `@habit` stay as tags — they're genuinely labels
- `due`, `scheduled_date`, `scheduled_time` untouched
- All user-facing behavior identical — Focus Log, Task Log, daily plan, weekly plan show the same entries
- `bt later`, `bt backlog`, `bt focus` — same CLI grammar
- Undo support — same pattern, different fields

## Helper

Add a `_this_monday()` utility that returns the Monday of the current ISO week:

```python
def _this_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())
```
