"""SQLite vector DB operations for bt using sqlite-vec."""

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
    return struct.pack(f"{len(vector)}f", *vector)


def _get_connection(config=None):
    from bute.db import get_connection
    return get_connection(config)


def upsert(entry_id: str, vector: list[float], config=None) -> None:
    db = _get_connection(config)
    blob = _serialize_vector(vector)
    db.execute("DELETE FROM vec_entries WHERE entry_id = ?", (entry_id,))
    db.execute(
        "INSERT INTO vec_entries (entry_id, embedding) VALUES (?, ?)",
        (entry_id, blob),
    )
    db.commit()


def delete(entry_id: str, config=None) -> None:
    db = _get_connection(config)
    db.execute("DELETE FROM vec_entries WHERE entry_id = ?", (entry_id,))
    db.commit()


def search(query_vector: list[float], limit: int = 10, config=None) -> list[tuple[str, float]]:
    db = _get_connection(config)
    blob = _serialize_vector(query_vector)
    rows = db.execute(
        "SELECT entry_id, distance FROM vec_entries WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (blob, limit),
    ).fetchall()
    return [(row[0], row[1]) for row in rows]


def count(config=None) -> int:
    db = _get_connection(config)
    row = db.execute("SELECT COUNT(*) FROM vec_entries").fetchone()
    return row[0] if row else 0


def clear(config=None) -> None:
    db = _get_connection(config)
    db.execute("DELETE FROM vec_entries")
    db.commit()
