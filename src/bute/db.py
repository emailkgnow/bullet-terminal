"""SQLite structured index for bute entries.

Provides fast queries on type, status, tags, dates — complementing the
Markdown file store. Independent of storage.py; does not read .md files.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from bute.config import get_data_dir
from bute.models import Entry

logger = logging.getLogger(__name__)

# Module-level globals
_connection: sqlite3.Connection | None = None
_db_path_override: Optional[Path] = None  # Set by tests via monkeypatch


# ---------------------------------------------------------------------------
# Path / connection management
# ---------------------------------------------------------------------------

def _db_path(config=None) -> Path:
    """Return path to the SQLite index file: ~/bute/.index/bute.db"""
    if _db_path_override is not None:
        return _db_path_override
    data_dir = get_data_dir(config)
    index_dir = data_dir / ".index"
    index_dir.mkdir(parents=True, exist_ok=True)
    return index_dir / "bute.db"


def get_connection(config=None) -> sqlite3.Connection:
    """Return the singleton connection, creating schema on first call."""
    global _connection
    if _connection is None:
        path = _db_path(config)
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(path))
        db.row_factory = sqlite3.Row
        _load_vec_extension(db)
        ensure_schema(db)
        _connection = db
    return _connection


def _load_vec_extension(db: sqlite3.Connection) -> None:
    """Try to load sqlite-vec. No-op if not installed."""
    try:
        import sqlite_vec  # type: ignore
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
        logger.debug("sqlite-vec loaded")
    except (ImportError, Exception) as exc:
        logger.debug("sqlite-vec not available: %s", exc)


def ensure_schema(db: sqlite3.Connection) -> None:
    """Create all tables and indexes. Idempotent (IF NOT EXISTS)."""
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
        CREATE INDEX IF NOT EXISTS idx_created     ON entries(created);
        CREATE INDEX IF NOT EXISTS idx_due         ON entries(due);
        CREATE INDEX IF NOT EXISTS idx_scheduled_date ON entries(scheduled_date);

        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
            entry_id UNINDEXED,
            body
        );
    """)
    # vec0 is optional — only create if sqlite-vec is loaded
    try:
        db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
                entry_id TEXT PRIMARY KEY,
                embedding float[384]
            )
        """)
    except sqlite3.OperationalError:
        # sqlite-vec not available; skip silently
        pass
    db.commit()


def close() -> None:
    """Close the connection and reset the singleton."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def upsert_entry(entry: Entry, config=None) -> None:
    """Insert or replace an entry in the index (entries + FTS)."""
    db = get_connection(config)

    tags_json = json.dumps(entry.tags) if entry.tags else "[]"
    extra_json = json.dumps(entry.extra_meta) if entry.extra_meta else None
    due_str = entry.due.isoformat() if entry.due else None
    sched_date_str = entry.scheduled_date.isoformat() if entry.scheduled_date else None
    created_str = entry.created.isoformat()

    # FTS content-table sync: delete old FTS row before replacing in base table
    db.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry.id,))

    db.execute(
        """
        INSERT OR REPLACE INTO entries
            (entry_id, type, status, body, important, due,
             scheduled_date, scheduled_time, repeat, tags, created, extra_meta)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.id,
            entry.type.value,
            entry.status.value if entry.status else None,
            entry.body,
            1 if entry.important else 0,
            due_str,
            sched_date_str,
            entry.scheduled_time,
            entry.repeat,
            tags_json,
            created_str,
            extra_json,
        ),
    )

    # Insert new FTS row
    db.execute(
        "INSERT INTO entries_fts (entry_id, body) VALUES (?, ?)",
        (entry.id, entry.body),
    )
    db.commit()


def delete_entry(entry_id: str, config=None) -> None:
    """Remove an entry from the index (entries + FTS)."""
    db = get_connection(config)
    db.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry_id,))
    db.execute("DELETE FROM entries WHERE entry_id = ?", (entry_id,))
    db.commit()


# ---------------------------------------------------------------------------
# Query operations
# ---------------------------------------------------------------------------

def query_entries(
    config=None,
    *,
    type: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    tags: list[str] | None = None,
    created_date: str | None = None,
    scheduled_date: str | None = None,
    due_before: str | None = None,
    due_on: str | None = None,
    has_due: bool = False,
    has_tags: bool = False,
    exclude_status: str | None = None,
    important: bool | None = None,
    created_since: str | None = None,
    created_until: str | None = None,
) -> list[tuple[str, str]]:
    """Query the index, returning (entry_id, created) tuples ordered by created DESC.

    All conditions are AND'd together.
    """
    db = get_connection(config)

    conditions: list[str] = []
    params: list = []

    if type is not None:
        conditions.append("type = ?")
        params.append(type)

    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    if exclude_status is not None:
        conditions.append("status != ?")
        params.append(exclude_status)

    if important is not None:
        conditions.append("important = ?")
        params.append(1 if important else 0)

    if created_date is not None:
        conditions.append("date(created) = ?")
        params.append(created_date)

    if created_since is not None:
        conditions.append("created >= ?")
        params.append(created_since)

    if created_until is not None:
        conditions.append("created <= ?")
        params.append(created_until)

    if scheduled_date is not None:
        conditions.append("scheduled_date = ?")
        params.append(scheduled_date)

    if due_on is not None:
        conditions.append("due = ?")
        params.append(due_on)

    if due_before is not None:
        conditions.append("due < ?")
        params.append(due_before)

    if has_due:
        conditions.append("due IS NOT NULL")

    if has_tags:
        conditions.append("tags != '[]'")

    # Single tag filter
    if tag is not None:
        conditions.append(
            "entry_id IN ("
            "  SELECT e.entry_id FROM entries e, json_each(e.tags) j"
            "  WHERE j.value = ?"
            ")"
        )
        params.append(tag)

    # Multiple tags — each must match
    if tags:
        for t in tags:
            conditions.append(
                "entry_id IN ("
                "  SELECT e.entry_id FROM entries e, json_each(e.tags) j"
                "  WHERE j.value = ?"
                ")"
            )
            params.append(t)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"SELECT entry_id, created FROM entries {where_clause} ORDER BY created DESC"

    rows = db.execute(sql, params).fetchall()
    return [(row[0], row[1]) for row in rows]


# ---------------------------------------------------------------------------
# Text search and bulk operations
# ---------------------------------------------------------------------------

def search_text(
    query: str,
    type: str | None = None,
    limit: int = 50,
    config=None,
) -> list[tuple[str, str]]:
    """Full-text search on entry bodies using FTS5.

    Returns (entry_id, created) tuples. Optional type filter.
    """
    db = get_connection(config)

    if type is not None:
        sql = """
            SELECT f.entry_id, e.created
            FROM entries_fts f
            JOIN entries e ON e.entry_id = f.entry_id
            WHERE entries_fts MATCH ?
              AND e.type = ?
            ORDER BY e.created DESC
            LIMIT ?
        """
        rows = db.execute(sql, (query, type, limit)).fetchall()
    else:
        sql = """
            SELECT f.entry_id, e.created
            FROM entries_fts f
            JOIN entries e ON e.entry_id = f.entry_id
            WHERE entries_fts MATCH ?
            ORDER BY e.created DESC
            LIMIT ?
        """
        rows = db.execute(sql, (query, limit)).fetchall()

    return [(row[0], row[1]) for row in rows]


def clear_all(config=None) -> None:
    """Delete all entries from the index (entries_fts then entries)."""
    db = get_connection(config)
    db.execute("DELETE FROM entries_fts")
    db.execute("DELETE FROM entries")
    db.commit()


def count(config=None) -> int:
    """Return the total number of entries in the index."""
    db = get_connection(config)
    row = db.execute("SELECT COUNT(*) FROM entries").fetchone()
    return row[0] if row else 0
