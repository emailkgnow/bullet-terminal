# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is bt?

bt (Bullet Terminal) is a CLI life management system based on the Bullet Journal methodology. Single user, local data, plain Markdown files. The name mirrors BuJo (Bullet Journal) — same family, different medium. The distribution is `bullet-terminal`; the Python import package is still `bute` (invisible to users, so it was never renamed).

## Development Commands

```bash
# Install all deps (dev + optional)
uv sync --extra dev

# Run tests
uv run pytest                         # all tests
uv run pytest tests/test_capture.py   # single module
uv run pytest --cov=src/bute          # with coverage

# Install globally (for manual testing)
uv tool install --from . bullet-terminal --force --reinstall

# Build
uv build
```

## Architecture

### CLI Dispatch (cli.py — DwnGroup)

Custom Click group with 7-branch routing in `resolve_command()` (numbered 1–7 in the source):

1. **Word signifier with text** — `task`/`note`/`jrnl`/`cal` followed by text routes straight to capture, checked before the named-command lookup so `bt cal meet mom` doesn't get swallowed by the `calendar` view. Ahead of this, the retired words `journal`/`calendar` raise a pointer to `jrnl`/`cal`, and the removed `like` points at `bt find`.
2. **Named commands** — standard Click lookup (dp, tasks, notes, tags, etc.), plus the `bt overdue` → `bt due overdue` alias.
3. **Signifiers** — `t`, `n`, `j`, `c` (or words: `task`, `note`, `jrnl`, `cal`)
   - With text → **capture** (`bt t call dentist`)
   - Without text (or only `@tag`/view flags) → **view** (`bt t` → today's tasks)
   - With a bare `!` suffix and no text → the important-filtered view
4. **Important filter** — `!` alone → all important entries
5. **Tag filter** — `@tagname` (or a leading `-@tagname`) → cross-dimension filter (multi-tag: `@a @b -@c`)
6. **Number-action** — `1 done`, `2 3 drop` → action dispatch
7. **Unknown** — falls through to Click's own error

`b`, `w` and `m` are not letter shortcuts: `SHORT_TO_VIEW` maps only `t`/`n`/`j`/`c`, so `bt b`/`bt w`/`bt m` are unregistered and error like any unknown command.

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
  → models.py:Entry.create() → storage.py:save_entry() → db.upsert_entry() → confirm_capture()
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
| `db.py` | SQLite index — metadata, FTS5, and lazy reconciliation |
| `commands/tags.py` | Tag listing and filtering helpers |

### Local search (no LLM)

1. **SQLite index** — metadata + FTS5 at `.index/bt.db`, rebuildable from .md files via `bt rebuild`. Powers `bt find`.
2. **Lazy reconciliation** — `db.reconcile_index()` runs once per process on first read and detects externally-added/removed `.md` files, upserting or deleting matching rows. Enables the "bring your own AI" model where external agents (Claude Desktop + filesystem MCP, Claude Code, scripts) write valid .md files into `entries/` and bt picks them up automatically.

There is no built-in LLM. `bt chat` was removed in favor of BYOAI — the README's data-model section is the contract external agents read. When you change the data model, update README.md in the same commit.

## CLI Grammar (Current)

**Capture** — signifier + text:
```
bt t call dentist due:friday @backend    # single letter
bt task call dentist due:friday @backend # word form (also note, jrnl, cal)
bt t! fix prod bug                       # important modifier
bt c dentist time:14:30 date:03-30       # calendar: Mar 30 at 2:30 PM
bt c meeting time:9:00                   # calendar: today at 9:00 AM
bt c conference date:apr-15              # calendar: Apr 15, all day
bt n check OAuth docs date:04-10         # note: resurfaces in Focus Log Apr 10
bt t meditate repeat:daily               # recurring task (habit)
bt j lunch with @@Elham                  # double duty tag: body keeps "Elham", tags @elham
```

**Date/time metadata:**
Four keys, one spelling each — the typed word *is* the frontmatter key it writes.
- `date:` — scheduled / resurface date. Five forms, hyphen-separated, case-insensitive: `today`, `tomorrow`, a weekday (`friday`/`fri`), `jan-23`, `01-23`, `2026-01-23`.
- `time:` — `HH:MM`, read as 24-hour unless an `am`/`pm` suffix is given. Minutes are always required: `time:9:00`, `time:14:30`, `time:2:20pm`.
- `due:` — deadline, tasks only (same date forms as `date:`). Rejected on notes/journals/calendar with a pointer to `date:` (`parser.check_due_is_task_only`); an empty/`none` value (a clear) is still allowed so stray BYOAI-written `due` fields stay removable. On capture only, an `am`/`pm` time (`due:3:00pm`) means due today and fills `time:` unless one was given.
- `repeat:` — `daily` | `weekly` | `monthly` | `yearly`; anything else is rejected at capture.

Everything except full ISO resolves *forward*: `01-23` typed in September means next January. Use full ISO for a past date.

**Views** — signifier alone, or named commands:
```
bt t              # Tasks — Today: the task rows of the Focus Log
bt t -w           # Tasks — Weeklog: active tasks with week_date == this week (long form --weeklog)
bt t -b           # Tasks — Backlog: all active tasks
bt t -a           # Tasks — All: every task, any status, grouped by date (bt t -b -a also works)
bt t @backend     # any scope, filtered by tag
bt t! -b          # any scope, important only
bt n / j / c      # notes / journals / calendar (grouped by date)
bt -a             # Focus Log + hidden items (dropped, non-focus captures, past events)
bt                # Focus Log (or daily plan if not done today)
bt @tagname       # cross-dimension tag filter, as a tree grouped by type
bt @bt @ai        # entries with both tags (AND)
bt @bt -@done     # entries with @bt but not @done
bt -@habit        # all entries excluding @habit
bt !              # all important entries
bt t!             # important tasks (also: n!, j!, c!)
bt find <keyword> # partial-word search in full body + tags (-t -n -j -c to filter)
bt t -b --json      # numbered entry views as JSON (n = display number); not stats/streak/actions/captures
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
bt 6 clear date   # clear scheduled date
bt 6 clear time   # clear time
bt 6 clear repeat # clear repeat
bt 3              # read entry 3 in the viewer: e edit in $EDITOR, q quit
bt 3 5            # step through several with n/p
bt 3 weeklog      # defer — off today, into this week's Weeklog (bt t -w)
bt 3 backlog      # off today and this week — Backlog only (bt t -b)
bt undo           # undo last action
bt 3 undo         # undo last action on entry 3
```

**Tags**:
```
bt tags                           # all tags as a tree: total, then counts per type (. - = o)
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
- **Double duty tags (`@@`)** — `@tag` files the entry and removes the word from the body (unchanged). `@@tag` keeps the word in the body *as typed* and records the lowercased tag: `bt j lunch with @@Elham` → body "lunch with Elham", tag `elham`. Only `@@` is scanned inside tokens, so it survives quoting and glued punctuation while single `@` keeps whole-token matching — that's what protects literal text like `@server.tool()` and quoted `@backend` in notes about bt.
- **Tags are always lowercase** — normalized at creation (parser, `bt <n> @tag`, filters) *and* on every read in `storage._normalize_tags()`, so files written directly by external agents (BYOAI) can't split a tag into `Elham`/`elham`. Filtering is therefore case-insensitive: `bt @Elham` finds `elham`.
- **Tags are plain labels** — organize entries and power cross-dimension filters. The `+collection` syntax was removed — tags absorbed collections. A `tag_stages` SQLite table from the removed AI analyze feature still exists; harmless, may be pruned later.
- **Logs are derived** — no stored files. The Focus Log (`bt`) and the task scopes query entries for their period. Tasks show status (done = strikethrough, dropped = strikethrough + label). `bt -a` expands the Focus Log to include dropped tasks, non-focus captures from today, and past-timed events — replaces the retired `bt d` and the old per-day/per-week logs.
- **No Monthly Log, no event history** — `bt m` and the per-entry `events:` list were removed in `78c82dd` (2026-04-18): the list bloated frontmatter and existed almost only to power `bt m`'s day-by-day replay. Under BYOAI, retrospectives belong to external agents reading the date fields. `storage.py` still accepts a legacy `events` key and drops it on save. Don't rebuild `bt m` without revisiting that trade-off.
- **`bt` with no args** = planning entry point. On the trigger day (default Sunday, configurable via `core.wp_day`), runs weekly plan then daily plan. Other days, runs daily plan only. If all done, shows Focus Log.
- **Focus Log (`bt`)** — what matters today: tasks with `focus_date == today`, tasks due today or overdue, today's calendar events, all today's journals and notes. Any entry with `date:` (scheduled_date) matching today also surfaces. Other tasks stay in the Backlog (`bt t -b`) or this week's Weeklog (`bt t -w`). Curated and active-only — `bt -a` expands to dropped tasks, captures from today that lack focus, and past-timed events.
- **Task view titles share a root** — `Tasks — Today` / `Tasks — Weeklog` / `Tasks — Backlog` / `Tasks — All` (`bt t -a`), em dash, so the views read as one dimension at different zoom levels and rank correctly by size. `Notes`/`Journals`/`Calendar` stay bare nouns; tasks alone need the qualifier because they alone have multiple scopes.
- **One way to open an entry** — bare `bt <n>` opens `viewer.py`, a Textual app (metadata strip, rendered body, key footer). Reading is ~90% of why an entry gets opened, so it reads; `e`/`ctrl+e` suspends the viewer, runs `$EDITOR` (fallback `nano`) on the real `.md`, then re-indexes and re-renders. `open`/`edit`/`show`/`read`/`view` were folded in and raise a pointer (`action.REMOVED_ACTIONS`). Textual is a hard dependency so the nice path needs no Homebrew step (it replaced the optional `leaf` viewer); it is imported lazily so other commands don't pay its startup. Off a TTY (pipes, agents) `bt <n>` prints via Rich `display_entry_full` instead. `bt t|n|j|c open` (long-form capture) is unrelated and unchanged.
- **Weeklog, a coined noun** — the this-week scope is the *Weeklog*, built like *Backlog*, because an action names the place a task goes, not a time: `bt <n> focus` / `bt <n> weeklog` / `bt <n> backlog`, matching `Tasks — Today` / `Tasks — Weeklog` / `Tasks — Backlog` and the long flags `--weeklog` / `--backlog`. It replaced `bt <n> later` and `--week`; both raise a pointer to the new name (`action.REMOVED_ACTIONS`, the `--week` guard in `capture_cmd`), and `apply_undo` still accepts undo records saved as `later`.
- **Task scope is a flag, not a command** — `bt t` is today, `-w` is this week, `-b` is the backlog, and the same flag spells the scope on capture (`bt t -b <text>`). `bt b` and `bt w` were removed along with their `backlog`/`week` long forms. `t`/`n`/`j`/`c` are dimensions again, with no scope letters beside them.
- **Filters stack, scopes don't** — `@tag` and `!` compose on top of exactly one scope; `-w` and `-b` together is an error. On tasks, bare `-a` is itself the widest scope: `bt t -a` (and `bt t! -a`) is `Tasks — All`, every task in any status. It took over `bt t -b -a`, which still works as an alias. The old reading, today's tasks including done/dropped, was never documented and duplicated the task rows of `bt -a`. Anywhere else, `-a` widens status: `bt t -w -a`, `bt -a`, `bt n -a`.
- **`bt t` and `bt` share one definition of today** — `ritual_ops.get_today_tasks()` filters `get_daily_log()` to tasks, so the two views can't disagree about focus dates, overdue tasks or today's completions.
- **Focus state as dates, not tags** — `focus_date` and `week_date` are proper `Optional[date]` fields on `Entry`. Set by `bt dp` / `bt wp` / `bt focus` / capture. `bt <n> weeklog` swaps `focus_date` for this week's `week_date` (a task picked in `dp` has no `week_date`, so clearing focus alone would silently drop it to the Backlog); `bt <n> backlog` clears both. Either prints a dim hint when `due:` or `date:` still keeps the task in the Focus Log. Old dates expire naturally — no clearing ritual needed. Replaces the former `@today` / `@thisweek` system tags.
- **`bt wp`** includes task dump phase — add tasks before selecting for the week.
- **Display**: notes/journals/calendar always group by date with a Date column (`display_entry_list_grouped`, keyed on `scheduled_date` else `created`). Among task scopes only `bt t -a` (the full task dimension) groups the same way; `bt t`, `bt t -w`, and `bt t -b` stay flat lists, since a short curated list needs no date spine. `bt @tag` (the `tag_filter` command) is the one tree view (`display_entry_tree`): a branch per entry type in `. - = o` order, empty types skipped, numbers continuous down the tree, and the filtered tags hidden from each row since the root already names them. A tag cuts across dimensions, so type is its natural spine, not date.
- **Scheduling is universal** — `date:` (scheduled_date) works on all entry types. Tasks: the day to work on it (the deadline is `due:`, tasks only). Calendar: event date. Notes/journals: resurface date. All surface in the Focus Log on the target date. Only tasks can be overdue (past-due tasks linger; missed note/journal reminders don't).
- **Calendar sorting**: timed events first (chronologically), then untimed, then other entry types.
- **Time format**: stored as `HH:MM` (24h), displayed as `h:MM AM/PM`. Input is `HH:MM`, 24-hour unless suffixed `am`/`pm`; minutes are always required, so `time:9` is an error pointing at `time:9:00`. There is exactly one way to write any given time.
- **Date format**: five forms — `today`, `tomorrow`, weekday, `jan-23`, `01-23`, `2026-01-23`. The hyphen is the only separator and the dot is not a date character at all, which is what keeps `01-23` from colliding with a time. `01-23` is full ISO with the year dropped, so the month-day order is ISO's, not an American convention.
- **Signifier words are 3–4 letters** — `task`, `note`, `jrnl`, `cal`, each starting with its letter. `journal` and `calendar` were retired as typed words because they were the two long outliers; each new word is its word's conventional short form (`jrnl` is the established CLI spelling, `cal` the Unix command). Only the typed word changed: the stored `type:` values, `entries/` folders, and view titles (`Journals`, `Calendar`) keep the full nouns, so no data migration and the BYOAI contract is untouched. Typing an old word raises a pointer (`parser.REMOVED_SIGNIFIER_WORDS`), caught before the named-command lookup so `bt calendar` can't reach the internal `calendar` view command.
- **Reading is looser than typing** — `storage._normalize_time` does *not* call `resolve_time`. The input grammar is opinionated and has changed twice; files on disk are forever. It reads the canonical `'HH:MM'`, the retired spellings (`3pm`, `14.30`, `1430`), and the integer YAML produces from an *unquoted* `time: 14:30` (sexagesimal, 870). Anything unreadable returns `None` instead of raising, so one bad field can't hide an entry from every view.
- **One spelling per key, one spelling per value** — `d:`/`t:`/`r:` and the legacy numeric formats (`0407`, `3/29`, `1430`) went first; then the value grammar itself was cut to one form each (dot dates, `next-<day>`, glued `jan15`, bare hours, dot times, and the `tod`/`tom`/`tmr`/`tmrw` aliases). Rationale: on 161 real tasks only 6 carried any date metadata (the dp/wp/Focus Log flow does the prioritising), and 72% of all usage was on calendar entries, so the full words cost ~137 keystrokes across 25 weeks of real use. Typing a removed key raises a pointer to its replacement (`parser.REMOVED_META_KEYS`) rather than silently landing in `extra_meta` or being misread as a tag.
- **No built-in AI** — `bt chat` and the LLM layer were removed in favor of "bring your own AI." External agents (Claude Desktop + filesystem MCP, Claude Code, scripts) read/write `.md` files directly in `~/bullet-terminal/entries/`. bt's README is the schema contract; `db.reconcile_index()` picks up external writes on the next read. Semantic search is the agent's job too — see *No semantic search* below.
- **No semantic search** — `bt like` (fastembed + sqlite-vec) was removed 2026-09-24. A small embedding model matches *topic*, not meaning: `bt like fun` returned "feeling down" because both are about mood, and with no distance cutoff it always showed 10 hits, mostly noise. It cost ~75 MB of onnxruntime, an 87 MB model cache, the `vec_entries` table and vector-sync code in storage/action/rebuild. `bt find` covers literal recall; fuzzy recall ("my fun days") belongs to a BYOAI agent. `bt like` raises a pointer to both, and `db.get_connection()` discards an old index that still has `vec_entries` (the vec0 table can't be dropped without its module) and rebuilds it from the .md files.

## Backlog

### Commands — High Value
- ~~**Stale `@today`/`@thisweek` tag cleanup**~~ ✓ Done — replaced by `focus_date` and `week_date` date fields on `Entry`. Old dates expire naturally (a `focus_date` from last week simply doesn't match today's Focus Log), so no clearing ritual is needed. See `docs/superpowers/specs/2026-04-16-focus-date-fields-design.md`.
- ~~`bt due`~~ ✓ Done — overdue + due today + next 7 days (rolling). `bt due all` for all tasks with due dates.
- ~~`bt <n> untag @tag`~~ ✓ Done — replaced by `bt 1 clear @tag` (unified `clear` for all fields)
- ~~`bt edit <n>`~~ ✓ Done — now bare `bt <n>`: the viewer, `e` to edit in `$EDITOR`

### Commands — Medium Value
- ~~`bt streak`~~ Done — 7-day grid, current streak count, 30-day completion rate.
- ~~`bt reflect`~~ / `bt recap` — removed with the AI layer. For retrospectives, point your own AI agent at `entries/`.
- `bt w` — free again: the this-week task scope moved to the `-w` flag (`bt t -w`), so the bare `bt w` command no longer exists. A cross-dimension Weekly Log (Mon–Sun over all four types, `bt w last`, `bt w 14`) was documented as done but never existed; if it is still wanted, `bt w` is available for it again.
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
- ~~SQLite index for structured queries~~ In progress — see `docs/superpowers/specs/2026-04-02-sqlite-index-design.md`. Metadata + FTS5 in one DB, write-through sync, auto-rebuild.

### Design Guardrail
- **Stay BuJo, not Notion.** As bt grows into a PKM, resist becoming a general-purpose notes app. Every feature should serve the BuJo methodology — signifiers, rapid logging, rituals, migration. The CLI constraint and opinionated simplicity are features, not limitations. If a feature requires explaining, it probably doesn't belong.

