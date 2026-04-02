# SQLite Metadata Index — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the file-scanning query engine with a SQLite metadata index (+ FTS5 for body search) so all views, rituals, and filters query the DB instead of parsing every `.md` file.

**Architecture:** A new `db.py` module manages a single SQLite database (`~/bute/.index/bute.db`) containing a metadata table, an FTS5 virtual table, and the existing `vec_entries` table. `storage.py` writes through to the DB on every save/delete. All 18 `load_entries_by_filter()` call sites are replaced with `db.query_entries()` keyword queries. The `.md` files remain the source of truth; the DB is a rebuildable cache.

**Tech Stack:** Python `sqlite3` (stdlib), SQLite FTS5, `sqlite-vec` (existing dependency), Rich `Progress` (existing dependency)

**Spec:** `docs/superpowers/specs/2026-04-02-sqlite-index-design.md`

---

### Task 1: Create `db.py` — Schema and Connection Management

**Files:**
- Create: `src/bute/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write test for schema creation**

```python
# tests/test_db.py
"""Tests for SQLite metadata index."""

import sqlite3

import pytest

from bute.db import close, ensure_schema, get_connection


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect DB to temp directory."""
    index_dir = tmp_path / ".index"
    index_dir.mkdir()
    monkeypatch.setattr("bute.db._db_path_override", index_dir / "bute.db")
    yield
    close()


def test_ensure_schema_creates_tables():
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' OR type='view'"
    ).fetchall()
    table_names = {row[0] for row in tables}
    assert "entries" in table_names
    assert "entries_fts" in table_names


def test_ensure_schema_creates_indexes():
    conn = get_connection()
    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    ).fetchall()
    index_names = {row[0] for row in indexes}
    assert "idx_type_status" in index_names
    assert "idx_created" in index_names
    assert "idx_due" in index_names
    assert "idx_scheduled_date" in index_names


def test_ensure_schema_idempotent():
    get_connection()
    get_connection()  # second call should not error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bute.db'`

- [ ] **Step 3: Implement `db.py` — connection and schema**

```python
# src/bute/db.py
"""SQLite metadata index for bute — schema, connection, CRUD."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from bute.config import get_data_dir

logger = logging.getLogger(__name__)

_connection: sqlite3.Connection | None = None
_db_path_override: Path | None = None  # for tests


def _db_path(config=None) -> Path:
    if _db_path_override is not None:
        return _db_path_override
    data_dir = get_data_dir(config)
    index_dir = data_dir / ".index"
    index_dir.mkdir(parents=True, exist_ok=True)
    return index_dir / "bute.db"


def get_connection(config=None) -> sqlite3.Connection:
    """Get or create the shared DB connection. Creates schema on first call."""
    global _connection
    if _connection is not None:
        return _connection

    path = _db_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    _connection = db
    _load_vec_extension(db)
    ensure_schema(db)
    return db


def _load_vec_extension(db: sqlite3.Connection) -> None:
    """Load sqlite-vec if available. No-op if not installed."""
    try:
        import sqlite_vec
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
    except ImportError:
        pass


def ensure_schema(db: sqlite3.Connection | None = None) -> None:
    """Create all tables and indexes. Idempotent."""
    if db is None:
        db = get_connection()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS entries (
            entry_id       TEXT PRIMARY KEY,
            type           TEXT NOT NULL,
            status         TEXT,
            body           TEXT NOT NULL,
            important      INTEGER DEFAULT 0,
            due            TEXT,
            scheduled_date TEXT,
            scheduled_time TEXT,
            repeat         TEXT,
            tags           TEXT,
            created        TEXT NOT NULL,
            extra_meta     TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_type_status ON entries(type, status);
        CREATE INDEX IF NOT EXISTS idx_created ON entries(created);
        CREATE INDEX IF NOT EXISTS idx_due ON entries(due);
        CREATE INDEX IF NOT EXISTS idx_scheduled_date ON entries(scheduled_date);
    """)

    # FTS5 — separate statement (can't be in executescript with IF NOT EXISTS reliably)
    db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
            entry_id UNINDEXED,
            body,
            content=entries,
            content_rowid=rowid
        )
    """)

    # Vec table — only if sqlite-vec is loaded
    try:
        db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
                entry_id TEXT PRIMARY KEY,
                embedding float[384]
            )
        """)
    except sqlite3.OperationalError:
        pass  # sqlite-vec not loaded

    db.commit()


def close() -> None:
    """Close the DB connection."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/db.py tests/test_db.py
git commit -m "feat: add db.py with SQLite schema and connection management"
```

---

### Task 2: Add `upsert_entry()` and `delete_entry()` to `db.py`

**Files:**
- Modify: `src/bute/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write tests for upsert and delete**

Add to `tests/test_db.py`:

```python
import json
from datetime import date, datetime, timezone

from bute.db import close, delete_entry, get_connection, upsert_entry
from bute.models import Entry, EntryType, TaskStatus


def test_upsert_entry_inserts():
    entry = Entry.create(EntryType.TASK, "call dentist", tags=["health"])
    upsert_entry(entry)

    conn = get_connection()
    row = conn.execute(
        "SELECT entry_id, type, status, body, tags FROM entries WHERE entry_id = ?",
        (entry.id,),
    ).fetchone()
    assert row is not None
    assert row[0] == entry.id
    assert row[1] == "task"
    assert row[2] == "active"
    assert row[3] == "call dentist"
    assert json.loads(row[4]) == ["health"]


def test_upsert_entry_updates():
    entry = Entry.create(EntryType.TASK, "call dentist")
    upsert_entry(entry)
    entry.body = "call doctor"
    entry.status = TaskStatus.DONE
    upsert_entry(entry)

    conn = get_connection()
    row = conn.execute(
        "SELECT body, status FROM entries WHERE entry_id = ?", (entry.id,)
    ).fetchone()
    assert row[0] == "call doctor"
    assert row[1] == "done"


def test_upsert_entry_updates_fts():
    entry = Entry.create(EntryType.TASK, "call dentist")
    upsert_entry(entry)

    conn = get_connection()
    rows = conn.execute(
        "SELECT entry_id FROM entries_fts WHERE body MATCH 'dentist'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == entry.id


def test_upsert_entry_note_no_status():
    entry = Entry.create(EntryType.NOTE, "some note")
    upsert_entry(entry)

    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM entries WHERE entry_id = ?", (entry.id,)
    ).fetchone()
    assert row[0] is None


def test_delete_entry():
    entry = Entry.create(EntryType.TASK, "to be deleted")
    upsert_entry(entry)
    delete_entry(entry.id)

    conn = get_connection()
    row = conn.execute(
        "SELECT entry_id FROM entries WHERE entry_id = ?", (entry.id,)
    ).fetchone()
    assert row is None


def test_delete_entry_removes_fts():
    entry = Entry.create(EntryType.TASK, "findable text")
    upsert_entry(entry)
    delete_entry(entry.id)

    conn = get_connection()
    rows = conn.execute(
        "SELECT entry_id FROM entries_fts WHERE body MATCH 'findable'"
    ).fetchall()
    assert len(rows) == 0


def test_delete_nonexistent_entry():
    delete_entry("nonexistent_id")  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -v -k "upsert or delete"`
