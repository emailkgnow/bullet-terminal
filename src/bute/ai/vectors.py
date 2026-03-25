"""SQLite vector DB operations for bute using sqlite-vec."""

from __future__ import annotations

import logging
import sqlite3
import struct
from pathlib import Path

from bute.config import get_data_dir

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
_connection: sqlite3.Connection | None = None
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


def _db_path(config=None) -> Path:
    """Return ~/bute/.vectors/bute.db"""
    data_dir = get_data_dir(config)
    vec_dir = data_dir / ".vectors"
    vec_dir.mkdir(parents=True, exist_ok=True)
    return vec_dir / "bute.db"


def _serialize_vector(vector: list[float]) -> bytes:
    """Convert float list to binary blob for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


def connect(db_path: Path | None = None, config=None) -> None:
    """Open a connection with sqlite-vec loaded. Used by tests for path override."""
    global _connection
    close()

    import sqlite_vec

    path = db_path or _db_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(str(path))
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)

    db.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
            entry_id TEXT PRIMARY KEY,
            embedding float[{EMBEDDING_DIM}]
        )
        """
    )
    db.commit()
    _connection = db


def _get_connection(config=None) -> sqlite3.Connection:
    """Get or create a connection."""
    global _connection
    if _connection is None:
        connect(config=config)
    return _connection


def upsert(entry_id: str, vector: list[float], config=None) -> None:
    """Insert or replace a vector for an entry."""
    db = _get_connection(config)
    blob = _serialize_vector(vector)
    # vec0 doesn't support INSERT OR REPLACE, so delete first
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
    """Find nearest entries by vector similarity.

    Returns list of (entry_id, distance) tuples, sorted by distance ascending.
    """
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


def close() -> None:
    """Close the database connection."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
