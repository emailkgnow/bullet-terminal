# bt recap — End-of-Day Summary

## Overview

Read-only day summary with AI coaching narrative. No prompts, no decisions — "here's your day" plus a forward-looking nudge. Evening counterpart to the morning `bt dp`.

## CLI Interface

```
bt recap          # today's recap
bt recap -q       # quiet — structured data only, skip AI
```

## Structured Display (always shown)

Five sections rendered as a single table/output:

1. **Done** — tasks completed today (status changed to done today, or done tasks tagged @today)
2. **Open** — @today tasks still active (carrying forward)
3. **Dropped** — tasks dropped today (status changed to dropped today)
4. **Captured** — journals, notes, events created today (show counts per type + the entries)
5. **Habits** — today's habit checklist status (same rendering as dp)

If a section is empty, skip it (no "No items" placeholder — keep it clean).

### Data Queries

- **Done today**: tasks where `status == done` and either created today or tagged @today. Need to detect tasks marked done today — check entries modified today with done status. Since entries are .md files with YAML frontmatter, "modified today" = file mtime is today.
- **Open @today**: tasks where `status == active` and `"today" in tags`.
- **Dropped today**: same approach as done — dropped status + mtime today.
- **Captured today**: all non-task entries created today (`load_entries_by_date(today)`), grouped by type.
- **Habits**: use existing `get_habit_summary()`.

### Alternative for done/dropped detection

Since we don't track status-change timestamps, use file modification time (mtime) as a proxy. A task is "done today" if `status == done` and `Path(entry_file).stat().st_mtime` is today. Same for dropped.

## AI Narrative

- Appears **after** the structured data
- Coaching tone: acknowledge wins, note patterns, give a light nudge for tomorrow
- 3-5 sentences max
- Uses existing `send_with_entries()` from `ai/llm.py`
- Prompt template added to `ai/prompts.py`
- When AI unavailable: skip silently (structured data stands alone)
- `-q` flag skips AI even when available

### Prompt Direction

System prompt should instruct the LLM to:
- Summarize accomplishments briefly
- Note what's carrying forward without judgment
- Identify patterns (e.g. "you focused on @backend today")
- Give one concrete, light suggestion for tomorrow
- Keep it to 3-5 sentences, warm but not cheesy

## Evening Reminder

When `bt ls` runs after 6pm and recap hasn't been run today, show:
```
  Run bt recap for your day summary
```
(dim styling, single line, after the daily log output)

### State Tracking

- `.recap_date` file in data dir (same pattern as `.dyts_date`)
- `mark_recap_done(config)` writes today's ISO date
- `is_recap_done_today(config)` checks it
- Written after recap completes successfully

## Files to Modify

| File | Change |
|------|--------|
| `commands/rituals.py` | Add `recap_cmd` command |
| `ritual_ops.py` | Add `get_tasks_done_today()`, `get_tasks_dropped_today()`, `get_today_captured()` |
| `state.py` | Add `mark_recap_done()`, `is_recap_done_today()` |
| `ai/prompts.py` | Add `recap_prompt()` template |
| `commands/views.py` | Add evening reminder to `ls_cmd` |
| `cli.py` | Register `recap_cmd`, add to help text |
| `display.py` | Add `display_recap()` if needed (or reuse existing display functions) |

## Design Decisions

- **Read-only**: no interactive prompts. If you want to act on entries, use `bt <n> done` etc.
- **mtime-based detection**: imperfect (editing a done task re-triggers it) but good enough without adding a status-change timestamp field.
- **No period argument**: always today. Use `bt review` for multi-day AI synthesis.
- **Reminder is passive**: dim hint in `bt ls`, not a modal prompt.
