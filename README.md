# bt (Bullet Terminal)

A CLI life management system based on the [Bullet Journal](https://bulletjournal.com/) methodology. Single user, local data, plain Markdown files. No cloud, no accounts, no network.

bt stays opinionated and lean. The goal is to capture fast, plan each morning, and keep the mental loop closed — in a terminal. The name mirrors BuJo (Bullet Journal): same family, different medium.

---

## Install

```bash
uv tool install 'bullet-terminal @ git+https://github.com/emailkgnow/bullet-terminal'
```

- Run `bt init` once to create `~/.config/bt/config.toml` and `~/bullet-terminal/`.
- Tab completion for `@tags` and command names: run `bt completion` and add the printed line to `~/.zshrc`.

---

## A two-minute tour

```bash
bt t call dentist due:friday @home   # capture a task
bt n OAuth2 tokens expire in 30 days # capture a note
bt j rough morning, couldn't focus   # capture a journal
bt c standup time:9                  # capture a calendar event

bt                # Focus Log — what matters today
bt t              # today's tasks
bt t -w           # this week's tasks
bt t -b           # backlog (all active tasks)
bt t -a           # every task, any status, grouped by date
bt dp             # daily plan ritual (pick today's tasks)
bt wp             # weekly plan ritual (pick this week's)
bt @home          # cross-dimension filter
bt find OAuth     # keyword search (partial words match: bt find auth)

bt 1 done         # mark entry #1 complete
bt 2 3 drop       # drop entries #2 and #3
bt 1-4 done       # range — mark entries 1, 2, 3, 4 complete
bt 1-3 7 done     # mix range + bare numbers
bt 4 @urgent      # tag entry #4
bt 5              # read entry #5 — e edits it in $EDITOR, q quits
```

Full command reference: `bt -h`. First-run onboarding triggers automatically.

---

## Data model — the source of truth

**Everything bt knows lives in plain Markdown files.** The SQLite index at `~/bullet-terminal/.index/bt.db` is a derived cache — it can be rebuilt from the `.md` files at any time with `bt rebuild`, and bt auto-reconciles it on each read (see [Bring Your Own AI](#bring-your-own-ai) below).

### Folder layout

```
~/bullet-terminal/
├── entries/
│   ├── task/YYYY-MM/<ULID>.md
│   ├── note/YYYY-MM/<ULID>.md
│   ├── journal/YYYY-MM/<ULID>.md
│   └── calendar/YYYY-MM/<ULID>.md
├── .trash/
│   └── <ULID>.md       # deleted entries (bt <n> delete) — flat, restorable with bt trash → bt <n> restore
├── .index/
│   └── bt.db           # SQLite index (metadata + FTS5) — regenerable
└── backups/
    └── bt-YYYY-MM-DD.zip   # daily auto-backup, pruned after 30 days — regenerable
```

Each entry is one file. The filename (without `.md`) is the entry's ULID, which must match the `id` frontmatter key. The `YYYY-MM` folder must match the `created` timestamp's month in the entry's local time.

External agents should ignore `.trash/` and `backups/`. Both are outside `entries/`, so reconciliation never indexes them. To delete an entry the bt way, move its file into `.trash/` rather than unlinking it.

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
| `repeat` | string | no | `daily` \| `weekly` \| `monthly` \| `yearly` — any other value is rejected |
| `focus_date` | ISO date | no | set by `bt dp`; day this task is pulled into Focus Log |
| `week_date` | ISO date | no | Monday of the week this task is in focus for |
| `completed_date` | ISO date | no | when a task became `done` or `dropped` |
| `tags` | list[string] | no | e.g. `['home', 'urgent']` — no `@` prefix in YAML, always lowercase |
| `completions` | list[ISO date] | no | for repeating tasks, dates when completed |

Any other frontmatter key is preserved as `extra_meta` — round-trips through reads/writes but doesn't affect behavior. bt shows these keys in the meta column of list views.

**Private keys.** A key starting with `_` is bookkeeping that belongs to whoever wrote it — a sync script's remote event id, an agent's checksum. bt preserves it on every read and write and still emits it under `extra` in `--json`, but never renders it in `bt c`, `bt t`, `bt <n>`, or any other human-facing view. Use it for anything you need to find your own entries again but the user should never have to read.

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

Only three: `active`, `done`, `dropped`. There is no `migrated` state — tasks stay `active` until completed or dropped. The daily plan (`bt dp`) resurfaces yesterday's unfinished tasks instead.

### No history log

bt keeps current state only. An `events` list from older versions is read without error and dropped on the next save — don't write one. For a retrospective, derive it from the date fields (`created`, `focus_date`, `scheduled_date`, `due`, `week_date`, `completed_date`, `completions`).

---

## Bring Your Own AI

bt has no built-in LLM. If you want AI over your entries, point your own agent (Claude Desktop with filesystem MCP, Claude Code, Gemini CLI, a custom script, etc.) at `~/bullet-terminal/entries/`. Read the .md files directly; write new .md files directly. bt will pick them up.

### The contract

1. **Filename = ULID + `.md`.** Use a library to generate a ULID (time-sortable, 26 chars). `python-ulid` in Python; most languages have one.
2. **Folder must match type and month.** A task created 2026-04-17 goes in `entries/task/2026-04/`.
3. **Frontmatter must be valid YAML** with the keys documented above. At minimum: `id`, `type`, `created`. Tasks should set `status: active`.
4. **Body is free-form Markdown.** First line is the title shown in list views.

To read what bt shows without parsing tables, append `--json` to any numbered entry view — the Focus Log, Tasks/Backlog/Notes/Journals/Calendar, tag filters, `due`, `tags`, and `find` (`bt --json`, `bt t -b --json`, `bt @home --json`, `bt find x --json`). It does not apply to `bt stats`/`bt streak` (their own reports), or to actions and captures (which still print Rich confirmations). The `n` field is the number you would pass to `bt <n> done`. Every view returns `{"view": ..., "entries": [...]}`; the one exception is `bt tags --json`, which returns a `tags` array of `{"tag", "count", "types"}` objects instead of `entries` (tags are not numbered); `types` maps each entry type with a non-zero count to that count, e.g. `{"task": 54, "note": 10}`.

### How reconciliation works

The first read operation per bt process (`bt`, `bt t`, `bt find`, etc.) compares the set of `.md` files under `entries/` against the SQLite index's `entry_id` column:

- **Files on disk not in the index** → `load_entry()` + `upsert` into the index and FTS5.
- **IDs in the index without a file** → delete from index.
- On subsequent reads in the same process, reconciliation is a no-op (latched per process).

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

## Capture metadata

Four keys, one spelling each — the word you type is the frontmatter key it writes.

| Key | Writes | Applies to | Accepted values |
|---|---|---|---|
| `due:` | `due` | tasks only — rejected on notes, journals, calendar | a date (below), or an `am`/`pm` time |
| `date:` | `date` | all types | a date (below) |
| `time:` | `time` | all types | `HH:MM`, optionally with `am`/`pm` |
| `repeat:` | `repeat` | tasks | `daily` \| `weekly` \| `monthly` \| `yearly` |

**Dates** — the hyphen is the only separator, and everything is case-insensitive:

| Form | Example | Means |
|---|---|---|
| relative word | `today`, `tomorrow` | today / tomorrow |
| weekday | `friday`, `fri` | the *next* Friday, never today |
| month + day | `jan-23` | the next 23 January |
| ISO tail | `01-23` | same thing, written as ISO without the year |
| full ISO | `2026-01-23` | exactly that date |

All but full ISO resolve **forward**: `01-23` typed in September means next
January, never the one just past. Use full ISO for a date in the past.

**Times** — `HH:MM`, read as 24-hour unless you add a suffix. Minutes are
always required, so there is exactly one way to write any given time:

```
time:09:00   → 09:00      time:14:30   → 14:30
time:9:00am  → 09:00      time:2:20pm  → 14:20
```

**`due:` with a time** — on capture, a `due:` value ending in `am`/`pm` means
*due today at that time*: `bt t take meds due:3:00pm` writes `due` = today and
`time` = `15:00` (an explicit `time:` wins). Same `HH:MM` rule, so `due:3pm` is
an error. On an existing entry, `bt <n> due:` takes a date only.

**`date:` means something slightly different for each type.** It always puts
the entry in the Focus Log on that day, and on that day only:

| Type | `date:` means | Before the day | After the day |
|---|---|---|---|
| task | the day you plan to work on it | waits in the Backlog | back to the Backlog if still open |
| calendar | the day of the event | hidden from the Focus Log | drops off |
| note | the day it resurfaces as a reminder | hidden from the Focus Log | drops off |
| journal | the day it resurfaces | hidden from the Focus Log | drops off |

`due:` versus `date:` on a task — `date:` is when it shows up for you to work
on; `due:` is when it must be finished. A task due today or earlier stays in the
Focus Log every day until it's done or dropped, and shows in `bt overdue`.
`bt t draft report date:monday due:friday` shows up Monday and, if still open,
comes back Friday and stays until finished.

```bash
bt t file taxes due:friday
bt c dentist date:12-25 time:14:30
bt t meditate repeat:daily
bt 1 date:tomorrow time:9:00     # set on an existing entry
bt 1 clear time                  # remove it
```

Reading is deliberately looser than typing. bt writes a quoted `'HH:MM'`, but
a file you or an agent writes by hand may use `3pm`, `14.30` or `1430` and
will still load — including an *unquoted* `time: 14:30`, which YAML turns into
the integer `870`. A time bt cannot read at all is dropped rather than raised,
so one bad field never hides the entry.

## Commands

Full help: `bt -h`.

| Command | What it does |
|---|---|
| `bt t <text>` | capture a task (also `n`, `j`, `c` for note/journal/calendar) |
| `bt` | Focus Log — today's focused tasks, due today, today's events/notes/journals |
| `bt t` | today's tasks |
| `bt t -w` / `bt t -b` | this week's active tasks / full Backlog |
| `bt @tag` | filter across all types, shown as a tree grouped by type; `@a @b` = AND, `-@c` = NOT (matching is case-insensitive) |
| `@@tag` | double duty tag at capture — keeps the word in the sentence *and* tags it: `bt j lunch with @@Elham` stores "lunch with Elham" tagged `elham` |
| `bt find <q>` | keyword + tag search over full note bodies; matches partial words (prefix via FTS5, then a substring fallback) and shows the matching line |
| `bt <view> --json` | numbered entry views as JSON (`bt`, `bt t`/`n`/`j`/`c`, `bt t -b`, `bt @tag`, `bt due`, `bt tags`, `bt find`) — same numbers as the table, so `bt 3 done` works from a script |
| `bt <n> done` | mark entry #n done (also `drop`, `delete`, `!`, `@tag`, `weeklog`, `focus`, `backlog`, `restore`) |
| `bt <n>` | read entry #n in a full-screen viewer — `e` edits in `$EDITOR`, `n`/`p` step through several (`bt 1 3`), `q` quits; piped, it prints instead |
| `bt <n> clear <field>` | clear tag, due, date, time, repeat, or `!` |
| `bt <n> mod <text>` | replace entry body |
| `bt dp` / `bt wp` | daily / weekly planning rituals |
| `bt due` / `bt overdue` | deadline views |
| `bt trash` / `bt trash empty` | list trashed entries (restore with `bt <n> restore`) / purge them |
| `bt streak` / `bt habit <name>` | habit tracking |
| `bt stats` | personal analytics (week/month/streaks) |
| `bt export` | zip backup of all .md files to cwd |
| `bt rebuild` | rebuild SQLite + FTS index from .md files |
| `bt init` | (re)create config + data dirs |

---

## Architecture (short version)

- **Source of truth**: `.md` files. Everything else is derived.
- **Index**: SQLite at `.index/bt.db` — metadata table and FTS5 virtual table. Auto-rebuilt on first run; auto-reconciled on each read.
- **State**: `.state.json` at config dir remembers the last displayed list so `bt 1 done` knows which entry "#1" maps to.

Core modules: `cli.py` dispatches, `parser.py` tokenizes capture input, `models.py` holds `Entry`, `storage.py` reads/writes .md, `db.py` manages the SQLite index and reconciliation, `display.py` renders Rich output, `commands/` hosts each subcommand.

---

## Design principles

- **Stay BuJo, not Notion.** Every feature serves rapid logging, signifiers, rituals. If it needs explaining, it probably doesn't belong.
- **Plain-text first.** The .md files work without bt. bt works without any service.
- **No AI inside.** AI belongs at the edge — you bring your own agent, point it at the folder.
- **Prefer removal over sprawl.** When features overlap, cut one.
- **Lean CLI grammar.** Number + action beats menus; signifier + text beats modals.

See `CLAUDE.md` for developer guidance and `docs/` for design notes and historical plans.
