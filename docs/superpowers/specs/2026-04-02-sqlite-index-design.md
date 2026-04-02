# SQLite Metadata Index — Performance Infrastructure

**Date:** 2026-04-02
**Status:** Draft

## Overview

Replace the file-scanning query engine with a SQLite metadata index. Currently, every view and ritual command scans all `.md` files across all month directories, parsing YAML frontmatter on each one. This works fine at hundreds of entries but degrades as the collection grows into thousands.

The solution: a SQLite database that indexes entry metadata and body text. The `.md` files remain the source of truth — SQLite is a read-optimized cache that rebuilds from files if lost or corrupted.

### Design Principles

- **Markdown files are the source of truth.** The SQLite index is derived, disposable, and rebuildable. The user's entries are never at risk.
- **Write-through sync.** Every `save_entry()` and `delete` operation updates the index immediately. No drift.
- **No user-facing changes.** Same commands, same output, just faster.
- **Graceful degradation.** If the DB is missing, auto-rebuild from files. If corrupt, delete and rebuild. The app never crashes due to index state.
- **Single DB file.** Metadata, FTS5, and vectors all live in one SQLite database.

## 1. Database Schema

**Location:** `~/bute/.index/bute.db` (replaces `~/.vectors/bute.db`)

```sql
-- Metadata table
CREATE TABLE IF NOT EXISTS entries (
    entry_id       TEXT PRIMARY KEY,
    type           TEXT NOT NULL,        -- task, note, journal, calendar
    status         TEXT,                 -- active, done, dropped (NULL for non-tasks)
    body           TEXT NOT NULL,
    important      INTEGER DEFAULT 0,
    due            TEXT,                 -- ISO date or NULL
    scheduled_date TEXT,                 -- ISO date or NULL
    scheduled_time TEXT,                 -- HH:MM or NULL
    repeat         TEXT,
    tags           TEXT,                 -- JSON array: '["backend","urgent"]'
    created        TEXT NOT NULL,        -- ISO datetime
    extra_meta     TEXT                  -- JSON object for custom key:value pairs
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_type_status ON entries(type, status);
CREATE INDEX IF NOT EXISTS idx_created ON entries(created);
CREATE INDEX IF NOT EXISTS idx_due ON entries(due);
CREATE INDEX IF NOT EXISTS idx_scheduled_date ON entries(scheduled_date);

-- FTS5 for body text search
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    entry_id UNINDEXED,
    body,
    content=entries,
    content_rowid=rowid
);

-- Vector table (migrated from old location, unchanged schema)
CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
    entry_id TEXT PRIMARY KEY,
    embedding float[384]
);
```

### Tags Storage

Tags are stored as a JSON array string (`'["backend","urgent"]'`). Queries use SQLite's `json_each()`:

```sql
SELECT entry_id FROM entries, json_each(entries.tags)
WHERE json_each.value = 'backend';
```

This avoids a join table while keeping tag queries indexed and fast.

## 2. Module Structure

### New: `src/bute/db.py`

Owns the database connection, schema creation, and all index operations.

**Connection management:**
- `get_connection(config=None)` — lazy-open, creates DB and schema on first call. Loads sqlite-vec extension if available.
- `close()` — close the connection.

**Schema:**
- `ensure_schema()` — creates all tables and indexes. Called on first connection. Idempotent.

**Write operations:**
- `upsert_entry(entry: Entry)` — insert or replace a row in `entries` + update `entries_fts`. Accepts an `Entry` model object.
- `delete_entry(entry_id: str)` — remove from `entries` + `entries_fts`.

**Query operations:**
- `query_entries(**kwargs)` — returns list of `(entry_id, created)` tuples matching the given filters. All conditions are combined with AND (all must match). Supported keyword args:
  - `type: str` — entry type
  - `status: str` — task status
  - `tags: list[str]` — all must match (AND)
  - `tag: str` — single tag match
  - `created_date: date` — entries created on this date
  - `due_before: date` — entries with due date on or before
  - `due_on: date` — entries with due date on this date
  - `scheduled_date: date` — entries scheduled on this date
  - `has_due: bool` — entries that have a due date set
  - `has_tags: bool` — entries that have any tags
  - `exclude_status: str` — exclude entries with this status
  - `include_all_statuses: bool` — include done/dropped (default: exclude dropped)
- `search_text(query: str, type: str = None)` — FTS5 match on body, optional type filter. Returns list of `(entry_id, created)` tuples.

**Bulk operations:**
- `clear_all()` — delete all rows from `entries` + `entries_fts` (for rebuild).
- `count()` — return row count.

**Vector operations** remain in `vectors.py` but use the shared connection from `db.py`.

### Modified: `src/bute/storage.py`

**`save_entry()`** — after writing the .md file, calls `db.upsert_entry(entry)`. Catches and logs DB errors — a failed index write must never prevent the .md file from being saved.