Expected: FAIL — `ImportError: cannot import name 'upsert_entry'`

- [ ] **Step 3: Implement upsert_entry and delete_entry**

Add to `src/bute/db.py`:

```python
import json

from bute.models import Entry


def upsert_entry(entry: Entry, config=None) -> None:
    """Insert or replace an entry in the metadata table and FTS5 index."""
    db = get_connection(config)

    tags_json = json.dumps(entry.tags) if entry.tags else "[]"
    extra_json = json.dumps(entry.extra_meta) if entry.extra_meta else "{}"

    # Delete existing FTS row (content-sync table requires manual delete before replace)
    db.execute(
        "DELETE FROM entries_fts WHERE entry_id = ?", (entry.id,)
    )

    db.execute(
        """INSERT OR REPLACE INTO entries
           (entry_id, type, status, body, important, due, scheduled_date,
            scheduled_time, repeat, tags, created, extra_meta)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entry.id,
            entry.type.value,
            entry.status.value if entry.status else None,
            entry.body,
            1 if entry.important else 0,
            entry.due.isoformat() if entry.due else None,
            entry.scheduled_date.isoformat() if entry.scheduled_date else None,
            entry.scheduled_time,
            entry.repeat,
            tags_json,
            entry.created.isoformat(),
            extra_json,
        ),
    )

    # Insert into FTS
    db.execute(
        "INSERT INTO entries_fts (entry_id, body) VALUES (?, ?)",
        (entry.id, entry.body),
    )

    db.commit()


def delete_entry(entry_id: str, config=None) -> None:
    """Remove an entry from the metadata table and FTS5 index."""
    db = get_connection(config)
    db.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry_id,))
    db.execute("DELETE FROM entries WHERE entry_id = ?", (entry_id,))
    db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/db.py tests/test_db.py
git commit -m "feat: add upsert_entry and delete_entry to db.py"
```

---

### Task 3: Add `query_entries()` to `db.py`

**Files:**
- Modify: `src/bute/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write tests for query_entries**

Add to `tests/test_db.py`:

```python
from datetime import timedelta

from bute.db import query_entries, upsert_entry
from bute.models import Entry, EntryType, TaskStatus


def _make_entry(type_, body, **kwargs):
    """Helper to create and index an entry."""
    entry = Entry.create(type_, body, **kwargs)
    upsert_entry(entry)
    return entry


def test_query_by_type():
    t = _make_entry(EntryType.TASK, "a task")
    n = _make_entry(EntryType.NOTE, "a note")
    results = query_entries(type="task")
    ids = [r[0] for r in results]
    assert t.id in ids
    assert n.id not in ids


def test_query_by_type_and_status():
    active = _make_entry(EntryType.TASK, "active task")
    done = Entry.create(EntryType.TASK, "done task")
    done.status = TaskStatus.DONE
    upsert_entry(done)

    results = query_entries(type="task", status="active")
    ids = [r[0] for r in results]
    assert active.id in ids
    assert done.id not in ids


def test_query_by_tag():
    tagged = _make_entry(EntryType.TASK, "tagged", tags=["backend"])
    untagged = _make_entry(EntryType.TASK, "untagged")
    results = query_entries(tag="backend")
    ids = [r[0] for r in results]
    assert tagged.id in ids
    assert untagged.id not in ids


def test_query_by_multiple_tags():
    both = _make_entry(EntryType.TASK, "both tags", tags=["backend", "urgent"])
    one = _make_entry(EntryType.TASK, "one tag", tags=["backend"])
    results = query_entries(tags=["backend", "urgent"])
    ids = [r[0] for r in results]
    assert both.id in ids
    assert one.id not in ids


def test_query_by_created_date():
    entry = _make_entry(EntryType.TASK, "today task")
    results = query_entries(created_date=date.today())
    ids = [r[0] for r in results]
    assert entry.id in ids


def test_query_by_scheduled_date():
    today = date.today()
    entry = _make_entry(EntryType.CALENDAR, "meeting", scheduled_date=today)
    results = query_entries(scheduled_date=today)
    ids = [r[0] for r in results]
    assert entry.id in ids


def test_query_by_due_before():
    today = date.today()
    overdue = _make_entry(EntryType.TASK, "overdue", due=today - timedelta(days=1))
    future = _make_entry(EntryType.TASK, "future", due=today + timedelta(days=7))
    results = query_entries(has_due=True, due_before=today)
    ids = [r[0] for r in results]
    assert overdue.id in ids
    assert future.id not in ids


def test_query_has_due():
    with_due = _make_entry(EntryType.TASK, "has due", due=date.today())
    no_due = _make_entry(EntryType.TASK, "no due")
    results = query_entries(has_due=True)
    ids = [r[0] for r in results]
    assert with_due.id in ids
    assert no_due.id not in ids


def test_query_has_tags():
    tagged = _make_entry(EntryType.TASK, "tagged", tags=["foo"])
    untagged = _make_entry(EntryType.TASK, "untagged")
    results = query_entries(has_tags=True)
    ids = [r[0] for r in results]
    assert tagged.id in ids
    assert untagged.id not in ids


def test_query_exclude_status():
    active = _make_entry(EntryType.TASK, "active")
    dropped = Entry.create(EntryType.TASK, "dropped")
    dropped.status = TaskStatus.DROPPED
    upsert_entry(dropped)
    results = query_entries(type="task", exclude_status="dropped")
    ids = [r[0] for r in results]
    assert active.id in ids
    assert dropped.id not in ids


def test_query_no_filters_returns_all():
    _make_entry(EntryType.TASK, "t1")
    _make_entry(EntryType.NOTE, "n1")
    results = query_entries()
    assert len(results) >= 2


def test_query_created_date_range():
    """Entries created today should match created_date=today even across timezones."""
    entry = _make_entry(EntryType.TASK, "today entry")
    results = query_entries(created_date=date.today())
    ids = [r[0] for r in results]
    assert entry.id in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -v -k "test_query"`
Expected: FAIL — `ImportError: cannot import name 'query_entries'`

- [ ] **Step 3: Implement query_entries**

Add to `src/bute/db.py`:

```python
from datetime import date


