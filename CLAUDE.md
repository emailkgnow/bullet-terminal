# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is bt?

bt (Bullet Terminal) is a CLI life management system based on the Bullet Journal methodology. Single user, local data, plain Markdown files. The name mirrors BuJo (Bullet Journal) — same family, different medium. The distribution is `bullet-terminal`; the Python import package is still `bute` (invisible to users, so it was never renamed).

## Development Commands

```bash
# Install all deps (dev + optional)
uv sync --extra embeddings --extra dev

# Run tests
uv run pytest                         # all tests
uv run pytest tests/test_capture.py   # single module
uv run pytest -m "not slow"           # skip embedding tests
uv run pytest --cov=src/bute          # with coverage

# Install globally (for manual testing)
uv tool install --from . --with fastembed --with sqlite-vec bullet-terminal --force --reinstall

# Build
uv build
```

## Architecture

### CLI Dispatch (cli.py — DwnGroup)

Custom Click group with 5-layer routing in `resolve_command()`:

1. **Named commands** — standard Click (dp, tasks, backlog, notes, tags, etc.)
2. **Letter shortcut** — `b` → backlog, `m` → monthly
3. **Signifiers** — `t`, `n`, `j`, `c` (or full words: `task`, `note`, `journal`, `calendar`)
   - With text → **capture** (`bt t call dentist`)
   - Without text → **view** (`bt t` → show Tasks / weekly focus)
   - With only `@tag` → **filtered view** (`bt t @backend`)
4. **Tag filter** — `@tagname` → cross-dimension filter (multi-tag: `@a @b -@c`)
5. **Number-action** — `1 done`, `2 3 drop` → action dispatch

Bullet symbols (`. - = o`) are used in display output but not accepted as CLI input — they conflict with shell metacharacters (`=` in zsh, `-` as option prefix). Use letter shortcuts instead.

### Data Model

- **Entry types**: task (`.`), note (`-`), journal (`=`), calendar (`o`)
- **Task statuses**: `active`, `done`, `dropped` (no `migrated` — removed by design)
- **IDs**: ULID (time-sortable, 26 chars)
- **Storage**: one `.md` file per entry at `~/bullet-terminal/entries/{type}/YYYY-MM/<ULID>.md`
- **Tags**: `@tag` syntax in CLI, stored as plain strings in YAML frontmatter. Pure organizational labels for cross-dimension filtering. Stage tracking in `tag_stages` SQLite table is a remnant of the removed AI analyze feature — harmless, may be pruned later.

### Data Flow

```
User input → DwnGroup.resolve_command() → capture.py
  → parser.py:parse_capture_tokens() — extracts signifier, body, key:value, @tags
  → models.py:Entry.create() → storage.py:save_entry() → embed → confirm_capture()
```

### State Management

`.state.json` stores the last displayed list as `{"view": "tasks", "entries": ["ulid1", "ulid2"]}`. Display numbers (1, 2, 3) map to ULIDs. Numbers re-scope on each new view.

### Key Modules

| Module | Role |
|--------|------|
| `cli.py` | DwnGroup dispatch + command registration + help text |
| `parser.py` | Signifier/metadata/@tag parsing, date/time resolution |
| `models.py` | Entry dataclass, EntryType/TaskStatus enums, SIGNIFIER_MAP |
| `storage.py` | Markdown file I/O, query by date/filter, handles legacy `migrated` status |
| `display.py` | Rich rendering: `display_entry_list`, `display_entry_list_grouped`, confirmations |
| `ritual_ops.py` | Pure functions for rituals (Focus Log, yesterday unresolved, schedule, active tasks) |
| `state.py` | View-to-action bridge, daily plan completion tracking |
| `ai/vectors.py` | sqlite-vec wrapper (upsert, search, delete) |
| `ai/embeddings.py` | fastembed wrapper, lazy model loading |
| `db.py` | SQLite index — metadata, FTS5, vec_entries, and lazy reconciliation |
| `commands/tags.py` | Tag listing and filtering helpers |

### Local search tier (no LLM)

