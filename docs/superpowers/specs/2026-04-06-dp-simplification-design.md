# dp Simplification — Daily Plan as Task Picker

**Date:** 2026-04-06
**Status:** Draft

## Problem

The current `dp` ritual (DYTS: Dump, Yesterday, Tasks, Schedule + Habits) has five phases, most of which duplicate functionality available elsewhere:

- **Dump** — capture works anywhere (`bt t ...`, `bt n ...`)
- **Yesterday** — unresolved tasks are visible in `bt t` and the tasks pool
- **Schedule** — calendar events already appear in the Focus Log
- **Habits** — already appear in the Focus Log

The only irreplaceable value is the **Tasks** phase — choosing what to focus on today.

## Design

### What `dp` becomes

A single-phase **task picker** with the header "Daily Plan":

1. Query yesterday's unresolved tasks via `get_yesterday_unresolved(config)`
2. Query weekly active tasks via `get_weekly_active_tasks(config)` (falls back to all active if no `@thisweek` tasks exist)
3. Deduplicate — yesterday's tasks may overlap with the weekly pool
4. Present a single `questionary.checkbox` list:
   - **Top section:** Yesterday's unresolved tasks, highlighted with a `↩` prefix to indicate carryover
   - **Bottom section:** Remaining `@thisweek`/backlog tasks (excluding those already shown in yesterday section)
   - **Pre-checked:** Tasks already tagged `@today`
5. On submit: add `@today` to newly selected tasks, remove `@today` from deselected tasks
6. Call `mark_dyts_done(config)` to gate Focus Log access
7. Print confirmation: `"X tasks tagged for today."`

### Non-interactive mode (`-y`)

Show the current `@today` selection count and mark done. No checkbox prompt. Same as a pass-through — useful for scripts or when the user just wants to unlock the Focus Log.

### Yesterday highlighting

Questionary checkbox choices support styled text via `questionary.Choice`. Yesterday's entries use a `↩` prefix:

```
❯ ◉ ↩ call dentist
  ◯ ↩ review PR #42
  ◯ deploy staging
  ◯ write API docs
```

The `↩` visually separates carried-over tasks from the rest of the pool without requiring a separate phase.

### Gate behavior

Unchanged:
- `bt` (no args) checks `is_dyts_done_today(config)`
- If not done → invokes `dp_cmd`
- If done → shows Focus Log
- `mark_dyts_done()` writes today's ISO date to `.dyts_date`

### What gets removed from `dp_cmd`

| Phase | Replacement |
|-------|-------------|
| D (Dump) | Capture via `bt t/n/j/c ...` from anywhere |
| Y (Yesterday) | Highlighted section at top of task picker |
| S (Schedule) | Already in Focus Log |
| H (Habits) | Already in Focus Log |
| Per-entry Y prompts (keep/drop/done/later) | Just selection — status changes via `bt <n> done/drop` |
| Per-event S prompts (include in log?) | Calendar auto-surfaces in Focus Log |

### What stays unchanged

- `mark_dyts_done()` / `is_dyts_done_today()` gate mechanism
- `@today` / `@thisweek` tag semantics
- `bt wp` — weekly curation is independent
- Command name: `dp`
- Focus Log contents and display
- `clear_daily_focus()` function (available but not called by dp — manual use)

## Code changes

| File | Change |
|------|--------|
| `src/bute/commands/rituals.py` | Rewrite `dp_cmd`: remove D/Y/S/H phases, replace with single checkbox picker |
| `src/bute/cli.py` | Update help text / cheat sheet description for `dp` |
| `src/bute/ritual_ops.py` | No changes — existing functions (`get_yesterday_unresolved`, `get_weekly_active_tasks`, `mark_dyts_done`) are reused as-is |
| `src/bute/display.py` | No changes |
| `src/bute/state.py` | No changes |
| Tests | Update `dp` tests to reflect single-phase behavior, remove DYTS phase tests |

## CLAUDE.md updates

- Update the Rituals section: `dp` description changes from "morning ritual (Dump, Yesterday, Tasks, Schedule)" to "morning ritual — pick today's tasks from weekly focus"
- Update the Backlog section: mark "Redesign Daily Plan" as done, remove "Focus Process" rename (keeping `dp` / "Daily Plan")
