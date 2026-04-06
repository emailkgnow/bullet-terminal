# Guided Tour — First-Run Onboarding Experience

## Problem

A new user installs bt, types `bt`, and hits the Daily Plan (`dp`) with zero entries. Every phase is empty — Dump has nothing to dump, Yesterday has nothing, Tasks has nothing, Schedule has nothing. The first impression is a hollow ceremony that teaches nothing.

The existing `bt start` command is a static cheat sheet. It shows the grammar but doesn't teach by doing.

## Solution

An interactive guided tour that runs automatically the first time a user launches bt with no entries. The tour uses a coaching REPL — the user types real bt commands that create real entries, with brief explanations between each step. By the end, the user has a populated system and understands every core concept through experience.

## Design Principles

- **Learn by doing.** No walls of text. Each concept is: brief intro → type a command → see the result.
- **Layers build on layers.** Each phase proves the previous one. Tasks first, then tags enrich them, then the Focus Log shows everything together.
- **Real data.** The user types their own tasks, notes, journals. By the end of the tour, they have a real system, not a throwaway sandbox.
- **AI is separate.** The core tour teaches the BuJo methodology with no AI dependency. AI features have their own tour triggered after `bt init`.
- **No new concepts to unlearn.** The tour REPL is the same as `bt -i`. Commands are the same as terminal usage without the `bt` prefix.

## Trigger & Entry Point

```
bt (no args, no subcommand)
  → no entries exist and tour not done? → run tour
  → tour done, dp not done today?       → run dp
  → tour done, dp done today?           → show Focus Log
```

- No config check. If `config.toml` doesn't exist, bt creates data dirs with defaults and starts the tour.
- Tour completion is marked by `~/.config/bute/.tour_done` (empty file).
- Tour progress is saved to `~/.config/bute/.tour_progress` (phase number) for resume on Ctrl+C.
- No `bt tour` command. The tour is a one-time first-run experience.
- `bt -d` (demo mode) is unrelated and unchanged.

## Phase Overview

11 phases, following the narrative arc: **capture → see → organize → act → plan**.

| # | Phase | Concepts Taught |
|---|-------|----------------|
| 1 | Tasks | `t`, `t @tag`, `t!` |
| 2 | Notes | `n`, `n @tag1 @tag2` |
| 3 | Journals | `j`, `j @tag` |
| 4 | Calendar | `c` with `d:` and `t:` |
| 5 | Focus Log | `bt` — see everything together |
| 6 | Tag Filter | `@tag` — search across all entry types |
| 7 | Habits | `h <name>` — daily tracking |
| 8 | Logs | `d`, `w`, `m` — wider lenses |
| 9 | Views | `t`, `n`, `b` — filtered lenses |
| 10 | Actions | `1 done`, `2 !`, `bt` — act by number |
| 11 | Daily Plan | `dp` — the morning ritual |

## Phase Details

### Phase 1: Tasks

> "Tasks are things you need to do. The letter `t` captures a task."

- **Step A:** "Try it — type something like: `t call dentist`"
  - Validate: any task captured
  - Feedback: shows the entry with the `·` signifier. "That dot means task."
- **Step B:** "Tags help you organize. Add one with @. Try: `t read book @health`"
  - Validate: task with at least one tag
  - Feedback: "Tagged @health. You can filter by tags later."
- **Step C:** "Mark something urgent with `!`. Try: `t! fix the leak @home`"
  - Validate: important task
  - Feedback: "The `!` marks it important. It'll stand out in every view."

### Phase 2: Notes

> "Notes are ideas, facts, things worth remembering."

- **Step A:** "Capture a note with `n`. Try: `n check OAuth token expiry @backend @security`"
  - Validate: note with at least one tag
  - Feedback: shows the `—` signifier. "Notes use the dash. Multiple tags work too."

### Phase 3: Journals

> "Journals are reflections — what you're thinking or feeling."

- **Step A:** "Type: `j excited to try this`"
  - Validate: journal captured
  - Feedback: shows the `=` signifier. "Journals use the equals sign."
- **Step B:** "Journals can have tags too. Try: `j need to be more focused @growth`"
  - Validate: journal with tag

### Phase 4: Calendar

> "Calendar events have dates and times. `d:` sets the date, `t:` sets the time."

- **Step A:** "Try: `c dentist appointment d:tomorrow t:14.30`"
  - Validate: calendar event with date and/or time
  - Feedback: "That's set for tomorrow at 2:30 PM. Calendar events use the `○` signifier."

### Phase 5: Focus Log

> "Let's see everything together."

- **Step:** "Type: `bt`"
  - Shows the Focus Log with all entries created so far
  - Feedback: "This is your Focus Log — your home screen. Everything that matters today, in one place."

### Phase 6: Tag Filter

> "Remember the @tags you've been adding? They work across everything."

- **Step:** "Type: `@<tag>`" (suggests a tag the user actually used in previous phases)
  - Shows all entries with that tag, regardless of type
  - Feedback: "Tasks, notes, journals, calendar — tags cut across all of them."

### Phase 7: Habits

> "Track daily habits you want to build."

