# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is bute?

bute (BuTe — Bullet Terminal) is a CLI life management system based on the Bullet Journal methodology. Single user, local data, plain Markdown files. The name mirrors BuJo (Bullet Journal) — same family, different medium.

## Development Commands

```bash
# Install all deps (dev + optional)
uv sync --extra embeddings --extra ai --extra dev

# Run tests
uv run pytest                         # all tests
uv run pytest tests/test_capture.py   # single module
uv run pytest -m "not slow"           # skip embedding tests
uv run pytest --cov=src/bute          # with coverage

# Install globally (for manual testing)
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall

# Build
uv build
```

## Architecture

### CLI Dispatch (cli.py — ButeGroup)

Custom Click group with 6-layer routing in `resolve_command()`:

1. **Named commands** — standard Click (dp, tasks, backlog, notes, tags, etc.)
2. **Letter shortcut** — `b` → backlog, `m` → monthly
3. **Signifiers** — `t`, `n`, `j`, `c` (or full words: `task`, `note`, `journal`, `calendar`)
   - With text → **capture** (`bute t call dentist`)
   - Without text → **view** (`bute t` → show Tasks / weekly focus)
   - With only `@tag` → **filtered view** (`bute t @backend`)
4. **Tag filter** — `@tagname` → cross-dimension filter (multi-tag: `@a @b -@c`)
5. **Number-action** — `1 done`, `2 3 drop` → action dispatch
6. **Fallback** — Click error

### Data Model

- **Entry types**: task (`.`), note (`-`), journal (`=`), calendar (`o`)
- **Task statuses**: `active`, `done`, `dropped` (no `migrated` — removed by design)
- **IDs**: ULID (time-sortable, 26 chars)
- **Storage**: one `.md` file per entry at `~/bullet-terminal/entries/{type}/YYYY-MM/<ULID>.md`
- **Tags**: `@tag` syntax in CLI, stored as plain strings in YAML frontmatter. Tags have a dual role: organizing entries (label) and processing groups via AI (analyze). Stage tracking in `tag_stages` SQLite table.

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
| `ritual_ops.py` | Pure functions for rituals (Focus Log, yesterday unresolved, schedule, active tasks, dump) |
| `state.py` | View-to-action bridge, DYTS completion tracking |
| `ai/llm.py` | Provider-agnostic OpenAI client, macOS Keychain API key resolution |
| `ai/vectors.py` | sqlite-vec wrapper (upsert, search, delete) |
| `ai/embeddings.py` | fastembed wrapper, lazy model loading |
| `ai/prompts.py` | Prompt templates for AI features |
| `commands/tags.py` | Tag processing: analyze (AI clusters entries) |

### AI Architecture

Three independent capability tiers — each degrades gracefully:
1. **Embeddings** (local) — fastembed ONNX model, no API key needed
2. **Vector DB** (local) — sqlite-vec, rebuildable from .md files via `bute rebuild`
3. **LLM** (remote) — OpenAI-compatible API, provider-agnostic. API key via config or macOS Keychain

AI is used for: `topic`, `recap [period]`, `nudges`, tag processing (`bt analyze @tag`), `chat` (interactive sessions with entry suggestions). Core capture/view/action loop works without AI.

## CLI Grammar (Current)

**Capture** — signifier + text:
```
bute t call dentist due:friday @backend    # single letter
bute task call dentist due:friday @backend # full word
bute t! fix prod bug                       # important modifier
bute c dentist t:14.30 d:3.30              # calendar: Mar 30 at 2:30 PM
bute c meeting t:9                         # calendar: today at 9:00 AM
bute c conference d:4.15                   # calendar: Apr 15, all day
bute n check OAuth docs d:4.10             # note: resurfaces in Focus Log Apr 10
```

**Date/time metadata:**
- `d:` — date. Formats: `d:4.7` (MM.DD), `d:today`, `d:tomorrow`, `d:friday`, `d:mar15`. Legacy `d:0407` still works.
- `t:` — time in 24h. Formats: `t:9` (9:00), `t:14.15` (2:15 PM). Legacy `t:1430` still works.
- `due:` — deadline for tasks (supports same formats as `d:`)

