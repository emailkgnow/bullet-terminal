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

Custom Click group with 7-layer routing in `resolve_command()`:

1. **Named commands** — standard Click (ls, dyts, plan, tasks, notes, collections, etc.)
2. **Letter shortcut** — `l` → linelog
3. **Signifiers** — `t`, `n`, `j`, `c` (or full words: `task`, `note`, `journal`, `cal`)
   - With text → **capture** (`bute t call dentist`)
   - With text + `+collection` → **collection capture** (`bute t fix faucet +home-reno`)
   - Without text → **view** (`bute t` → show Task Log)
   - With only `@tag` → **filtered view** (`bute t @backend`)
4. **Tag filter** — `@tagname` → cross-dimension filter
5. **Collection** — `+name` → view, `+name analyze` → AI analyze, `+name execute` → AI execute
6. **Number-action** — `1 done`, `2 3 drop` → action dispatch
7. **Fallback** — Click error

### Data Model

- **Entry types**: task (`.`), note (`-`), journal (`=`), calendar (`o`)
- **Task statuses**: `active`, `done`, `dropped` (no `migrated` — removed by design)
- **IDs**: ULID (time-sortable, 26 chars)
- **Storage**: one `.md` file per entry at `~/bute/entries/YYYY-MM/<ULID>.md`
- **Tags**: `@tag` syntax in CLI, stored as plain strings in YAML frontmatter
- **Collections**: `+collection` syntax in CLI, stored as sectioned `.md` files at `~/bute/collections/`

### Data Flow

```
User input → DwnGroup.resolve_command() → capture.py
  → parser.py:parse_capture_tokens() — extracts signifier, body, key:value, @tags, +collection
  → If +collection: append to collection_storage → confirm "Added to +name"
  → Else: models.py:Entry.create() → storage.py:save_entry() → embed → confirm_capture()
```

### State Management

`.state.json` stores the last displayed list as `{"view": "ls", "entries": ["ulid1", "ulid2"]}`. Display numbers (1, 2, 3) map to ULIDs. Numbers re-scope on each new view.

### Key Modules

| Module | Role |
|--------|------|
| `cli.py` | DwnGroup dispatch + command registration + help text |
| `parser.py` | Signifier/metadata/@tag parsing, date/time resolution |
| `models.py` | Entry dataclass, EntryType/TaskStatus enums, SIGNIFIER_MAP |
| `storage.py` | Markdown file I/O, query by date/filter, handles legacy `migrated` status |
| `display.py` | Rich rendering: `display_entry_list`, `display_entry_list_grouped`, confirmations |
| `ritual_ops.py` | Pure functions for rituals (daily log, yesterday unresolved, schedule, active tasks, dump) |
| `state.py` | View-to-action bridge, DYTS completion tracking |
| `ai/llm.py` | Provider-agnostic OpenAI client, macOS Keychain API key resolution |
| `ai/vectors.py` | sqlite-vec wrapper (upsert, search, delete) |
| `ai/embeddings.py` | fastembed wrapper, lazy model loading |
| `ai/prompts.py` | Prompt templates for AI features |
| `commands/collections.py` | Collection view, analyze, execute, list commands |
| `collection_storage.py` | Collection file I/O, sectioned Markdown (Input/Analysis/Tasks) |

### AI Architecture

Three independent capability tiers — each degrades gracefully:
1. **Embeddings** (local) — fastembed ONNX model, no API key needed
2. **Vector DB** (local) — sqlite-vec, rebuildable from .md files via `bute rebuild`
3. **LLM** (remote) — OpenAI-compatible API, provider-agnostic. API key via config or macOS Keychain

AI is used for: `topic`, `review`, `nudges`, collection processing (`analyze`, `execute`). Core capture/view/action loop works without AI.

## CLI Grammar (Current)

**Capture** — signifier + text:
```
bute t call dentist due:friday @backend    # single letter
bute task call dentist due:friday @backend # full word
bute t! fix prod bug                       # important modifier
bute c dentist t:1430 d:0330               # calendar: Mar 30 at 2:30 PM
bute c meeting t:0900                      # calendar: today at 9:00 AM
bute c conference d:0415                   # calendar: Apr 15, all day
```

**Calendar metadata:**
- `t:HHMM` — time in 24h (4 digits). No `t:` = all day.
- `d:MMDD` — date (4 digits). No `d:` = today.
- `due:` — deadline for tasks (supports: `tomorrow`, `friday`, `mar29`, `0329`)

**Views** — signifier alone, or named commands:
```
bute t              # Task Log (active tasks)
bute t @backend     # filtered by tag
bute t -a           # all including done/dropped
bute n / j / c      # notes / journals / calendar (grouped by date)
bute l              # line log (monthly overview)
bute ls             # today's daily log
bute @tagname       # cross-dimension tag filter
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
bute undo           # undo last action
bute 3 undo         # undo last action on entry 3
```

