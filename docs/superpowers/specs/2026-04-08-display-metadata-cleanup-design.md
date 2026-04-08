# Display Metadata Cleanup

## Context

Entry metadata (tags, due dates, times) is currently shown as a plain dim string in a right-aligned column. System tags like `@thisweek` and `@today` add noise — the view itself already communicates that context. The relevance percentage in `bt like` results is also unnecessary since ordering already communicates match quality. This change cleans up metadata display across all views.

## Target Output

```
 1   .  fix broken test suite · @bt @backend · due:fri
 2   o  dentist appointment · t:2:30 PM · d:4.10
 3   -  check OAuth docs · @backend
 4   .  call dentist · due:tomorrow
```

- **Tags**: dim, `@` prefixed. System tags (`goal`, `today`, `thisweek`, `habit`) hidden.
- **Dates/times**: cyan. `due:`, `t:` (time), `d:` (scheduled_date) prefixes.
- **Dot separator** (`·`): dim, placed between body and first metadata group, and between tags and dates if both present.
- **Relevance %**: removed from `bt like` results entirely.

## Functions to Modify

### `_build_entry_row()` (display.py:97-128)

Core change. Currently returns a plain meta string. Will return a Rich `Text` object with mixed styles.

**New meta building logic:**
1. Collect user tags (exclude `SYSTEM_TAGS`) → dim `@tag` strings
2. Collect date parts (due, scheduled_time, scheduled_date) → cyan strings
3. Build a `Text` object: `· ` dim separator, then tags dim, then `· ` dim separator, then dates cyan
4. Only include separators between groups that are non-empty
5. `hide_tags` parameter continues to work (applied before system tag filtering)

### `display_search_results()` (display.py:345-389)

- Remove relevance score calculation and display
- Filter system tags from `entry.tags`
- Use same `· ` separator and dim tags / cyan dates styling
- Show due/time if present (currently not shown — add them)

### `confirm_capture()` (display.py:23-63)

- Filter system tags from tag display

## System Tags Constant

Already exists in `models.py:34`:
```python
SYSTEM_TAGS = {"goal", "today", "thisweek", "habit"}
```

Import this in `display.py` and use for filtering.

## Date Display Format

- `due:` prefix + date value (existing format)
- `t:` prefix + 12h time from `format_time_display()` (e.g., `t:2:30 PM`)
- `d:` prefix + scheduled_date (e.g., `d:Apr 10`)

Use short month-day format for scheduled_date to keep it compact.

## What Stays the Same

- Table column structure (4 columns for flat, 5 for grouped)
- Entry body rendering (first sentence, `>` for long entries, strikethrough for done/dropped)
- Sorting (important first, resolved last)
- Grouping logic in `display_entry_list_grouped()`
- `display_action_confirmation()` — no metadata, untouched
- `hide_tags` parameter functionality

## Files to Modify

1. `src/bute/display.py` — `_build_entry_row()`, `display_search_results()`, `confirm_capture()`

## Verification

1. `bt t` — tasks show user tags dim, dates cyan, no `@thisweek`
2. `bt like productivity` — no relevance %, tags dim, dates cyan
3. `bt like 1` — same styling, no relevance %
4. `bt d` — daily log entries show metadata correctly
5. `bt n` — grouped notes show metadata correctly
6. `bt t call dentist due:friday @backend` — capture confirmation hides system tags
7. `bt c meeting t:9 d:4.15` — time and date show in cyan
