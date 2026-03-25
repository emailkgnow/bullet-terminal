"""Tests for sqlite-vec vector store."""

import pytest

sqlite_vec = pytest.importorskip("sqlite_vec")

from bute.ai.vectors import clear, close, connect, count, delete, search, upsert

DIM = 384


def _vec(val: float) -> list[float]:
    """Create a 384-dim vector filled with a single value."""
    return [val] * DIM


@pytest.fixture(autouse=True)
def tmp_vecdb(tmp_path):
    """Set up and tear down a temp vector DB for each test."""
    db_path = tmp_path / ".vectors" / "test.db"
    connect(db_path=db_path)
    yield
    close()


def test_upsert_and_search():
    upsert("entry1", _vec(1.0))
    results = search(_vec(1.0), limit=5)
    assert len(results) >= 1
    assert results[0][0] == "entry1"
    assert results[0][1] < 0.01  # near-zero distance


def test_upsert_replace():
    upsert("entry1", _vec(1.0))
    upsert("entry1", _vec(2.0))
    assert count() == 1


def test_search_ordering():
    upsert("close", _vec(1.0))
    upsert("far", _vec(100.0))
    results = search(_vec(1.1), limit=2)
    assert results[0][0] == "close"
    assert results[1][0] == "far"


def test_delete():
    upsert("entry1", _vec(1.0))
    assert count() == 1
    delete("entry1")
    assert count() == 0


def test_clear():
    upsert("a", _vec(1.0))
    upsert("b", _vec(2.0))
    assert count() == 2
    clear()
    assert count() == 0


def test_count_empty():
    assert count() == 0