**Collections** — ideas to action:
```
bute t fix faucet +home-reno        # add task to collection
bute n kitchen is 12x15 +home-reno  # add note to collection
bute +home-reno                     # view collection (full trail)
bute +home-reno analyze             # AI clusters and organizes
bute +home-reno execute             # AI generates sequenced tasks
bute collections                    # list all collections
```

**Rituals**:
```
bute                # entry point — DYTS if not done today, else daily log
bute dyts           # morning ritual (Dump, Yesterday, Tasks, Schedule)
bute plan           # dump tasks + select for the week
bute recap          # end-of-day summary (-q to skip AI)
bute habit <name>   # track habits
```

## Design Decisions

- **No migrate** — removed. Tasks stay `active` until `done` or `dropped`. DYTS Y phase handles yesterday's unfinished items.
- **Tags use `@`, collections use `+`** — `@backend` = flat label, `+home-reno` = collection funnel. Tags organize, collections process.
- **Collections replace FFFF** — `+collection` capture syntax, two AI stages (analyze, execute) instead of four (find/form/focus/finish). Collections are super notes (analyzed) or super tasks (executed). Items live only in the collection until Execute generates real entries.
- **Linelog is derived** — no stored file, computed from journal + calendar entries. No AI compression.
- **`bute` with no args** = DYTS entry point. If DYTS done today, shows daily log.
- **Daily log (`bute ls`)** shows only: `@today` tasks, today's calendar events, all today's journals and notes. Other tasks stay in Task Log (`bute t`).
- **`bute plan`** includes task dump phase — add tasks before selecting for the week.
- **Display**: tasks = flat list, notes/journals/calendar = grouped by date (using `scheduled_date` for calendar events).
- **Calendar sorting**: timed events first (chronologically), then untimed, then other entry types.
- **Time format**: stored as `HH:MM` (24h), displayed as `h:MM AM/PM`. Legacy formats (`3pm`, `3:30pm`) normalized on read.
- **API key**: resolved from config value, `keychain:<service>`, or auto-lookup in macOS Keychain.

## Backlog

### Commands — High Value
- ~~`bt due`~~ ✓ Done — overdue + due today + due this week. `bt due all` for all tasks with due dates.
- ~~`bt <n> untag @tag`~~ ✓ Done — `bt 1 untag @tag` or `bt 1 untag tag`
- ~~`bt edit <n>`~~ ✓ Done — `bt <n> edit` opens entry in `$EDITOR` (falls back to `nano`)

### Commands — Medium Value
- ~~`bt streak`~~ Done — 7-day grid, current streak count, 30-day completion rate.
- ~~`bt reflect`~~ Done as `bt recap` — end-of-day summary with structured display + AI coaching narrative.
- ~~`bt week`~~ Done — weekly spread across all dimensions, Mon-Sun. `bt week last` for previous week.
- ~~**Notes as reference layer**~~ Partially addressed by collections — `+collection` with notes creates "super notes" (analyzed collections). Full PKM features (pinned notes, AI recall, linked references) remain future work.

### Commands — Nice to Have
- `bt overdue` — shortcut for past-due tasks only. Quick "what am I behind on" accountability view.
- `bt move <n> due:friday` — update metadata fields without replacing body. Like `mod` but for due dates, tags, times.
- `bt stats` — personal analytics: done/dropped ratio, busiest days, most-used tags, capture frequency. Data is all in the markdown files.
- ~~`bt find <keyword>`~~ ✓ Done — FTS5 body search + tag search, deduped. Flags: `-t` (tasks), `-n` (notes), `-j` (journals), `-c` (calendar). No flag = search all types.
- ~~`bt export`~~ ✓ Done — exports entries, collections, habits as `bullet-terminal-markdown-YYYY-MM-DD.zip` with README. `-o <path>` for custom output. Counter suffix for same-day duplicates.

### Infrastructure
- **AI agent as mobile interface** — bt's CLI grammar is already agent-friendly. Via Claude desktop/mobile + MCP or remote dispatch, natural language commands can route to bt on the local machine. No mobile app, no REST API, no cloud sync needed — the AI agent is the frontend.
- Add meaningful AI features
- ~~SQLite index for structured queries~~ In progress — see `docs/superpowers/specs/2026-04-02-sqlite-index-design.md`. Metadata + FTS5 + vectors in one DB, write-through sync, auto-rebuild.
- Display `extra_meta` (custom key:value pairs) — saved to YAML frontmatter and round-trips correctly, but invisible in capture confirmation and all list views

### Design Guardrail
- **Stay BuJo, not Notion.** As bt grows into a PKM, resist becoming a general-purpose notes app. Every feature should serve the BuJo methodology — signifiers, rapid logging, rituals, migration. The CLI constraint and opinionated simplicity are features, not limitations. If a feature requires explaining, it probably doesn't belong.

## Full Design Doc

`/Users/khalidal-ghamdi/Documents/Obsidian/Home/dwn - AI Life Management System Design.md`