def query_entries(
    config=None,
    *,
    type: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    tags: list[str] | None = None,
    created_date: date | None = None,
    scheduled_date: date | None = None,
    due_before: date | None = None,
    due_on: date | None = None,
    has_due: bool = False,
    has_tags: bool = False,
    exclude_status: str | None = None,
    important: bool | None = None,
    created_since: date | None = None,
    created_until: date | None = None,
) -> list[tuple[str, str]]:
    """Query the index. Returns list of (entry_id, created) tuples.

    All conditions are combined with AND (all must match).
    """
    db = get_connection(config)
    conditions = []
    params: list = []

    if type is not None:
        conditions.append("type = ?")
        params.append(type)

    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    if exclude_status is not None:
        conditions.append("(status IS NULL OR status != ?)")
        params.append(exclude_status)

    if tag is not None:
        conditions.append(
            "entry_id IN (SELECT e.entry_id FROM entries e, json_each(e.tags) j WHERE j.value = ?)"
        )
        params.append(tag)

    if tags is not None:
        for t in tags:
            conditions.append(
                "entry_id IN (SELECT e.entry_id FROM entries e, json_each(e.tags) j WHERE j.value = ?)"
            )
            params.append(t)

    if created_date is not None:
        conditions.append("date(created) = ?")
        params.append(created_date.isoformat())

    if created_since is not None:
        conditions.append("date(created) >= ?")
        params.append(created_since.isoformat())

    if created_until is not None:
        conditions.append("date(created) <= ?")
        params.append(created_until.isoformat())

    if scheduled_date is not None:
        conditions.append("scheduled_date = ?")
        params.append(scheduled_date.isoformat())

    if due_before is not None:
        conditions.append("due <= ?")
        params.append(due_before.isoformat())

    if due_on is not None:
        conditions.append("due = ?")
        params.append(due_on.isoformat())

    if has_due:
        conditions.append("due IS NOT NULL")

    if has_tags:
        conditions.append("tags != '[]'")

    if important is not None:
        conditions.append("important = ?")
        params.append(1 if important else 0)

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"SELECT entry_id, created FROM entries WHERE {where} ORDER BY created DESC"

    rows = db.execute(sql, params).fetchall()
    return [(row[0], row[1]) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/db.py tests/test_db.py
git commit -m "feat: add query_entries with keyword-based SQL queries"
```

---

### Task 4: Add `search_text()` and bulk operations to `db.py`

**Files:**
- Modify: `src/bute/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write tests for search_text, clear_all, count**

Add to `tests/test_db.py`:

```python
from bute.db import clear_all, count, search_text


def test_search_text_basic():
    _make_entry(EntryType.TASK, "call the dentist tomorrow")
    _make_entry(EntryType.NOTE, "meeting notes from friday")
    results = search_text("dentist")
    ids = [r[0] for r in results]
    assert len(ids) == 1


def test_search_text_with_type_filter():
    _make_entry(EntryType.TASK, "buy groceries for dinner")
    _make_entry(EntryType.NOTE, "grocery list for dinner")
    results = search_text("dinner", type="task")
    ids = [r[0] for r in results]
    assert len(ids) == 1


def test_search_text_no_results():
    _make_entry(EntryType.TASK, "something else entirely")
    results = search_text("xyznonexistent")
    assert len(results) == 0


def test_count():
    assert count() == 0
    _make_entry(EntryType.TASK, "task 1")
    _make_entry(EntryType.NOTE, "note 1")
    assert count() == 2


def test_clear_all():
    _make_entry(EntryType.TASK, "task 1")
    _make_entry(EntryType.NOTE, "note 1")
    assert count() == 2
    clear_all()
    assert count() == 0


def test_clear_all_clears_fts():
    _make_entry(EntryType.TASK, "findable entry")
    clear_all()
    results = search_text("findable")
    assert len(results) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -v -k "search_text or count or clear_all"`
Expected: FAIL — `ImportError: cannot import name 'search_text'`

- [ ] **Step 3: Implement search_text, clear_all, count**

Add to `src/bute/db.py`:

```python
def search_text(
    query: str, type: str | None = None, limit: int = 50, config=None
) -> list[tuple[str, str]]:
    """FTS5 full-text search on entry body. Returns (entry_id, created) tuples."""
    db = get_connection(config)

    if type is not None:
        rows = db.execute(
            """SELECT f.entry_id, e.created
               FROM entries_fts f
               JOIN entries e ON f.entry_id = e.entry_id
               WHERE f.body MATCH ? AND e.type = ?
               LIMIT ?""",
            (query, type, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT f.entry_id, e.created
               FROM entries_fts f
               JOIN entries e ON f.entry_id = e.entry_id
               WHERE f.body MATCH ?
               LIMIT ?""",
            (query, limit),
        ).fetchall()

    return [(row[0], row[1]) for row in rows]


def clear_all(config=None) -> None:
    """Delete all rows from entries and FTS. For rebuild."""
    db = get_connection(config)
    db.execute("DELETE FROM entries_fts")
    db.execute("DELETE FROM entries")
    db.commit()


def count(config=None) -> int:
    """Return number of entries in the index."""
    db = get_connection(config)
    row = db.execute("SELECT COUNT(*) FROM entries").fetchone()
    return row[0] if row else 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/db.py tests/test_db.py
git commit -m "feat: add search_text, clear_all, count to db.py"
```

---

### Task 5: Wire `storage.py` Write-Through

**Files:**
- Modify: `src/bute/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write test for write-through on save**

Add to `tests/test_storage.py`:

```python
def test_save_entry_writes_to_db(tmp_data):
    """save_entry should upsert to the SQLite index."""
    from bute.db import close, get_connection
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    entry = Entry.create(EntryType.TASK, "test write-through")
    save_entry(entry)

    conn = get_connection()
    row = conn.execute(
        "SELECT body FROM entries WHERE entry_id = ?", (entry.id,)
    ).fetchone()
    assert row is not None
    assert row[0] == "test write-through"
    close()


def test_update_entry_updates_db(tmp_data):
    """update_entry should update the SQLite index."""
    from bute.db import close, get_connection
    from bute.models import Entry, EntryType, TaskStatus
    from bute.storage import save_entry, update_entry

    entry = Entry.create(EntryType.TASK, "original")
    save_entry(entry)
    entry.body = "updated"
    entry.status = TaskStatus.DONE
    update_entry(entry)

    conn = get_connection()
    row = conn.execute(
        "SELECT body, status FROM entries WHERE entry_id = ?", (entry.id,)
    ).fetchone()
    assert row[0] == "updated"
    assert row[1] == "done"
    close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storage.py -v -k "write_through or updates_db"`
Expected: FAIL — no row found in DB (write-through not wired yet)

- [ ] **Step 3: Modify `storage.py` to write through on save**

In `src/bute/storage.py`, modify `save_entry()`:

```python
def save_entry(entry: Entry, config=None) -> Path:
    """Write an entry to disk as a Markdown file with YAML frontmatter."""
    path = entry_path(entry, config)
    path.parent.mkdir(parents=True, exist_ok=True)

    post = frontmatter.Post(
        content=entry.body,
        **entry.to_frontmatter_dict(),
    )
    path.write_text(frontmatter.dumps(post))

    # Write-through to SQLite index
    try:
        from bute.db import upsert_entry
        upsert_entry(entry, config)
    except Exception:
        import logging
        logging.getLogger(__name__).debug(
            "Index write failed for %s", entry.id[:8], exc_info=True
        )

    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -v -k "write_through or updates_db"`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest -x -v`
Expected: PASS (all existing tests still pass)

- [ ] **Step 6: Commit**

```bash
git add src/bute/storage.py tests/test_storage.py
git commit -m "feat: wire write-through from storage.py to SQLite index"
```

---

### Task 6: Wire `handle_delete()` to DB

**Files:**
- Modify: `src/bute/commands/action.py`
- Modify: `tests/test_action.py`

- [ ] **Step 1: Write test for delete removing from DB**

Add to `tests/test_action.py`:

```python
def test_handle_delete_removes_from_db(tmp_data):
    """handle_delete should remove the entry from the SQLite index."""
    from bute.commands.action import handle_delete
    from bute.db import close, count, get_connection, upsert_entry
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    entry = Entry.create(EntryType.TASK, "to delete")
    save_entry(entry)  # writes .md and DB via write-through

    handle_delete(entry, [], None)

    conn = get_connection()
    row = conn.execute(
        "SELECT entry_id FROM entries WHERE entry_id = ?", (entry.id,)
    ).fetchone()
    assert row is None
    close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_action.py -v -k "removes_from_db"`
Expected: FAIL — row still in DB after delete

- [ ] **Step 3: Modify `handle_delete` in `action.py`**

In `src/bute/commands/action.py`, update `handle_delete()`:

```python
def handle_delete(entry: Entry, args: list[str], config) -> None:
    """Permanently delete an entry from disk, vector DB, and index."""
    path = entry_path_from_id(entry.id, config)
    if path and path.exists():
        path.unlink()
    from bute.ai.vectors import is_available, delete as vec_delete
    if is_available():
        vec_delete(entry.id, config)
    try:
        from bute.db import delete_entry
        delete_entry(entry.id, config)
    except Exception:
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_action.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/action.py tests/test_action.py
git commit -m "feat: wire handle_delete to remove entries from SQLite index"
```

---

### Task 7: Add `query_and_load()` Helper to `storage.py`

**Files:**
- Modify: `src/bute/storage.py`
- Modify: `tests/test_storage_queries.py`

- [ ] **Step 1: Write test for query_and_load**

Add to `tests/test_storage_queries.py`:

```python
from bute.storage import query_and_load
from bute.models import Entry, EntryType, TaskStatus


def test_query_and_load_by_type(populated_data):
    entries = query_and_load(type="task", status="active")
    assert len(entries) == 2
    assert all(e.type == EntryType.TASK for e in entries)


def test_query_and_load_by_tag(populated_data):
    entries = query_and_load(tag="backend")
    assert len(entries) == 1
    assert entries[0].body == "fix bug"


def test_query_and_load_returns_full_entries(populated_data):
    """Returned entries should be fully hydrated from .md files."""
    entries = query_and_load(type="task", status="active")
    for e in entries:
        assert e.id is not None
        assert e.body is not None
        assert e.created is not None
        assert isinstance(e.type, EntryType)


def test_query_and_load_empty(tmp_data):
    entries = query_and_load(type="task")
    assert entries == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storage_queries.py -v -k "query_and_load"`
Expected: FAIL — `ImportError: cannot import name 'query_and_load'`

- [ ] **Step 3: Implement query_and_load**

Add to `src/bute/storage.py`:

```python
def query_and_load(config=None, sort_key=None, reverse=False, **kwargs) -> list[Entry]:
    """Query the SQLite index and load matched entries from .md files.

    Falls back to load_entries_by_filter if the DB is unavailable.
    Keyword args are passed to db.query_entries().
    """
    try:
        from bute.db import query_entries
        results = query_entries(config=config, **kwargs)
    except Exception:
        import logging
        logging.getLogger(__name__).debug("DB query failed, falling back to file scan", exc_info=True)
        return load_entries_by_filter(lambda e: True, config)

    entries = []
    for entry_id, _ in results:
        path = entry_path_from_id(entry_id, config)
        if path:
            try:
                entries.append(load_entry(path))
            except Exception:
                continue
    if sort_key:
        entries.sort(key=sort_key, reverse=reverse)
    return entries
```

- [ ] **Step 4: Update the `populated_data` fixture to trigger write-through**

The `populated_data` fixture in `conftest.py` calls `save_entry()`, which now writes through to the DB. Verify this works by checking that tests pass without any fixture changes.

Run: `uv run pytest tests/test_storage_queries.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/storage.py tests/test_storage_queries.py
git commit -m "feat: add query_and_load helper for indexed queries with .md hydration"
```

---

### Task 8: Migrate `views.py` Call Sites

**Files:**
- Modify: `src/bute/commands/views.py`
- Existing tests: `tests/test_views.py`

- [ ] **Step 1: Read existing view tests to understand coverage**

Run: `uv run pytest tests/test_views.py -v --collect-only`
Understand which views have tests so regressions are caught.

- [ ] **Step 2: Replace `_dimension_command` predicate with `query_and_load`**

Modify `src/bute/commands/views.py` — replace the `_dimension_command` factory:

```python
from bute.storage import query_and_load


def _dimension_command(name, entry_type, label, group_by_date=False):
    """Factory for dimension view commands (tasks, notes, journals, calendar)."""

    @click.command(name)
    @click.argument("tag", required=False, default=None)
    @click.option("--all", "-a", "show_all", is_flag=True, help="Include done/dropped.")
    @click.pass_context
    def cmd(ctx, tag, show_all):
        config = ctx.obj.get("config")

        kwargs = {"type": entry_type.value}
        if tag:
            kwargs["tag"] = tag
        if not show_all and entry_type == EntryType.TASK:
            kwargs["status"] = "active"

        entries = query_and_load(config, **kwargs)

        title_parts = [label]
        if tag:
            title_parts.append(f"@{tag}")
        if show_all and entry_type == EntryType.TASK:
            title_parts[0] = f"All {label}"
        title = " ".join(title_parts)

        if group_by_date:
            display_entry_list_grouped(entries, title)
        else:
            display_entry_list(entries, title)
        save_state(name, [e.id for e in entries], config)

    cmd.__doc__ = f"Show {label.lower()}. Optional @tag to filter."
    return cmd
```

- [ ] **Step 3: Replace `important_cmd` predicate**

```python
@click.command("important", hidden=True)
@click.argument("entry_type", required=False, default=None)
@click.option("--all", "-a", "show_all", is_flag=True, help="Include done/dropped.")
@click.pass_context
def important_cmd(ctx, entry_type, show_all):
    """Show important entries. Optional type filter (task, note, journal, cal)."""
    config = ctx.obj.get("config")

    type_map = {
        "task": EntryType.TASK, "t": EntryType.TASK,
        "note": EntryType.NOTE, "n": EntryType.NOTE,
        "journal": EntryType.JOURNAL, "j": EntryType.JOURNAL,
        "cal": EntryType.CALENDAR, "c": EntryType.CALENDAR,
    }
    filter_type = type_map.get(entry_type) if entry_type else None

    kwargs = {"important": True}
    if filter_type:
        kwargs["type"] = filter_type.value
    if not show_all:
        kwargs["exclude_status"] = "dropped"

    entries = query_and_load(config, **kwargs)

    # Post-filter: if not show_all, exclude done tasks (but keep done notes/journals)
    if not show_all:
        entries = [
            e for e in entries
            if not (e.type == EntryType.TASK and e.status != TaskStatus.ACTIVE)
        ]

    if filter_type:
        type_label = {
            EntryType.TASK: "Tasks",
            EntryType.NOTE: "Notes",
            EntryType.JOURNAL: "Journals",
            EntryType.CALENDAR: "Events",
        }[filter_type]
        title = f"{'All ' if show_all else ''}Important {type_label}"
    else:
        title = f"{'All ' if show_all else ''}Important"

    display_entry_list(entries, title)
    save_state("important", [e.id for e in entries], config)
```

- [ ] **Step 4: Replace `tag_filter_cmd` predicate**

```python
@click.command("tag_filter", hidden=True)
@click.argument("tag")
@click.pass_context
def tag_filter_cmd(ctx, tag):
    """Show all entries with a given tag."""
    config = ctx.obj.get("config")
    entries = query_and_load(config, tag=tag)
    display_entry_list(entries, f"@{tag}")
    save_state("tag_filter", [e.id for e in entries], config)
```

- [ ] **Step 5: Replace `tags_cmd` predicate**

```python
@click.command("tags")
@click.pass_context
def tags_cmd(ctx):
    """List all tags with entry counts."""
    config = ctx.obj.get("config")
    entries = query_and_load(config, has_tags=True)
    # ... rest of function unchanged
```

- [ ] **Step 6: Replace `due_cmd` predicate**

```python
    entries = query_and_load(
        config, type="task", status="active", has_due=True
    )
```

Replace the `load_entries_by_filter(...)` call in `due_cmd` with this. The rest of the function (sorting, grouping) stays unchanged.

- [ ] **Step 7: Update imports**

Remove `load_entries_by_filter` from the imports at the top of `views.py`. Add `query_and_load`:

```python
from bute.storage import query_and_load
```

Keep `load_entries_by_filter` import only if still used. After these changes, it should no longer be imported in `views.py`.

- [ ] **Step 8: Run view tests**

Run: `uv run pytest tests/test_views.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/bute/commands/views.py
git commit -m "refactor: migrate views.py from file-scan predicates to query_and_load"
```

---

### Task 9: Migrate `ritual_ops.py` Call Sites

**Files:**
- Modify: `src/bute/ritual_ops.py`
- Existing tests: `tests/test_ritual_ops.py`

- [ ] **Step 1: Replace `get_today_schedule` (lines 25-49)**

```python
def get_today_schedule(config=None) -> list[Entry]:
    """Calendar entries for today — both created today and scheduled for today."""
    from bute.storage import query_and_load
    today = date.today()

    # Entries created today that are calendar type
    today_entries = load_entries_by_date(today, config)
    today_calendar = [e for e in today_entries if e.type == EntryType.CALENDAR]

    # Entries scheduled for today but created on a different day
    scheduled_today = query_and_load(
        config, type="calendar", scheduled_date=today
    )
    scheduled_today = [e for e in scheduled_today if e.created.date() != today]

    # Combine and deduplicate by ID
    seen = set()
    result = []
    for e in today_calendar + scheduled_today:
        if e.id not in seen:
            seen.add(e.id)
            result.append(e)
    return sorted(result, key=lambda e: (e.scheduled_time or "", e.created))
```

- [ ] **Step 2: Replace `get_daily_log` today_tasks query (lines 79-86)**

```python
    # Also include active tasks tagged @today but created on a different day
    from bute.storage import query_and_load
    today_tasks = query_and_load(
        config, type="task", status="active", tag="today"
    )
    today_tasks = [e for e in today_tasks if e.created.date() != today]
```

- [ ] **Step 3: Replace `get_daily_log` scheduled_today query (lines 95-102)**

```python
    # Also include calendar events scheduled for today but created on a different day
    scheduled_today = query_and_load(
        config, type="calendar", scheduled_date=today
    )
    scheduled_today = [e for e in scheduled_today if e.created.date() != today]
```

- [ ] **Step 4: Replace `get_week_entries` (lines 123-137)**

```python
def get_week_entries(target_date: date | None = None, config=None) -> list[Entry]:
    """All entries for the Mon-Sun week containing target_date."""
    from bute.storage import query_and_load
    d = target_date or date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    today = date.today()

    entries = query_and_load(
        config, created_since=monday, created_until=min(sunday, today)
    )
    return sorted(entries, key=lambda e: e.created)
```

- [ ] **Step 5: Replace `get_tasks_done_today` (lines 140-152)**

```python
def get_tasks_done_today(config=None) -> list[Entry]:
    """Tasks marked done with file mtime today (proxy for status-change date)."""
    from bute.storage import query_and_load, entry_path as _entry_path
    today = date.today()

    done = query_and_load(config, type="task", status="done")
    return [
        e for e in done
        if date.fromtimestamp(_entry_path(e, config).stat().st_mtime) == today
    ]
```

- [ ] **Step 6: Replace `get_tasks_dropped_today` (lines 155-167)**

```python
def get_tasks_dropped_today(config=None) -> list[Entry]:
    """Tasks marked dropped with file mtime today."""
    from bute.storage import query_and_load, entry_path as _entry_path
    today = date.today()

    dropped = query_and_load(config, type="task", status="dropped")
    return [
        e for e in dropped
        if date.fromtimestamp(_entry_path(e, config).stat().st_mtime) == today
    ]
```

- [ ] **Step 7: Replace `get_all_active_tasks` (lines 177-182)**

```python
def get_all_active_tasks(config=None) -> list[Entry]:
    """All active tasks across all dates."""
    from bute.storage import query_and_load
    return query_and_load(config, type="task", status="active")
```

- [ ] **Step 8: Replace `get_weekly_active_tasks` (lines 185-201)**

```python
def get_weekly_active_tasks(config=None) -> list[Entry]:
    """Active tasks selected for this week (@thisweek tag)."""
    from bute.storage import query_and_load
    weekly = query_and_load(config, type="task", status="active", tag="thisweek")
    if weekly:
        return weekly
    return get_all_active_tasks(config)
```

- [ ] **Step 9: Replace `clear_weekly_selection` (lines 272-281)**

```python
def clear_weekly_selection(config=None) -> int:
    """Remove +thisweek tag from all entries. Returns count cleared."""
    from bute.storage import query_and_load
    entries = query_and_load(config, tag="thisweek")
    for entry in entries:
        entry.tags.remove("thisweek")
        update_entry(entry, config)
    return len(entries)
```

- [ ] **Step 10: Replace `clear_daily_focus` (lines 284-293)**

```python
def clear_daily_focus(config=None) -> int:
    """Remove +today tag from all entries. Returns count cleared."""
    from bute.storage import query_and_load
    entries = query_and_load(config, tag="today")
    for entry in entries:
        entry.tags.remove("today")
        update_entry(entry, config)
    return len(entries)
```

- [ ] **Step 11: Update imports at top of `ritual_ops.py`**

Remove `load_entries_by_filter` from the top-level import:

```python
from bute.storage import (
    load_entries_by_date,
    save_entry,
    update_entry,
)
```

The `query_and_load` imports are done locally in each function to avoid circular imports.

- [ ] **Step 12: Run ritual_ops tests**

Run: `uv run pytest tests/test_ritual_ops.py tests/test_rituals.py -v`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
git add src/bute/ritual_ops.py
git commit -m "refactor: migrate ritual_ops.py from file-scan predicates to query_and_load"
```

---

### Task 10: Migrate `rituals.py`, `topic.py`, `nudges.py` Call Sites

**Files:**
- Modify: `src/bute/commands/rituals.py`
- Modify: `src/bute/commands/topic.py`
- Modify: `src/bute/commands/nudges.py`

- [ ] **Step 1: Migrate `_build_month_data` in `rituals.py` (line 271)**

Replace the `load_entries_by_filter` call for scheduled events:

```python
    from bute.storage import query_and_load

    # Calendar events scheduled in this month but created in a different month
    scheduled_events = query_and_load(config, type="calendar")
    scheduled_events = [
        e for e in scheduled_events
        if (
            e.scheduled_date is not None
            and e.scheduled_date.year == target.year
            and e.scheduled_date.month == target.month
            and e.created.strftime("%Y-%m") != target.strftime("%Y-%m")
        )
    ]
```

- [ ] **Step 2: Migrate `recap_cmd` in `rituals.py` (line 499)**

Replace the `load_entries_by_filter` call for open tasks:

```python
    from bute.storage import query_and_load

    open_tasks = query_and_load(config, type="task", status="active", tag="today")
```

- [ ] **Step 3: Migrate `review_cmd` in `rituals.py` (line 591)**

Replace the `load_entries_by_filter` call:

```python
    from bute.storage import query_and_load

    entries = query_and_load(config, created_since=start)
```

- [ ] **Step 4: Remove `load_entries_by_filter` import from `rituals.py`**

Remove it from the import at line 246 (`from bute.storage import load_entries_by_date, load_entries_by_filter`) — keep only `load_entries_by_date`. Also remove the import at line 493 and 581.

- [ ] **Step 5: Migrate `topic.py` (line 39)**

```python
    from bute.storage import query_and_load

    # Tag matches
    tag_entries = query_and_load(config, tag=topic_name.lower())
```

Note: the current code does case-insensitive tag matching (`topic_name.lower() in [t.lower() for t in e.tags]`). The DB stores tags as-is. For now, use exact match — tags are already lowercase by convention. If needed, a post-filter can handle case.

- [ ] **Step 6: Migrate `nudges.py` (line 28)**

```python
    from bute.storage import query_and_load
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=days)
    entries = query_and_load(config, created_since=cutoff)
