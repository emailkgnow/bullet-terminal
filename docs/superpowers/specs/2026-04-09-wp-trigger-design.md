# Weekly Plan Trigger Design

**Date:** 2026-04-09
**Status:** Draft

## Problem

The daily plan (`dp`) triggers automatically on the first `bt` call after midnight, but the weekly plan (`wp`) is manual-only. This creates an asymmetry — users must remember to run `bt wp` themselves. The two rituals should share the same trigger-and-gate pattern.

## Design

Unify `wp` with `dp` so that both are triggered automatically by `bt` (no args). The weekly plan fires on a configurable day (default Sunday), persists until completed, and chains into the daily plan.

### Cascade

```
backlog → wp (@thisweek) → task log → dp (@today) → focus log
```

Both transitions use the same mechanic: show a pool of tasks, highlight carryover from the previous period, user picks, tag, mark done.

## State Management

Two new functions in `state.py`, mirroring the dp pattern:

- **`mark_wp_done(config)`** — writes current ISO week number (e.g. `"2026-W15"`) to `.wp_date`.
- **`is_wp_done_this_week(config)`** — reads `.wp_date`, returns `True` if stored value matches the current ISO week.

Trigger condition: `today.weekday() >= wp_day_number` AND `is_wp_done_this_week()` is `False`.

Persistence: if the user misses the trigger day, wp keeps firing on every `bt` call until completed — no expiry.

## CLI Trigger Flow

In `cli.py`, the `bt` (no args) block checks wp **before** dp. The order:

1. **First-run tour?** → run tour, return.
2. **wp due this week?** → invoke `wp_cmd`, then fall through to dp check.
3. **dp done today?**
   - Yes → show Focus Log.
   - No → invoke `dp_cmd`.

On the trigger day (Sunday), first `bt` call runs: **wp → dp** in sequence. wp completes and marks done, then dp fires because it hasn't been done today.

On non-trigger days, wp is skipped (already done this week) and only dp is checked.

If the user missed Sunday and it's now Wednesday, wp still fires first (persists until done), then dp follows.

`bt dp` called directly skips the wp check — only `bt` (no args) chains them.

## WP Command Changes

### Carryover highlight

Last week's `@thisweek` tasks appear at the top of the selection list with a `↩` icon (same pattern as dp showing yesterday's unresolved tasks). All other backlog tasks appear below. Tasks that still have `@thisweek` are pre-checked.

### Auto-cleanup

After selection, unselected tasks that had `@thisweek` lose the tag silently. No prompt, no summary — they return to backlog. The existing `clear_weekly_selection()` function handles this.

### Completion marker

`mark_wp_done(config)` is called at the end of `wp_cmd`, same as dp calls `mark_dp_done`.

### Dump phase

The inline "add tasks" prompt remains — users can capture tasks before selecting.

### Non-interactive flag

`--non-interactive` (`-y`) skips prompts and marks done, same as dp.

## Configuration

A single new key in `config.toml`:

```toml
[core]
wp_day = "sunday"    # day weekly plan triggers (monday-sunday)
```

- Default: `"sunday"` (hardcoded fallback if key is missing).
- Accepted values: `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday`, `sunday` (lowercase).
- No new `bt init` phase — users who want a different day edit config manually.

## Edge Cases

- **First ever run**: No `.wp_date` file → wp triggers on the first `bt` call on or after the trigger day. If no tasks exist, wp shows "No tasks to plan", still marks done so dp can proceed.
- **Manual `bt wp`**: Always works regardless of trigger state. Still marks wp done so it won't re-trigger that week.
- **Week boundary**: ISO week starts Monday. Sunday is the last day of the ISO week. `.wp_date` stores the current ISO week string (the week during which planning happened).
- **Config change mid-week**: Trigger re-evaluates on next `bt` call. If wp is already done this week, no re-trigger.

## Files Changed

| File | Change |
|------|--------|
| `src/bute/state.py` | Add `mark_wp_done()`, `is_wp_done_this_week()` |
| `src/bute/cli.py` | Add wp trigger check before dp check in no-args block |
| `src/bute/commands/rituals.py` | Modify `wp_cmd`: carryover highlight, call `mark_wp_done()` |
| `src/bute/config.py` | Add `wp_day` config key with `"sunday"` default |
| `tests/test_rituals.py` | Add wp trigger tests, wp-then-dp chaining test |

## Summary Table

| | Weekly Plan (`wp`) | Daily Plan (`dp`) |
|---|---|---|
| **Source** | Backlog (all active tasks) | Task Log (`@thisweek`) |
| **Destination** | Task Log (`@thisweek`) | Focus Log (`@today`) |
| **Trigger** | First `bt` on or after configured day | First `bt` after midnight |
| **Default trigger** | Sunday | Every day |
| **Highlight** | Last week's `@thisweek` tasks (↩) | Yesterday's `@today` tasks (↩) |
| **Cleanup** | Unselected lose `@thisweek` silently | Unselected lose `@today` |
| **State file** | `.wp_date` (ISO week string) | `.dp_date` (ISO date string) |
| **Persists** | Until done (no expiry) | Until done (no expiry) |
| **Config** | `core.wp_day` | None (daily) |