**Views** — signifier alone, or named commands:
```
bute t              # Tasks — this week's focus (@thisweek)
bute t @backend     # filtered by tag
bute t -a           # all including done/dropped
bute b              # Task Backlog — all active tasks
bute n / j / c      # notes / journals / calendar (grouped by date)
bute d              # daily log (all entries for today, retrospective)
bute d yesterday    # yesterday's daily log
bute w              # weekly log (all entries, Mon-Sun)
bute w last         # last week's log
bute w 14           # week 14 of this year (ISO week number)
bute m              # monthly log (all entries for the month)
bute m jan          # January's log (full or abbreviated name)
bute m 2026-03      # March 2026
bute m 2026         # all months of 2026
bute                # Focus Log (or DYTS if not done today)
bute @tagname       # cross-dimension tag filter
bute @bt @ai        # entries with both tags (AND)
bute @bt -@done     # entries with @bt but not @done
bute -@habit        # all entries excluding @habit
bute !              # all important entries
bute t!             # important tasks (also: n!, j!, c!)
bute find <keyword> # keyword search in body + tags (-t -n -j -c to filter)
bute like <input>   # semantic similarity (bt like 3, bt like productivity)
```

**Actions** — number + command:
```
bute 1 done         # mark complete
bute 2 3 drop       # consciously delete
bute 4 delete       # permanently remove from disk
bute 5 !            # toggle important
bute 6 @tag         # add tag
bute 6 untag @tag   # remove tag
bute 7 edit         # open in $EDITOR
bute 3 later        # defer — remove from today's log
bute 3 chat         # AI chat session anchored to entry
bute undo           # undo last action
bute 3 undo         # undo last action on entry 3
```

**Chat sessions** — `bt <n> chat` starts an AI conversation anchored to an entry. During the chat, use `/bt t`, `/bt @tag`, etc. to pull entries into context. At exit (`/done`), the AI reviews the conversation and suggests entries to create (tasks, notes, journals, calendar events). You confirm with `y`/`n`/`p` (pick). Chat-created tasks auto-tag `@thisweek`, notes/journals auto-tag `@today`.

**Goals** — orient tasks toward outcomes:
```
bute goals                          # show goals with task progress
```
Goals are notes tagged `@goal`. Other tags on the note connect tasks to the goal. `bute goals` shows each goal with active/done task counts. System tags (`@goal`, `@today`, `@thisweek`) are filtered out when computing connected tags.

**Tag Processing** — ideas to clarity:
```
bute analyze @home-reno             # AI clusters and organizes tagged entries
bute analyze @bt @ai -@done         # analyze filtered intersection
bute map @backend                   # mind map of tag analysis
bute tags                           # list all tags with stage and count
```

**Rituals**:
```
bute                # entry point — DYTS if not done today, else Focus Log
bute dp             # morning ritual — pick today's tasks
bute wp             # weekly plan — select tasks for the week
bute recap week     # AI analysis of a period (day, week, month, year)
bute habit <name>   # track habits
bute streak         # habit streaks and 30-day stats
```

**System**:
```
bute export         # zip backup of all data to cwd (-o path)
bute rebuild        # rebuild search index from .md files
bute init           # first-run setup (pick AI provider)
```

## Design Decisions

