# bt (Bullet Terminal)

A CLI life management system based on the [Bullet Journal](https://bulletjournal.com/) methodology. Single user, local data, plain Markdown files. No cloud, no accounts, no network.

bt stays opinionated and lean. The goal is to capture fast, plan each morning, and keep the mental loop closed — in a terminal.

---

## Install

```bash
uv tool install --from . --with fastembed --with sqlite-vec bute
```

- `fastembed` + `sqlite-vec` are optional — they enable `bt like` (local semantic search). Skip them if you only want the core BuJo loop.
- Run `bt init` once to create `~/.config/bute/config.toml` and `~/bullet-terminal/`.

---

## A two-minute tour

```bash
bt t call dentist due:friday @home   # capture a task
bt n OAuth2 tokens expire in 30 days # capture a note
bt j rough morning, couldn't focus   # capture a journal
bt c standup t:9                     # capture a calendar event

bt                # Focus Log — what matters today
bt t              # this week's tasks
bt b              # backlog (all active tasks)
bt dp             # daily plan ritual (pick today's tasks)
bt wp             # weekly plan ritual (pick this week's)
bt m              # monthly log — retrospective, one row per day
bt @home          # cross-dimension filter
bt find OAuth     # keyword search
bt like 3         # semantic: entries similar to entry #3

bt 1 done         # mark entry #1 complete
bt 2 3 drop       # drop entries #2 and #3
bt 4 @urgent      # tag entry #4
bt 5 edit         # open in $EDITOR
```

Full command reference: `bt -h`. Quick tour in-app: `bt start`.

---

## Data model — the source of truth

**Everything bt knows lives in plain Markdown files.** The SQLite index at `~/bullet-terminal/.index/bute.db` is a derived cache — it can be rebuilt from the `.md` files at any time with `bt rebuild`, and bt auto-reconciles it on each read (see [Bring Your Own AI](#bring-your-own-ai) below).

### Folder layout

```
~/bullet-terminal/
├── entries/
│   ├── task/YYYY-MM/<ULID>.md
│   ├── note/YYYY-MM/<ULID>.md
│   ├── journal/YYYY-MM/<ULID>.md
│   └── calendar/YYYY-MM/<ULID>.md
└── .index/
    └── bute.db         # SQLite index (metadata + FTS5 + vectors) — regenerable
```

Each entry is one file. The filename (without `.md`) is the entry's ULID, which must match the `id` frontmatter key. The `YYYY-MM` folder must match the `created` timestamp's month in the entry's local time.

### Frontmatter schema

All metadata lives in YAML frontmatter. Body text is the rest of the file.

| Key | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | 26-char ULID, matches filename stem |
| `type` | string | yes | `task` \| `note` \| `journal` \| `calendar` |
| `created` | ISO 8601 datetime | yes | e.g. `'2026-04-17T14:30:00+03:00'` |
| `status` | string | tasks only | `active` \| `done` \| `dropped` |
| `important` | bool | no | `true` to mark as `!` |
| `due` | ISO date | no | `'2026-04-20'` — tasks only, surfaces in Focus Log when overdue/today |
| `date` | ISO date | no | scheduled date; entry surfaces in Focus Log on that day |
| `time` | string | no | `HH:MM` 24h, for timed calendar events |
| `repeat` | string | no | `daily` \| `weekly` \| `monthly` |
| `focus_date` | ISO date | no | set by `bt dp`; day this task is pulled into Focus Log |
| `week_date` | ISO date | no | Monday of the week this task is in focus for |
| `completed_date` | ISO date | no | when a task became `done` or `dropped` |
| `tags` | list[string] | no | e.g. `['home', 'urgent']` — no `@` prefix in YAML |
| `events` | list[dict] | no | lifecycle event log; see below |
| `completions` | list[ISO date] | no | for repeating tasks, dates when completed |

Any other frontmatter key is preserved as `extra_meta` — round-trips through reads/writes but doesn't affect behavior.

### Example: a minimal task

```markdown
---
id: 01KPDYMXHTDZEWTY0GE0QYBHAA
type: task
created: '2026-04-17T09:00:00+03:00'
status: active
tags:
- home
---

fix the leaky faucet
```

### Example: a scheduled calendar event with time

```markdown
---
id: 01KPDYP0123456789ABCDEFGHJ
type: calendar
created: '2026-04-17T09:00:00+03:00'
date: '2026-04-20'
time: '14:30'
---

dentist appointment
```

### Body format

First line is the display title. Subsequent lines are long-form content. In list views, long bodies are truncated to the first line with a `>` suffix.

### Task statuses

Only three: `active`, `done`, `dropped`. There is no `migrated` state — tasks stay `active` until completed or dropped. Migration is implicit: repeated appearance across days in `bt m` *is* the migration signal.

### Events (optional, but bt appends them)

bt's own mutations (capture, dp, wp, done, drop, later, backlog, schedule, mod, undo) append to an `events` list in frontmatter. Each event has a `date` (ISO) and `action` (`captured`, `focused`, `unfocused`, `scheduled`, `unscheduled`, `week_planned`, `done`, `dropped`, `undropped`, `modified`, `due_set`, `due_cleared`). `bt m` replays events to render a daily retrospective.

External writers can omit `events`. When an entry has no stored events, bt synthesizes them at read time from `created`, `scheduled_date`, `focus_date`, and `completed_date`.

---

## Bring Your Own AI

bt has no built-in LLM. If you want AI over your entries, point your own agent (Claude Desktop with filesystem MCP, Claude Code, Gemini CLI, a custom script, etc.) at `~/bullet-terminal/entries/`. Read the .md files directly; write new .md files directly. bt will pick them up.

### The contract

1. **Filename = ULID + `.md`.** Use a library to generate a ULID (time-sortable, 26 chars). `python-ulid` in Python; most languages have one.
2. **Folder must match type and month.** A task created 2026-04-17 goes in `entries/task/2026-04/`.
3. **Frontmatter must be valid YAML** with the keys documented above. At minimum: `id`, `type`, `created`. Tasks should set `status: active`.
4. **Body is free-form Markdown.** First line is the title shown in list views.

### How reconciliation works

The first read operation per bt process (`bt`, `bt t`, `bt m`, `bt find`, `bt like`, etc.) compares the set of `.md` files under `entries/` against the SQLite index's `entry_id` column:

- **Files on disk not in the index** → `load_entry()` + `upsert` into the index and FTS5.
- **IDs in the index without a file** → delete from index.
- On subsequent reads in the same process, reconciliation is a no-op (latched per process).

`bt like` additionally runs the embedding step for new entries, so semantic search sees them without manual rebuild.

Edits to an existing file (same ID, new body) are not yet auto-detected. Run `bt rebuild` after external edits until that's handled. Capture/delete flows are fully auto-reconciled.

### Minimal example (any language with YAML + ULID)

```python
from ulid import ULID
from datetime import datetime, timezone
from pathlib import Path
import yaml

entry_id = str(ULID())
now = datetime.now(timezone.utc).astimezone()
frontmatter = {
    "id": entry_id,
    "type": "task",
    "created": now.isoformat(),
    "status": "active",
    "tags": ["agent-added"],
}
body = "review the quarterly metrics"

month = now.strftime("%Y-%m")
path = Path.home() / "bullet-terminal" / "entries" / "task" / month / f"{entry_id}.md"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(f"---\n{yaml.safe_dump(frontmatter)}---\n\n{body}\n")
```

Run `bt` after, and the task appears in Focus Log immediately — no rebuild needed.

---

## Commands

Full help: `bt -h` · Quick start tour: `bt start`.

| Command | What it does |
|---|---|
| `bt t <text>` | capture a task (also `n`, `j`, `c` for note/journal/calendar) |
| `bt` | Focus Log — today's focused tasks, due today, today's events/notes/journals |
| `bt t` / `bt b` | weekly Tasks / full Backlog |
| `bt m` / `bt m jan` / `bt m 2026` | Monthly Log (event-driven daily retrospective) |
| `bt @tag` | filter across all types; `@a @b` = AND, `-@c` = NOT |
| `bt find <q>` | keyword + tag search (FTS5) |
| `bt like <q>` | semantic search (local embeddings, no API key) |
| `bt <n> done` | mark entry #n done (also `drop`, `delete`, `!`, `@tag`, `edit`, `later`, `focus`) |
| `bt <n> clear <field>` | clear tag, due, date, time, repeat, or `!` |
| `bt <n> mod <text>` | replace entry body |
| `bt dp` / `bt wp` | daily / weekly planning rituals |
| `bt due` / `bt overdue` | deadline views |
| `bt goals` | goals (notes tagged `@goal`) with connected task progress |
| `bt streak` / `bt habit <name>` | habit tracking |
| `bt stats` | personal analytics (week/month/streaks) |
| `bt export` | zip backup of all .md files to cwd |
| `bt rebuild` | rebuild SQLite + FTS + vector index from .md files |
| `bt init` | (re)create config + data dirs |

---

## Architecture (short version)

- **Source of truth**: `.md` files. Everything else is derived.
- **Index**: SQLite at `.index/bute.db` — metadata table, FTS5 virtual table, `vec_entries` virtual table (sqlite-vec). Auto-rebuilt on first run; auto-reconciled on each read.
- **Embeddings**: local via fastembed (ONNX). No API keys, no network.
- **State**: `.state.json` at config dir remembers the last displayed list so `bt 1 done` knows which entry "#1" maps to.

Core modules: `cli.py` dispatches, `parser.py` tokenizes capture input, `models.py` holds `Entry`, `storage.py` reads/writes .md, `db.py` manages the SQLite index and reconciliation, `events.py` owns the event log, `display.py` renders Rich output, `commands/` hosts each subcommand.

---

## Design principles

- **Stay BuJo, not Notion.** Every feature serves rapid logging, signifiers, rituals. If it needs explaining, it probably doesn't belong.
- **Plain-text first.** The .md files work without bt. bt works without any service.
- **No AI inside.** AI belongs at the edge — you bring your own agent, point it at the folder.
- **Prefer removal over sprawl.** When features overlap, cut one.
- **Lean CLI grammar.** Number + action beats menus; signifier + text beats modals.

See `CLAUDE.md` for developer guidance and `docs/` for design notes and historical plans.