1. **Embeddings** (local) — fastembed ONNX model, no API key needed
2. **Vector DB** (local) — sqlite-vec, rebuildable from .md files via `bt rebuild`
3. **Lazy reconciliation** — `db.reconcile_index()` runs once per process on first read and detects externally-added/removed `.md` files, upserting or deleting matching rows. Enables the "bring your own AI" model where external agents (Claude Desktop + filesystem MCP, Claude Code, scripts) write valid .md files into `entries/` and bt picks them up automatically.

There is no built-in LLM. `bt chat` was removed in favor of BYOAI — the README's data-model section is the contract external agents read. When you change the data model, update README.md in the same commit.

## CLI Grammar (Current)

**Capture** — signifier + text:
```
bt t call dentist due:friday @backend    # single letter
bt task call dentist due:friday @backend # full word
bt t! fix prod bug                       # important modifier
bt c dentist t:14.30 d:3.30              # calendar: Mar 30 at 2:30 PM
bt c meeting t:9                         # calendar: today at 9:00 AM
bt c conference d:4.15                   # calendar: Apr 15, all day
bt n check OAuth docs d:4.10             # note: resurfaces in Focus Log Apr 10
```

**Date/time metadata:**
- `d:` — date. Formats: `d:4.7` (MM.DD), `d:today`, `d:tomorrow`, `d:friday`, `d:next-friday` (week after the upcoming Friday), `d:mar15`. Legacy `d:0407` still works.
- `t:` — time in 24h. Formats: `t:9` (9:00), `t:14.15` (2:15 PM). Legacy `t:1430` still works.
- `due:` — deadline for tasks (supports same formats as `d:`)

**Views** — signifier alone, or named commands:
```
bt t              # Tasks — this week's focus (@thisweek)
bt t @backend     # filtered by tag
bt t -a           # all including done/dropped
bt b              # Task Backlog — all active tasks
bt n / j / c      # notes / journals / calendar (grouped by date)
bt -a             # Focus Log + hidden items (dropped, non-focus captures, past events)
bt m              # monthly log (all entries for the month)
bt m jan          # January's log (full or abbreviated name)
bt m 2026-03      # March 2026
bt m 2026         # all months of 2026
bt                # Focus Log (or daily plan if not done today)
bt @tagname       # cross-dimension tag filter
bt @bt @ai        # entries with both tags (AND)
bt @bt -@done     # entries with @bt but not @done
bt -@habit        # all entries excluding @habit
bt !              # all important entries
bt t!             # important tasks (also: n!, j!, c!)
bt find <keyword> # partial-word search in full body + tags (-t -n -j -c to filter)
bt like <input>   # semantic similarity (bt like 3, bt like productivity)
bt b --json         # numbered entry views as JSON (n = display number); not stats/streak/actions/captures
```

**Actions** — number + command:
```
bt 1 done         # mark complete
bt 2 3 drop       # consciously delete (space-separated)
bt 1-4 done       # range — marks 1, 2, 3, 4 done
bt 1-3 7 done     # mix range + bare numbers
bt 4 delete       # move to .trash/ (recoverable)
bt trash          # list trashed entries; bt trash empty -y to purge
bt 2 restore      # restore entry 2 from the trash view
bt 5 !            # toggle important
bt 6 @tag         # add tag
bt 6 clear @tag   # remove tag
bt 6 clear !      # remove important
bt 6 clear due    # clear due date
bt 6 clear d      # clear scheduled date
bt 6 clear t      # clear time
bt 6 clear repeat # clear repeat
bt 7 edit         # open in $EDITOR
bt 3 show         # read entry in glow pager, q to quit (aliases: view, read)
bt 3 later        # defer — remove from today's log
bt undo           # undo last action
bt 3 undo         # undo last action on entry 3
```

**Tags**:
```
bt tags                           # list all tags with stage and count
```

**Rituals**:
```
bt                # entry point — weekly plan (on trigger day) → daily plan → Focus Log
bt dp             # morning ritual — pick today's tasks
bt wp             # weekly plan — select tasks for the week (auto-triggers on configured day)
bt habit <name>   # track habits
bt streak         # habit streaks and 30-day stats
```