- **No migrate** — removed. Tasks stay `active` until `done` or `dropped`. DYTS Y phase handles yesterday's unfinished items.
- **Tags have a dual role** — `@tag` as label (organizes entries) and `@tag` as thinking tool (`analyze` clusters the group via AI). The `+collection` syntax was removed — tags absorbed collections. Stage tracking (raw → analyzed) lives in the `tag_stages` SQLite table.
- **Logs are derived** — no stored files. Focus Log (`bt`), daily log (`bt d`), weekly log (`bt w`), monthly log (`bt m`) all query entries for their period. Tasks show status (done = strikethrough, dropped = strikethrough + label).
- **`bute` with no args** = Daily Plan entry point. If daily plan done today, shows Focus Log.
- **Focus Log (`bt`)** — what matters today: `@today` tasks, tasks due today or overdue, today's calendar events, all today's journals and notes. Any entry with `d:` (scheduled_date) matching today also surfaces. Other tasks stay in Backlog (`bute b`) or Tasks (`bute t`). Curated and active-only — distinct from Daily Log (`bt d`) which shows everything retrospectively.
- **Task views**: `bt t` (Tasks) shows `@thisweek` focus tasks. `bt b` (Backlog) shows all active tasks. The flow is: backlog → weekly plan → tasks → Focus Log.
- **`bute wp`** includes task dump phase — add tasks before selecting for the week.
- **Display**: tasks = flat list, notes/journals/calendar = grouped by date (using `scheduled_date` for calendar events).
- **Scheduling is universal** — `d:` (scheduled_date) works on all entry types. Tasks: deadline. Calendar: event date. Notes/journals: resurface date. All surface in the Focus Log on the target date. Only tasks can be overdue (past-due tasks linger; missed note/journal reminders don't).
- **Calendar sorting**: timed events first (chronologically), then untimed, then other entry types.
- **Time format**: stored as `HH:MM` (24h), displayed as `h:MM AM/PM`. Preferred input: `t:9`, `t:14.30`. Legacy formats (`t:1430`, `3pm`) still accepted.
- **Date format**: preferred input: `d:4.7`, `d:mar15`, `d:tomorrow`, `d:friday`. Legacy `d:0407` still accepted.
- **API key**: resolved from config value, `keychain:<service>`, or auto-lookup in macOS Keychain.

## Backlog

### Commands — High Value
- ~~`bt due`~~ ✓ Done — overdue + due today + next 7 days (rolling). `bt due all` for all tasks with due dates.
- ~~`bt <n> untag @tag`~~ ✓ Done — `bt 1 untag @tag` or `bt 1 untag tag`
- ~~`bt edit <n>`~~ ✓ Done — `bt <n> edit` opens entry in `$EDITOR` (falls back to `nano`)

### Commands — Medium Value
- ~~`bt streak`~~ Done — 7-day grid, current streak count, 30-day completion rate.
- ~~`bt reflect`~~ Done as `bt recap` — end-of-day summary. `bt recap [period]` runs AI analyze pipeline for day/week/month/year.
- ~~`bt week`~~ Done — Weekly Log across all dimensions, Mon-Sun. `bt w last` for previous week, `bt w 14` for week 14.
- ~~**Notes as reference layer**~~ Partially addressed by tag processing — `@tag analyze` clusters tagged notes. Full PKM features (pinned notes, AI recall, linked references) remain future work.

### Commands — Nice to Have
- **Title lines for long-form notes** — when a note body is long (multi-line or beyond a threshold), auto-extract or prompt for a title line. Gives notes a scannable heading in list views instead of truncating the first line of a wall of text.
- `bt overdue` — shortcut for past-due tasks only. Quick "what am I behind on" accountability view.
- `bt move <n> due:friday` — update metadata fields without replacing body. Like `mod` but for due dates, tags, times.
- `bt stats` — personal analytics: done/dropped ratio, busiest days, most-used tags, capture frequency. Data is all in the markdown files.
- ~~`bt find <keyword>`~~ ✓ Done — FTS5 body search + tag search, deduped. Flags: `-t` (tasks), `-n` (notes), `-j` (journals), `-c` (calendar). No flag = search all types.
- ~~`bt export`~~ ✓ Done — exports entries, collections, habits as `bullet-terminal-markdown-YYYY-MM-DD.zip` with README. `-o <path>` for custom output. Counter suffix for same-day duplicates.

### Tag Processing
- **Mindmap output for `bt @tag analyze`** — after AI clusters and organizes tagged entries, render or export a mindmap visualization of the themes and their items. Could be ASCII art in the terminal, or generate a Mermaid/Markmap diagram that opens in a browser. Gives the user a spatial view of how their ideas relate.

### Onboarding
- ~~**Guided tour — first-run onboarding**~~ ✓ Done — interactive REPL teaches core concepts on first `bt` run. 11 phases: capture → see → organize → act → plan.
- **AI tour** — triggered after `bt init` configures an AI provider. Teaches search, chat, recap, nudges, analyze, tag-notes using real entries.
- ~~**Redesign Daily Plan (`dp`)**~~ ✓ Done — simplified to single-phase task picker. Yesterday's unresolved highlighted at top, @thisweek/backlog pool below.

### Infrastructure
- **`bt this` — capture Claude Code chat into bt** — add a Claude Code hook or slash command so `bt this` saves the current conversation's markdown export as a bt note. Turns ephemeral AI chats into searchable, tagged entries in the bt system.
- **AI agent as mobile interface** — bt's CLI grammar is already agent-friendly. Via Claude desktop/mobile + MCP or remote dispatch, natural language commands can route to bt on the local machine. No mobile app, no REST API, no cloud sync needed — the AI agent is the frontend.
- Add meaningful AI features
- ~~SQLite index for structured queries~~ In progress — see `docs/superpowers/specs/2026-04-02-sqlite-index-design.md`. Metadata + FTS5 + vectors in one DB, write-through sync, auto-rebuild.
- Display `extra_meta` (custom key:value pairs) — saved to YAML frontmatter and round-trips correctly, but invisible in capture confirmation and all list views

### Design Guardrail
- **Stay BuJo, not Notion.** As bt grows into a PKM, resist becoming a general-purpose notes app. Every feature should serve the BuJo methodology — signifiers, rapid logging, rituals, migration. The CLI constraint and opinionated simplicity are features, not limitations. If a feature requires explaining, it probably doesn't belong.

## Full Design Doc

`/Users/khalidal-ghamdi/Documents/Obsidian/Home/dwn - AI Life Management System Design.md`