```

- [ ] **Step 7: Run all affected tests**

Run: `uv run pytest tests/test_rituals.py tests/test_topic.py tests/test_nudges.py tests/test_linelog.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/bute/commands/rituals.py src/bute/commands/topic.py src/bute/commands/nudges.py
git commit -m "refactor: migrate rituals, topic, nudges from file-scan to query_and_load"
```

---

### Task 11: Migrate `vectors.py` to Shared Connection

**Files:**
- Modify: `src/bute/ai/vectors.py`
- Existing tests: `tests/test_vectors.py`

- [ ] **Step 1: Rewrite `vectors.py` to use `db.get_connection()`**

Replace the entire `src/bute/ai/vectors.py`:

```python
"""SQLite vector DB operations for bute using sqlite-vec."""

from __future__ import annotations

import logging
import struct

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
_vec_available: bool | None = None


def is_available() -> bool:
    """Check if sqlite-vec is installed. Cached after first call."""
    global _vec_available
    if _vec_available is None:
        try:
            import sqlite_vec  # noqa: F401
            _vec_available = True
        except ImportError:
            _vec_available = False
    return _vec_available


def _serialize_vector(vector: list[float]) -> bytes:
    """Convert float list to binary blob for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


def _get_connection(config=None):
    """Get shared DB connection from db.py."""
    from bute.db import get_connection
    return get_connection(config)


def upsert(entry_id: str, vector: list[float], config=None) -> None:
    """Insert or replace a vector for an entry."""
    db = _get_connection(config)
    blob = _serialize_vector(vector)
    db.execute("DELETE FROM vec_entries WHERE entry_id = ?", (entry_id,))
    db.execute(
        "INSERT INTO vec_entries (entry_id, embedding) VALUES (?, ?)",
        (entry_id, blob),
    )
    db.commit()


def delete(entry_id: str, config=None) -> None:
    """Remove a vector for an entry."""
    db = _get_connection(config)
    db.execute("DELETE FROM vec_entries WHERE entry_id = ?", (entry_id,))
    db.commit()


def search(
    query_vector: list[float], limit: int = 10, config=None
) -> list[tuple[str, float]]:
    """Find nearest entries by vector similarity."""
    db = _get_connection(config)
    blob = _serialize_vector(query_vector)
    rows = db.execute(
        """
        SELECT entry_id, distance
        FROM vec_entries
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?
        """,
        (blob, limit),
    ).fetchall()
    return [(row[0], row[1]) for row in rows]


def count(config=None) -> int:
    """Return the number of vectors in the store."""
    db = _get_connection(config)
    row = db.execute("SELECT COUNT(*) FROM vec_entries").fetchone()
    return row[0] if row else 0


def clear(config=None) -> None:
    """Delete all vectors (used before rebuild)."""
    db = _get_connection(config)
    db.execute("DELETE FROM vec_entries")
    db.commit()
```

- [ ] **Step 2: Update `tests/test_vectors.py` fixture**

Replace the `tmp_vecdb` fixture to use `db.py`:

```python
"""Tests for sqlite-vec vector store."""

import pytest

sqlite_vec = pytest.importorskip("sqlite_vec")

from bute.ai.vectors import clear, count, delete, search, upsert
from bute.db import close

DIM = 384


def _vec(val: float) -> list[float]:
    """Create a 384-dim vector filled with a single value."""
    return [val] * DIM


@pytest.fixture(autouse=True)
def tmp_vecdb(tmp_path, monkeypatch):
    """Set up and tear down a temp vector DB using db.py shared connection."""
    db_path = tmp_path / ".index" / "test.db"
    db_path.parent.mkdir(parents=True)
    monkeypatch.setattr("bute.db._db_path_override", db_path)
    yield
    close()
```

The test functions themselves stay exactly the same.

- [ ] **Step 3: Run vector tests**

Run: `uv run pytest tests/test_vectors.py -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -x -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/ai/vectors.py tests/test_vectors.py
git commit -m "refactor: migrate vectors.py to shared db.py connection"
```

---

### Task 12: Update `rebuild` Command and Add Progress Bar

**Files:**
- Modify: `src/bute/commands/search.py`
- Modify: `src/bute/db.py` (add `rebuild_from_files`)

- [ ] **Step 1: Add `rebuild_from_files` to `db.py`**

Add to `src/bute/db.py`:

```python
def rebuild_from_files(config=None, include_vectors: bool = False, show_progress: bool = True) -> int:
    """Rebuild the entire index from .md files.

    Returns the number of entries indexed.
    """
    from bute.config import get_data_dir
    from bute.storage import load_entry

    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"

    if not entries_dir.exists():
        return 0

    md_files = sorted(entries_dir.rglob("*.md"))
    if not md_files:
        return 0

    # Parse all entries first
    entries = []
    for path in md_files:
        try:
            entries.append(load_entry(path))
        except Exception:
            logger.debug("Skipped %s (parse error)", path.name, exc_info=True)

    # Clear existing index
    clear_all(config)

    if include_vectors:
        try:
            from bute.ai.vectors import clear as vec_clear
            vec_clear(config)
        except Exception:
            pass

    # Optional: embed texts in batch
    vectors = None
    if include_vectors:
        try:
            from bute.ai.embeddings import embed_texts, is_available
            if is_available():
                texts = [e.body for e in entries]
                vectors = embed_texts(texts)
        except Exception:
            pass

    # Index with progress bar
    if show_progress:
        from rich.console import Console
        from rich.progress import Progress

        console = Console()
        with Progress(console=console) as progress:
            task = progress.add_task("  Indexing entries...", total=len(entries))
            for i, entry in enumerate(entries):
                upsert_entry(entry, config)
                if include_vectors and vectors:
                    try:
                        from bute.ai.vectors import upsert as vec_upsert
                        vec_upsert(entry.id, vectors[i], config)
                    except Exception:
                        pass
                progress.advance(task)
    else:
        for i, entry in enumerate(entries):
            upsert_entry(entry, config)
            if include_vectors and vectors:
                try:
                    from bute.ai.vectors import upsert as vec_upsert
                    vec_upsert(entry.id, vectors[i], config)
                except Exception:
                    pass

    return len(entries)
```

- [ ] **Step 2: Rewrite `rebuild_cmd` in `search.py`**

Replace the `rebuild_cmd` in `src/bute/commands/search.py`:

```python
@click.command("rebuild")
@click.pass_context
def rebuild_cmd(ctx):
    """Rebuild the search index from Markdown files."""
    from bute.ai import is_embedding_available
    from bute.db import rebuild_from_files

    config = ctx.obj.get("config")
    include_vectors = is_embedding_available()

    console.print("  [dim]Your entries are safe — all data lives in your .md files.[/dim]")
    console.print("  [dim]Rebuilding search index...[/dim]")

    count = rebuild_from_files(config, include_vectors=include_vectors)

    if count == 0:
        console.print("  [dim]No entries found to index.[/dim]")
    else:
        vec_msg = f", {count} vectors embedded" if include_vectors else " (vectors skipped — embeddings not installed)"
        console.print(f"  [green]Rebuilt index: {count} entries indexed{vec_msg}.[/green]")
        console.print("  [dim]Your .md files are untouched — they're always the source of truth.[/dim]")
```

- [ ] **Step 3: Run rebuild test**

Run: `uv run pytest tests/test_search.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/bute/db.py src/bute/commands/search.py
git commit -m "feat: unified rebuild command with progress bar and user messaging"
```

---

### Task 13: Add Auto-Rebuild on Missing/Corrupt DB

**Files:**
- Modify: `src/bute/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write test for auto-rebuild on missing DB**

Add to `tests/test_db.py`:

```python
from bute.db import close, get_connection, count
from bute.models import Entry, EntryType
from bute.storage import save_entry


def test_auto_rebuild_on_query_after_db_deleted(tmp_data, tmp_path, monkeypatch):
    """If the DB is deleted, the next query should trigger a rebuild."""
    db_path = tmp_path / ".index" / "bute.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("bute.db._db_path_override", db_path)

    # Create entries (writes .md + DB)
    entry = Entry.create(EntryType.TASK, "test entry")
    save_entry(entry)
    assert count() == 1

    # Simulate DB loss
    close()
    db_path.unlink()

    # Next connection should trigger auto-rebuild
    from bute.db import count as db_count, get_connection
    get_connection()  # this should auto-rebuild

    # Entry should be back in the index (auto-rebuild reads .md files)
    assert db_count() == 1
```

- [ ] **Step 2: Add auto-rebuild logic to `get_connection`**

Modify `get_connection` in `src/bute/db.py`:

```python
def get_connection(config=None) -> sqlite3.Connection:
    """Get or create the shared DB connection. Auto-rebuilds if DB is new."""
    global _connection
    if _connection is not None:
        return _connection

    path = _db_path(config)
    is_new_db = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    _connection = db
    _load_vec_extension(db)
    ensure_schema(db)

    if is_new_db:
        _auto_rebuild(config)

    return db


def _auto_rebuild(config=None) -> None:
    """Rebuild index from .md files when DB is new or missing."""
    from bute.config import get_data_dir

    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return

    md_files = list(entries_dir.rglob("*.md"))
    if not md_files:
        return

    from rich.console import Console
    console = Console()
    console.print()
    console.print("  [dim]Your entries are safe — all data lives in your .md files.[/dim]")
    console.print("  [dim]Building search index for faster lookups...[/dim]")

    indexed = rebuild_from_files(config, include_vectors=False, show_progress=True)

    if indexed > 0:
        console.print(f"  [green]Index built. {indexed} entries indexed.[/green]")
        console.print("  [dim]Tip: You can export your entries anytime with[/dim] [bold]bt export[/bold][dim].[/dim]")
    console.print()
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/bute/db.py tests/test_db.py
git commit -m "feat: auto-rebuild index when DB is missing, with progress bar and user messaging"
```

---

### Task 14: DB Location Migration (`.vectors/` → `.index/`)

**Files:**
- Modify: `src/bute/db.py`
- Modify: `src/bute/config.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write migration test**

Add to `tests/test_db.py`:

```python
import shutil

from bute.db import _migrate_from_vectors, close


def test_migrate_from_vectors(tmp_path, monkeypatch):
    """Old .vectors/bute.db should be moved to .index/bute.db."""
    old_dir = tmp_path / "data" / ".vectors"
    old_dir.mkdir(parents=True)
    old_db = old_dir / "bute.db"
    old_db.write_text("fake db")  # just needs to exist

    new_dir = tmp_path / "data" / ".index"
    monkeypatch.setattr("bute.db._db_path_override", None)  # use real path logic
    monkeypatch.setattr("bute.config.DATA_DIR_DEFAULT", tmp_path / "data")

    _migrate_from_vectors(config=None)

    assert (new_dir / "bute.db").exists()
    assert not old_db.exists()


def test_migrate_skips_if_index_exists(tmp_path, monkeypatch):
    """If .index/bute.db already exists, don't migrate."""
    old_dir = tmp_path / "data" / ".vectors"
    old_dir.mkdir(parents=True)
    (old_dir / "bute.db").write_text("old")

    new_dir = tmp_path / "data" / ".index"
    new_dir.mkdir(parents=True)
    (new_dir / "bute.db").write_text("new")

    monkeypatch.setattr("bute.db._db_path_override", None)
    monkeypatch.setattr("bute.config.DATA_DIR_DEFAULT", tmp_path / "data")

    _migrate_from_vectors(config=None)

    assert (new_dir / "bute.db").read_text() == "new"  # unchanged