**System**:
```
bt stats          # personal analytics (week/month views, streaks)
bt export         # zip backup of all data to cwd (-o path)
bt rebuild        # rebuild search index from .md files
bt init           # first-run setup (create config + data dirs)
bt completion     # print the shell line that enables @tag tab completion
```

## Design Decisions

- **No migrate** — removed. Tasks stay `active` until `done` or `dropped`. Daily plan handles yesterday's unfinished items.
- **Tags are plain labels** — organize entries and power cross-dimension filters. The `+collection` syntax was removed — tags absorbed collections. A `tag_stages` SQLite table from the removed AI analyze feature still exists; harmless, may be pruned later.
- **Logs are derived** — no stored files. Focus Log (`bt`), monthly log (`bt m`) query entries for their period. Tasks show status (done = strikethrough, dropped = strikethrough + label). `bt -a` expands the Focus Log to include dropped tasks, non-focus captures from today, and past-timed events — replaces the retired `bt d`/`bt w`.
- **`bt m` is event-driven** — each entry surfaces on every day any of its lifecycle events occurred (captured, focused, scheduled, completed, dropped, undropped). Events are stored as a YAML `events:` list in the entry's frontmatter, appended by every mutation site (capture, dp, wp, done, drop, later, backlog, schedule, mod, undo). Legacy entries without a stored `events` list use render-time synthesis from `created`, `scheduled_date`, `focus_date`, `completed_date`. This makes `bt m` a BuJo retrospective — you can relive each day of the month.
- **`bt` with no args** = planning entry point. On the trigger day (default Sunday, configurable via `core.wp_day`), runs weekly plan then daily plan. Other days, runs daily plan only. If all done, shows Focus Log.
- **Focus Log (`bt`)** — what matters today: tasks with `focus_date == today`, tasks due today or overdue, today's calendar events, all today's journals and notes. Any entry with `d:` (scheduled_date) matching today also surfaces. Other tasks stay in Backlog (`bt b`) or Tasks (`bt t`). Curated and active-only — `bt -a` expands to dropped tasks, captures from today that lack focus, and past-timed events.
- **Task views**: `bt t` (Tasks) shows tasks with `week_date == this Monday`. `bt b` (Backlog) shows all active tasks. The flow is: backlog → weekly plan → tasks → Focus Log.
- **Focus state as dates, not tags** — `focus_date` and `week_date` are proper `Optional[date]` fields on `Entry`. Set by `bt dp` / `bt wp` / `bt focus` / capture. Cleared by `bt later` / `bt backlog`. Old dates expire naturally — no clearing ritual needed. Replaces the former `@today` / `@thisweek` system tags.
- **`bt wp`** includes task dump phase — add tasks before selecting for the week.
- **Display**: tasks = flat list, notes/journals/calendar = grouped by date (using `scheduled_date` for calendar events).
- **Scheduling is universal** — `d:` (scheduled_date) works on all entry types. Tasks: deadline. Calendar: event date. Notes/journals: resurface date. All surface in the Focus Log on the target date. Only tasks can be overdue (past-due tasks linger; missed note/journal reminders don't).
- **Calendar sorting**: timed events first (chronologically), then untimed, then other entry types.
- **Time format**: stored as `HH:MM` (24h), displayed as `h:MM AM/PM`. Preferred input: `t:9`, `t:14.30`. Legacy formats (`t:1430`, `3pm`) still accepted.
- **Date format**: preferred input: `d:4.7`, `d:mar15`, `d:tomorrow`, `d:friday`. Legacy `d:0407` still accepted.
- **API key**: resolved from config value, `keychain:<service>`, or auto-lookup in macOS Keychain.
- **No built-in AI** — `bt chat` and the LLM layer were removed in favor of "bring your own AI." External agents (Claude Desktop + filesystem MCP, Claude Code, scripts) read/write `.md` files directly in `~/bullet-terminal/entries/`. bt's README is the schema contract; `db.reconcile_index()` picks up external writes on the next read. Local semantic search via `bt like` stays — it uses fastembed + sqlite-vec, no network.

## Backlog

### Commands — High Value
- ~~**Stale `@today`/`@thisweek` tag cleanup**~~ ✓ Done — replaced by `focus_date` and `week_date` date fields on `Entry`. Old dates expire naturally (a `focus_date` from last week simply doesn't match today's Focus Log), so no clearing ritual is needed. See `docs/superpowers/specs/2026-04-16-focus-date-fields-design.md`.
- ~~`bt due`~~ ✓ Done — overdue + due today + next 7 days (rolling). `bt due all` for all tasks with due dates.
- ~~`bt <n> untag @tag`~~ ✓ Done — replaced by `bt 1 clear @tag` (unified `clear` for all fields)
- ~~`bt edit <n>`~~ ✓ Done — `bt <n> edit` opens entry in `$EDITOR` (falls back to `nano`)

### Commands — Medium Value
- ~~`bt streak`~~ Done — 7-day grid, current streak count, 30-day completion rate.
- ~~`bt reflect`~~ / `bt recap` — removed with the AI layer. For retrospectives, use `bt m` (per-day replay across a month) or point your own AI agent at `entries/`.
- ~~`bt week`~~ Done — Weekly Log across all dimensions, Mon-Sun. `bt w last` for previous week, `bt w 14` for week 14.
- **Notes as reference layer** — full PKM features (pinned notes, linked references) remain future work. AI-driven recall is now handled by external agents via BYOAI.

### Commands — Nice to Have
- **Title lines for long-form notes** — when a note body is long (multi-line or beyond a threshold), auto-extract or prompt for a title line. Gives notes a scannable heading in list views instead of truncating the first line of a wall of text.
- `bt overdue` — shortcut for past-due tasks only. Quick "what am I behind on" accountability view.
- `bt move <n> due:friday` — update metadata fields without replacing body. Like `mod` but for due dates, tags, times.
- ~~`bt stats`~~ ✓ Done — personal analytics with week/month views, streaks, done/dropped ratio.
- ~~`bt find <keyword>`~~ ✓ Done — three tiers: FTS5 prefix match on full bodies (`find dent` → "dentist") plus exact tag match, then a substring fallback over bodies and tags (`find ntist` → "dentist") when the first tier is empty. Results show the matching line as a dim snippet when the hit isn't in the entry's first line. Query tokens are quoted before hitting FTS5, so user text is never parsed as FTS syntax. Flags: `-t` (tasks), `-n` (notes), `-j` (journals), `-c` (calendar). No flag = search all types.
- ~~`bt export`~~ ✓ Done — exports entries as `bullet-terminal-markdown-YYYY-MM-DD.zip` with README. `-o <path>` for custom output. Counter suffix for same-day duplicates.

### Onboarding
- ~~**Guided tour — first-run onboarding**~~ ✓ Done — interactive REPL teaches core concepts on first `bt` run. 11 phases: capture → see → organize → act → plan.
- ~~**Redesign Daily Plan (`dp`)**~~ ✓ Done — simplified to single-phase task picker. Yesterday's unresolved highlighted at top, @thisweek/backlog pool below.

### Infrastructure
- **`bt this` — capture Claude Code chat into bt** — add a Claude Code hook or slash command so `bt this` saves the current conversation's markdown export as a bt note. Turns ephemeral AI chats into searchable, tagged entries in the bt system.
- **AI agent as mobile interface** — with BYOAI, external agents (Claude Desktop + filesystem MCP, Claude Code, mobile Claude) can both read and write `.md` files under `~/bullet-terminal/entries/`. bt's reconciliation picks up their writes. No mobile app, no REST API, no cloud sync needed — the AI agent is the frontend, bt is the storage + CLI.
- ~~SQLite index for structured queries~~ In progress — see `docs/superpowers/specs/2026-04-02-sqlite-index-design.md`. Metadata + FTS5 + vectors in one DB, write-through sync, auto-rebuild.

### Design Guardrail
- **Stay BuJo, not Notion.** As bt grows into a PKM, resist becoming a general-purpose notes app. Every feature should serve the BuJo methodology — signifiers, rapid logging, rituals, migration. The CLI constraint and opinionated simplicity are features, not limitations. If a feature requires explaining, it probably doesn't belong.

## Full Design Doc

`/Users/khalidal-ghamdi/Documents/Obsidian/Home/dwn - AI Life Management System Design.md`
