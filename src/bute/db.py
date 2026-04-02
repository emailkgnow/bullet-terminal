"""SQLite structured index for bute entries.

Provides fast queries on type, status, tags, dates — complementing the
Markdown file store. Independent of storage.py; does not read .md files.
"""

from __future__ import annotations

import json
import logging
import shutil
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
    if _connection is not None:
        return _connection

    if _db_path_override is None:
        _migrate_from_vectors(config)

    path = _db_path(config)
    is_new_db = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    _load_vec_extension(db)
    ensure_schema(db)
    _connection = db

    if is_new_db and _db_path_override is None:
        _auto_rebuild(config)

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

        CREATE TABLE IF NOT EXISTS tag_stages (
            tag         TEXT PRIMARY KEY,
            stage       TEXT NOT NULL DEFAULT 'raw',
            analysis    TEXT,
            tasks_text  TEXT,
            analyzed_at TEXT,
            executed_at TEXT
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

    old_dir = data_dir / ".vectors"
    if old_dir.exists() and not any(old_dir.iterdir()):
        old_dir.rmdir()

    logger.info("Migrated vector DB from .vectors/ to .index/")


def _auto_rebuild(config=None) -> None:
    """Rebuild index from .md files when DB is new."""
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


def rebuild_from_files(config=None, include_vectors: bool = False, show_progress: bool = True) -> int:
    """Rebuild the entire index from .md files. Returns count indexed."""
    from bute.storage import load_entry

    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"

    if not entries_dir.exists():
        return 0

    md_files = sorted(entries_dir.rglob("*.md"))
    if not md_files:
        return 0

    entries = []
    for path in md_files:
        try:
            entries.append(load_entry(path))
        except Exception:
            logger.debug("Skipped %s (parse error)", path.name, exc_info=True)

    clear_all(config)

    if include_vectors:
        try:
            from bute.ai.vectors import clear as vec_clear
            vec_clear(config)
        except Exception:
            pass

    vectors = None
    if include_vectors:
        try:
            from bute.ai.embeddings import embed_texts, is_available
            if is_available():
                vectors = embed_texts([e.body for e in entries])
        except Exception:
            pass

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
        conditions.append("(status IS NULL OR status != ?)")
        params.append(exclude_status)

    if important is not None:
        conditions.append("important = ?")
        params.append(1 if important else 0)

    if created_date is not None:
        conditions.append("date(created) = ?")
        params.append(created_date)

    if created_since is not None:
        conditions.append("date(created) >= ?")
        params.append(created_since)

    if created_until is not None:
        conditions.append("date(created) <= ?")
        params.append(created_until)

    if scheduled_date is not None:
        conditions.append("scheduled_date = ?")
        params.append(scheduled_date)

    if due_on is not None:
        conditions.append("due = ?")
        params.append(due_on)

    if due_before is not None:
        conditions.append("due <= ?")
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


# ---------------------------------------------------------------------------
# Tag stage operations
# ---------------------------------------------------------------------------

def upsert_tag_stage(
    tag: str,
    stage: str,
    *,
    analysis: str | None = None,
    tasks_text: str | None = None,
    config=None,
) -> None:
    """Insert or update a tag's processing stage."""
    from datetime import datetime, timezone

    db = get_connection(config)
    now = datetime.now(timezone.utc).astimezone().isoformat()

    existing = get_tag_stage(tag, config)
    if existing is None:
        db.execute(
            """INSERT INTO tag_stages (tag, stage, analysis, tasks_text, analyzed_at, executed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                tag,
                stage,
                analysis,
                tasks_text,
                now if stage in ("analyzed", "executed") else None,
                now if stage == "executed" else None,
            ),
        )
    else:
        updates = ["stage = ?"]
        params: list = [stage]
        if analysis is not None:
            updates.append("analysis = ?")
            params.append(analysis)
        if tasks_text is not None:
            updates.append("tasks_text = ?")
            params.append(tasks_text)
        if stage in ("analyzed", "executed"):
            updates.append("analyzed_at = ?")
            params.append(existing["analyzed_at"] or now)
        if stage == "executed":
            updates.append("executed_at = ?")
            params.append(now)
        if stage == "analyzed":
            updates.append("executed_at = ?")
            params.append(None)
            updates.append("tasks_text = ?")
            params.append(None)
            updates.append("analyzed_at = ?")
            params.append(now)
        params.append(tag)
        db.execute(f"UPDATE tag_stages SET {', '.join(updates)} WHERE tag = ?", params)
    db.commit()


def get_tag_stage(tag: str, config=None) -> dict | None:
    """Get a tag's processing stage. Returns dict or None."""
    db = get_connection(config)
    row = db.execute(
        "SELECT tag, stage, analysis, tasks_text, analyzed_at, executed_at FROM tag_stages WHERE tag = ?",
        (tag,),
    ).fetchone()
    if row is None:
        return None
    return {
        "tag": row[0],
        "stage": row[1],
        "analysis": row[2],
        "tasks_text": row[3],
        "analyzed_at": row[4],
        "executed_at": row[5],
    }


def get_all_tag_stages(config=None) -> list[dict]:
    """Get all tag stage rows."""
    db = get_connection(config)
    rows = db.execute(
        "SELECT tag, stage, analysis, tasks_text, analyzed_at, executed_at FROM tag_stages ORDER BY tag"
    ).fetchall()
    return [
        {
            "tag": r[0],
            "stage": r[1],
            "analysis": r[2],
            "tasks_text": r[3],
            "analyzed_at": r[4],
            "executed_at": r[5],
        }
        for r in rows
    ]


def count(config=None) -> int:
    """Return the total number of entries in the index."""
    db = get_connection(config)
    row = db.execute("SELECT COUNT(*) FROM entries").fetchone()
    return row[0] if row else 0