```

- [ ] **Step 2: Implement migration function**

Add to `src/bute/db.py`:

```python
import shutil


def _migrate_from_vectors(config=None) -> None:
    """Move .vectors/bute.db to .index/bute.db if needed."""
    data_dir = get_data_dir(config)
    old_path = data_dir / ".vectors" / "bute.db"
    new_dir = data_dir / ".index"
    new_path = new_dir / "bute.db"

    if new_path.exists() or not old_path.exists():
        return

    new_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old_path), str(new_path))

    # Clean up empty .vectors dir
    old_dir = data_dir / ".vectors"
    if old_dir.exists() and not any(old_dir.iterdir()):
        old_dir.rmdir()

    logger.info("Migrated vector DB from .vectors/ to .index/")
```

- [ ] **Step 3: Call migration from `get_connection` before opening DB**

Update `get_connection` — add `_migrate_from_vectors(config)` before checking if the DB exists:

```python
def get_connection(config=None) -> sqlite3.Connection:
    global _connection
    if _connection is not None:
        return _connection

    if _db_path_override is None:
        _migrate_from_vectors(config)

    path = _db_path(config)
    is_new_db = not path.exists()
    # ... rest unchanged
```

- [ ] **Step 4: Update `ensure_data_dirs` in `config.py`**

Change `.vectors` to `.index` in the directory creation:

```python
def ensure_data_dirs(config: tomlkit.TOMLDocument | None = None) -> Path:
    """Create the data directory structure. Returns the data dir path."""
    data_dir = get_data_dir(config)
    for subdir in ["entries", "collections", "habits", ".index"]:
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)
    return data_dir
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_db.py tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -x -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/bute/db.py src/bute/config.py tests/test_db.py
git commit -m "feat: migrate DB location from .vectors/ to .index/, auto-migration on upgrade"
```

---

### Task 15: Final Integration Test and Cleanup

**Files:**
- All modified files
- Existing tests

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: ALL PASS

- [ ] **Step 2: Verify no remaining references to old `load_entries_by_filter` pattern**

Check that `load_entries_by_filter` is no longer imported in the migrated files:

Run: `grep -rn "from bute.storage import.*load_entries_by_filter" src/bute/commands/ src/bute/ritual_ops.py`

Expected: No matches (the function still exists in `storage.py` as the fallback, but should not be imported anywhere except `storage.py` itself).

- [ ] **Step 3: Test CLI manually**

Run these commands to verify the full pipeline works:

```bash
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall
bt t test sqlite index @testing
bt t
bt n this is a note
bt n
bt @testing
bt 1 done
bt rebuild
```

- [ ] **Step 4: Verify DB was created**

```bash
ls -la ~/bullet-terminal/.index/
# Should show bute.db
```

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final integration cleanup for SQLite index"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Schema + connection management | `db.py`, `test_db.py` |
| 2 | `upsert_entry`, `delete_entry` | `db.py`, `test_db.py` |
| 3 | `query_entries` with keyword args | `db.py`, `test_db.py` |
| 4 | `search_text`, `clear_all`, `count` | `db.py`, `test_db.py` |
| 5 | Write-through in `storage.py` | `storage.py`, `test_storage.py` |
| 6 | Delete wire-up in `action.py` | `action.py`, `test_action.py` |
| 7 | `query_and_load` helper | `storage.py`, `test_storage_queries.py` |
| 8 | Migrate `views.py` (5 call sites) | `views.py` |
| 9 | Migrate `ritual_ops.py` (8 call sites) | `ritual_ops.py` |
| 10 | Migrate `rituals.py`, `topic.py`, `nudges.py` (5 call sites) | 3 files |
| 11 | Migrate `vectors.py` to shared connection | `vectors.py`, `test_vectors.py` |
| 12 | Rebuild command + progress bar | `search.py`, `db.py` |
| 13 | Auto-rebuild on missing DB | `db.py`, `test_db.py` |
| 14 | DB location migration | `db.py`, `config.py`, `test_db.py` |
| 15 | Integration test + cleanup | All |
