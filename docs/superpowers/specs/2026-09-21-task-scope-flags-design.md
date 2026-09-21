# Task scope flags — collapse `bt t` / `bt b` / `bt w` into one command

**Date:** 2026-09-21
**Status:** Approved, pending implementation
**Type:** Breaking grammar change (same class as `7d0cc11`, `59801e9`)

## Problem

Tasks are the only dimension with three view commands — `bt t` (all), `bt b`
(backlog), `bt w` (this week) — and the capture flags that write to those places
carry different names than the commands that read them. `bt t -l` writes
`week_date`; `bt w` reads `week_date`. Nothing in the grammar says they are the
same place.

Three further defects fall out of the same seam:

- `--all/-a` is accepted and never read on `bt t`, `bt w`, `bt n`, `bt j`, `bt c`
  (`views.py:45`, `:79`, `:105`). It parses and does nothing.
- `-l/--later` is named for a verb, not for the field it sets.
- `bt t!` ignores scope entirely, because `important_cmd` takes a bare type
  string with no scope parameter (`views.py:168-172`).

## Design

One scope per invocation, any number of filters stacked on top, and the same
flag spells the scope whether you are reading it or writing to it.

### Scopes — exclusive, task-only

| Command | Shows |
|---|---|
| `bt t` | **Today** — the task rows of the Focus Log |
| `bt t -w` / `--week` | **This week** — active tasks, `week_date == this week's anchor` |
| `bt t -b` / `--backlog` | **Backlog** — all active tasks |

"Today" reuses the Focus Log's task selection rather than defining a second
one. Concretely, `bt t` shows:

- active tasks with `focus_date == today`
- active tasks with `due <= today` (overdue lingers)
- entries with `scheduled_date == today`
- tasks completed today, struck through

Recurring tasks are excluded from every scope; they live in `bt streak`.

### Filters — stack on the scope

| Filter | Effect |
|---|---|
| `-a` / `--all` | Include hidden: done, dropped, and today's unfocused captures |
| `@tag` / `-@tag` | Tag include / exclude |
| `!` (as `bt t!`) | Important only |

`-a` keeps the meaning it already has everywhere in bt — it widens *status*,
never *scope*. `bt -a` is "Focus Log + hidden"; `bt t -b -a` is "backlog +
done/dropped", which is the same query as today's `bt t` and therefore
preserves the full task dimension without a fourth scope flag.

All three filters compose: `bt t! -b @backend` is important, backlogged,
tagged `@backend`.

### Capture — same flags

| Command | Sets |
|---|---|
| `bt t <text>` | `focus_date = today` + `week_date = anchor` |
| `bt t -w <text>` | `week_date` only |
| `bt t -b <text>` | neither |

Unchanged: a future `date:` or `due:` still suppresses both focus fields
(`capture.py:114-118`).

`-a` has no capture meaning. `bt t -a buy milk` exits non-zero with a message
pointing at `-w` and `-b`, following the `parser.REMOVED_META_KEYS` precedent —
a rejected flag beats one silently written into the body.

### Display

Flat lists (`display_entry_list`) everywhere except `bt t -b -a`, which groups
by date (`display_entry_list_grouped`) so it renders exactly as `bt t` does
today. The rule is "group when the result spans many dates": today and
today+hidden are one day, and the week and backlog scopes are short curated
lists that need no date spine.

### Removed

- `bt b`, `bt w` — the `(b, w)` loop at `cli.py:100-105`, and `"b"` in
  `SHORT_TO_VIEW` (`cli.py:18`).
- `bt backlog`, `bt week` long forms — registrations at `cli.py:605-606`.
  `bt t -b` is the one spelling.
- `-l/--later` on capture, renamed `-w/--week`.
- `week_cmd` and `backlog_cmd` as registered commands. Their bodies become
  scope branches inside `tasks_cmd`.

`bt <n> later` and `bt <n> backlog` actions are unaffected — they are verbs,
not views, and keep their names.

## Rationale, and the case against

This was specced against usage data from 372 `bt` invocations in shell history.
The data argues both ways and is recorded here so the decision is auditable:

- `bt b` (21 views) and `bt w` (17 views) are the 4th and 7th most-used
  commands. Lengthening them costs ~114 keystrokes over the same span — close
  to the ~137 that `7d0cc11` was justified by saving.
- `bt t -l` and `bt t -b` have zero real uses, so the read/write symmetry is an
  invariant over an unused path.
- `-a` on a dimension view has six uses, every one a silent no-op. This is the
  defect the data actually supports fixing.
- `bt t` = today makes it a subset of bare `bt` (69 uses), the most-used
  command.

Accepted anyway: one entry point with a composition rule is a smaller grammar
to hold than four commands with divergent flag vocabularies, and it makes `-a`
and `!` behave the same way on every task view instead of three different ways.

## Implementation

| File | Change |
|---|---|
| `cli.py` | Add `-w`/`--week`/`-b`/`--backlog` to `view_flags` in `resolve_command` (`:109`, `:134`) and `_is_capture_like` (`:36`); delete the b/w branch (`:100-105`); drop `"b"` from `SHORT_TO_VIEW`; drop `backlog_cmd`/`week_cmd` imports and registrations; rewrite help rows `:282-283`, `:339`, `:350-351`, `:386` |
| `commands/views.py` | `tasks_cmd` gains `-w`/`-b`/`-a`, absorbs `week_cmd` and `backlog_cmd`; `important_cmd` gains a scope parameter |
| `commands/capture.py` | `-l/--later` → `-w/--week` (`:28`); reject `-a` |
| `ritual_ops.py` | Extract the task selection out of `get_daily_log` into `get_today_tasks(config, include_all)` so `bt` and `bt t` share one definition of "today" |
| `README.md` | `:30-32`, `:159`, `:254` |
| `CLAUDE.md` | CLI Grammar and Design Decisions sections |
| `completion.py`, `commands/habits.py`, `commands/tour.py`, `commands/zen.py` | stale `bt b` / `bt w` strings |

State view names stay distinct (`tasks`, `week`, `backlog`) so `bt <n> done`
numbering and `--json` `view` fields are unchanged.

## Testing

- `bt t` returns the Focus Log's task rows and nothing else — same entries as
  `bt`, filtered to tasks.
- `bt t -w` and `bt t -b` return what `bt w` and `bt b` return today.
- `bt t -b -a` returns what `bt t` returns today.
- `bt t -b buy milk` captures with no focus fields; `bt t -w buy milk` sets
  `week_date` only; `bt t buy milk` sets both.
- `bt t -a buy milk` exits non-zero and does not create an entry.
- `bt t! -b` is important ∩ backlog; `bt t! -b @backend` adds the tag filter.
- `bt b` and `bt w` exit non-zero with Click's unknown-command error.
- `bt n --json add -w flag to parser` still stores the literal text — the
  `_is_capture_like` guard must survive the new flags.
- Existing suites to update: `test_views.py`, `test_help_grammar.py`,
  `test_json_output.py`, `test_action.py`, `test_rituals.py`.

## Risk

Breaking change to one user's muscle memory. No on-disk format change, so no
data migration. The README's data-model contract for external agents is
untouched; only its CLI examples move.