**`load_entries_by_filter()`** — replaced. The 18 call sites are migrated to use `db.query_entries()` which returns entry IDs, then `load_entry()` to hydrate the full `Entry` objects from .md files for the matched subset only.

**`load_entries_by_date()`** — same pattern: `db.query_entries(created_date=target)`, then load matched .md files.

**`load_entry()`** — unchanged. Still reads a single .md file.

**`entry_path_from_id()`** — unchanged.

**Fallback:** If `db.query_entries()` raises (DB missing/corrupt), fall back to the current file-scan implementation. This means the file-scan code stays in the codebase as a recovery path, not deleted.

### Modified: `src/bute/ai/vectors.py`

- Remove `connect()`, `_connection`, `_db_path`, `close()`, `_get_connection()`.
- All functions call `db.get_connection()` instead of managing their own connection.
- `vec_entries` table creation moves to `db.ensure_schema()`.
- The `is_available()` check (for sqlite-vec import) stays in `vectors.py`.

### Modified: `src/bute/commands/action.py`

**`handle_delete()`** — add `db.delete_entry(entry_id)` alongside the existing `vec_delete()` call.

## 3. Query Migration — All 18 Call Sites

Every `load_entries_by_filter(lambda ...)` call is replaced with a `db.query_entries(...)` call followed by loading the matched .md files. The lambdas are all simple field checks that map directly to keyword arguments.

### views.py (5 call sites)

| Current predicate | Replacement |
|---|---|
| `e.type == TASK and e.status == ACTIVE` | `query_entries(type="task", status="active")` |
| `e.type == NOTE` | `query_entries(type="note")` |
| `e.type == JOURNAL` | `query_entries(type="journal")` |
| `e.type == CALENDAR` | `query_entries(type="calendar", scheduled_date=...)` |
| `tag in e.tags` | `query_entries(tag=tag)` |
| `e.due is not None and e.due <= today` | `query_entries(has_due=True, due_before=today)` |
| `bool(e.tags)` | `query_entries(has_tags=True)` |

### ritual_ops.py (8 call sites)

| Current predicate | Replacement |
|---|---|
| `e.type == TASK and e.status == ACTIVE and "today" in e.tags` | `query_entries(type="task", status="active", tag="today")` |
| `e.scheduled_date == today and e.type == CALENDAR` | `query_entries(type="calendar", scheduled_date=today)` |
| `e.type == TASK and e.status == DONE and e.created.date() == today` | `query_entries(type="task", status="done", created_date=today)` |
| `e.type == TASK and e.status == DROPPED and e.created.date() in range` | `query_entries(type="task", status="dropped", created_date=...)` |
| ...and similar patterns for weekly spread, active tasks, etc. | Direct keyword mappings |

### rituals.py (3 call sites), topic.py (1), nudges.py (1)

Same mechanical translation — all are simple field checks on type, status, tags, dates.

### Helper in storage.py

To avoid duplicating the "query IDs then load .md files" pattern across 18 sites, a helper:

```python
def query_and_load(config=None, sort_key=None, reverse=False, **kwargs) -> list[Entry]:
    """Query the index, load matched entries from .md files."""
    from bute.db import query_entries
    results = query_entries(config=config, **kwargs)
    entries = []
    for entry_id, _ in results:
        path = entry_path_from_id(entry_id, config)
        if path:
            entries.append(load_entry(path))
    if sort_key:
        entries.sort(key=sort_key, reverse=reverse)
    return entries
```

## 4. Graceful Degradation & Rebuild

### Auto-rebuild on missing DB

On first `get_connection()` call, if the DB file does not exist:

1. Display reassurance message:
   ```
   Your entries are safe — all data lives in your .md files.
   Building search index for faster lookups...
   ```
2. Display Rich progress bar:
   ```
   Indexing entries... ━━━━━━━━━━━━━━━━━━━━╸━━━━━━━━━━━  52% 1,247/2,400
   ```
3. Display completion message:
   ```
   Index built. 2,400 entries indexed.
   Tip: You can export your entries anytime with `bt export`.
   ```

### Auto-rebuild on corrupt DB

If a query raises a database error:

1. Delete the corrupt DB file.
2. Display message:
   ```
   Index needs rebuilding — your entries are safe in .md files.
   Rebuilding search index...
   ```
3. Same progress bar and completion message as above.
4. Retry the original query.

### `bute rebuild` command

Updated to rebuild everything in one pass — metadata, FTS5, and vectors:

1. Scan all `.md` files in `~/bute/entries/`.
2. Parse each with `load_entry()`.
3. For each entry:
   - `db.upsert_entry(entry)` — metadata + FTS5
   - `vectors.upsert(entry.id, vector)` — if embeddings available
4. Progress bar throughout.
5. Final message:
   ```
   Rebuilt index: 2,400 entries indexed, 2,400 vectors embedded.
   Your .md files are untouched — they're always the source of truth.
   ```