- **Step A:** "Type: `h reading`"
  - Creates and logs the habit
  - Feedback: "Habit tracked. It'll show up in your Focus Log every day."

### Phase 8: Logs

> "Logs show everything for a time period — like zooming out."

- **Step A:** "Type: `d`" — daily log
  - Feedback: "The daily log shows everything that happened today."
- **Step B:** "Type: `w`" — weekly log
  - Feedback: "Same idea, wider lens. `w last` for last week, `w 14` for week 14."
- **Step C:** "Type: `m`" — monthly log
  - Feedback: "Monthly view. `m jan` for January, `m 2026` for a full year."

### Phase 9: Views

> "Views filter by entry type — like zooming in."

- **Step A:** "Type: `t`" — tasks view
  - Feedback: "Just your tasks. `n` for notes, `b` for the full backlog."
- **Step B:** "Type: `b`" — backlog
  - Feedback: "The backlog is every active task. `bt t` shows this week's focus."

### Phase 10: Actions

> "Act on entries by their number. Let's see the list first."

- **Step A:** "Type: `bt`" — Focus Log with numbers
- **Step B:** "Type: `1 done`" — mark first entry complete
  - Feedback: "Done. Strikethrough means completed."
- **Step C:** "Type: `2 !`" — toggle important
  - Feedback: "Toggled important. `drop` consciously deletes, `@tag` adds a tag."
- **Step D:** "Type: `bt`" — see the changes reflected
  - Feedback: "See the changes? That's the capture → view → act loop."

### Phase 11: Daily Plan

> "You've learned the pieces. The Daily Plan ties them together as a morning ritual."

- **Step:** "Type: `dp`"
  - Runs through the actual dp flow
  - Feedback: "Start every morning with `bt dp`. It walks you through planning your day."

### Outro

> "That's bt. Capture fast, act by number, plan each morning."
>
> "To use this interactive mode again: `bt -i`"
> "In the terminal, prefix everything with bt: `bt t call mom`"
> "For AI features (search, chat, analysis): `bt init`"
> "Cheat sheet: `bt start` · Full help: `bt -h`"

## UX & Edge Cases

### Prompt & Pacing
- REPL uses `>` as the prompt, same as `bt -i`.
- Coaching text is indented, uses Rich markup for color/emphasis.
- Each phase starts with a 1-2 line intro. No walls of text.
- The user should spend more time typing than reading.

### Ctrl+C
- Exits tour cleanly, saves progress to `~/.config/bute/.tour_progress`.
- Message: "Tour paused. Run `bt` to pick up where you left off."
- Next `bt` invocation resumes at the interrupted phase.

### Unexpected Input
- Wrong entry type (typed `n` when asked for `t`) → accept it, don't block. Gently say "That created a note — try `t` for a task."
- Random command (typed `w` during phase 1) → execute normally, then re-show the current step's prompt.
- Empty input → re-show the hint.

### Skipping
- `/skip` jumps to the next phase.
- `/done` ends the tour entirely and marks it as complete.
- Ending early marks the tour as complete — it won't re-trigger.

### Phase 6 (Tag Filter)
- The tour inspects entries created so far to find a tag the user actually used, and suggests that specific tag. Not a hardcoded example.

### Phase 10 (Actions)
- Depends on numbered entries. The tour shows the Focus Log first so the user has a numbered list.
- Adapts instructions if fewer entries than expected.

### Phase 11 (Daily Plan)
- Runs the real `dp` command. Since the user has entries now, Dump and Tasks phases have content. Yesterday will be empty (first day). Schedule depends on whether they created calendar events for today.

## What Changes in Existing Code

### Modified files

**`cli.py` — `main()` function:**
- Add tour check before the dp/Focus Log branch. If no entries and no `.tour_done` marker → invoke tour.
- No other changes to dispatch logic.

**`config.py`:**
- `ensure_data_dirs()` needs to work without a config file — create `~/bute/entries/` with sensible defaults even if no `config.toml` exists.

### Unchanged files

- `start.py` — stays as-is, referenced at end of tour.
- `_run_interactive()` — unchanged. Tour has its own REPL loop.
- All other commands, display, storage, state — untouched.

### New files

- `src/bute/commands/tour.py` — all tour logic: phase definitions, coaching text, validation, REPL loop.

### New markers

- `~/.config/bute/.tour_done` — empty file, prevents re-triggering.
- `~/.config/bute/.tour_progress` — single number, tracks current phase for resume.

## AI Tour (Separate Spec)

Triggered after `bt init` successfully configures an AI provider. Teaches the AI layer on top of existing entries:
- `search <query>` — semantic search
- `3 chat` — think through an entry with AI
- `recap week` — AI analysis of a period
- `nudges` — actionable suggestions
- `analyze @tag` — AI clusters a tag group
- `tag-notes` — AI suggests tags for untagged entries

This is a separate spec and implementation.

## Backlog (Out of Scope)

- **Redesign Daily Plan (`dp`):** Decompose Dump into individual entry types (t, n, j, c) mirroring the tour's layered approach. Rename to "Focus Process" since it flows into the Focus Log. Separate spec.