If embeddings are not installed, skip the vector step and adjust the message:
   ```
   Rebuilt index: 2,400 entries indexed. (Vectors skipped — embeddings not installed.)
   ```

### User reassurance

Every rebuild message — whether auto-triggered or manual — explicitly tells the user:
- Their entries are safe in .md files
- The index is derived/rebuildable
- They can export entries for safekeeping with `bt export` (once available)

This is important because a "rebuilding" message can feel alarming. The user should never worry about data loss.

## 5. DB Location Migration

The existing vector DB lives at `~/bute/.vectors/bute.db`. The new unified DB lives at `~/bute/.index/bute.db`.

On first run after upgrade:

1. If `~/bute/.index/bute.db` does not exist but `~/bute/.vectors/bute.db` does:
   - Move (rename) `.vectors/bute.db` to `.index/bute.db`
   - Remove the empty `.vectors/` directory
   - The existing `vec_entries` table comes along for free
   - Create the new `entries` and `entries_fts` tables in the moved DB
   - Run a metadata-only rebuild (no need to re-embed vectors)
2. If neither exists: fresh DB, full rebuild.
3. If `.index/bute.db` already exists: no migration needed.

This is a one-time migration that preserves existing vector embeddings.

## 6. Files Changed

| File | Change |
|------|--------|
| `src/bute/db.py` | **NEW** — connection, schema, CRUD, `query_entries()`, `search_text()` |
| `src/bute/storage.py` | **MODIFY** — `save_entry()` write-through, replace `load_entries_by_filter` with `query_and_load`, keep file-scan as fallback |
| `src/bute/ai/vectors.py` | **MODIFY** — use shared connection from `db.py`, remove own connection management |
| `src/bute/commands/views.py` | **MODIFY** — replace lambda predicates with `query_and_load()` keyword calls |
| `src/bute/commands/action.py` | **MODIFY** — add `db.delete_entry()` in `handle_delete()` |
| `src/bute/commands/search.py` | **MODIFY** — `rebuild_cmd` does metadata + FTS5 + vectors in one pass with progress bar |
| `src/bute/commands/rituals.py` | **MODIFY** — replace lambda predicates with `query_and_load()` keyword calls |
| `src/bute/ritual_ops.py` | **MODIFY** — replace lambda predicates with `query_and_load()` keyword calls |
| `src/bute/commands/topic.py` | **MODIFY** — replace `load_entries_by_filter` tag search with `query_and_load(tag=...)` |
| `src/bute/commands/nudges.py` | **MODIFY** — replace lambda predicate with `query_and_load()` keyword call |
| `tests/` | **ADD/MODIFY** — tests for `db.py`, updated tests for storage, migration tests |

## 7. Backlog Additions

These commands are enabled by the index but not implemented in this spec. Added to the project backlog for future work.

### `bt find <keyword>` — Full-text search across entries

FTS5-powered keyword search. Searches entry body text for exact/keyword matches.

```bash
bt find dentist                # search all entries
bt find -t faucet              # tasks only
bt find -n kitchen             # notes only
bt find -j overwhelmed         # journals only
bt find -c contractor          # calendar only
```

Flags: `-t` (tasks), `-n` (notes), `-j` (journals), `-c` (calendar). No flag = search all types.

Uses `db.search_text(query, type=...)` under the hood. Results displayed the same as `bt search` but for exact keyword matches instead of semantic similarity.

### `bt export` — Export all entries as a zip file

Exports all `.md` files from `~/bute/entries/` into a timestamped zip file, preserving the `YYYY-MM/` directory structure.

```bash
bt export                      # → ~/bute/exports/bute-2026-04-02.zip
bt export -o ~/Desktop         # → ~/Desktop/bute-2026-04-02.zip
```

Gives the user a portable backup of all their entries. Referenced in rebuild messages to reassure users about data safety.

## 8. What This Spec Does NOT Change

- **Entry format** — `.md` files with YAML frontmatter, unchanged.
- **CLI grammar** — all commands, arguments, flags stay the same.
- **Display output** — same Rich formatting, same columns, same grouping.
- **AI features** — semantic search, topic, nudges, collections all work the same.
- **Capture flow** — parser, signifiers, tags, collections unchanged.
- **State management** — `.state.json` unchanged.

## 9. Testing Strategy

- **Unit tests for `db.py`** — upsert, delete, query_entries with all keyword combinations, search_text, schema creation, connection management.
- **Integration tests** — save_entry writes both .md and DB, delete removes from both, rebuild produces consistent state.
- **Migration test** — `.vectors/bute.db` correctly moved and extended.
- **Fallback test** — corrupt/missing DB triggers rebuild, app still works.
- **Regression tests** — existing tests for views, rituals, actions still pass (they exercise the full path from command to display).
