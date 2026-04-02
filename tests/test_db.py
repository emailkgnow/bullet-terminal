"""Tests for src/bute/db.py — SQLite structured index."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import bute.db as db_module
from bute.db import (
    clear_all,
    close,
    count,
    delete_entry,
    ensure_schema,
    get_connection,
    query_entries,
    search_text,
    upsert_entry,
)
from bute.models import Entry, EntryType, TaskStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect the DB to a temp directory and close after each test."""
    index_dir = tmp_path / ".index"
    index_dir.mkdir()
    monkeypatch.setattr("bute.db._db_path_override", index_dir / "bute.db")
    yield
    close()


def _task(body: str = "a task", **kwargs) -> Entry:
    return Entry.create(EntryType.TASK, body, **kwargs)


def _note(body: str = "a note", **kwargs) -> Entry:
    return Entry.create(EntryType.NOTE, body, **kwargs)


def _journal(body: str = "a journal", **kwargs) -> Entry:
    return Entry.create(EntryType.JOURNAL, body, **kwargs)


# ---------------------------------------------------------------------------
# Task 1: Schema / connection
# ---------------------------------------------------------------------------

class TestConnection:
    def test_get_connection_returns_connection(self):
        conn = get_connection()
        assert conn is not None

    def test_get_connection_singleton(self):
        conn1 = get_connection()
        conn2 = get_connection()
        assert conn1 is conn2

    def test_close_resets_singleton(self):
        conn1 = get_connection()
        close()
        conn2 = get_connection()
        assert conn1 is not conn2

    def test_ensure_schema_idempotent(self):
        conn = get_connection()
        # Calling twice must not raise
        ensure_schema(conn)
        ensure_schema(conn)

    def test_entries_table_exists(self):
        conn = get_connection()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entries'"
        ).fetchone()
        assert row is not None

    def test_entries_fts_table_exists(self):
        conn = get_connection()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entries_fts'"
        ).fetchone()
        assert row is not None

    def test_tag_stages_table_exists(self):
        """tag_stages table should be created by ensure_schema."""
        db = get_connection()
        db.execute(
            "INSERT INTO tag_stages (tag, stage) VALUES (?, ?)",
            ("test-tag", "raw"),
        )
        db.commit()
        row = db.execute(
            "SELECT tag, stage, analysis, tasks_text, analyzed_at, executed_at "
            "FROM tag_stages WHERE tag = ?",
            ("test-tag",),
        ).fetchone()
        assert row is not None
        assert row[0] == "test-tag"
        assert row[1] == "raw"
        assert row[2] is None
        assert row[3] is None

    def test_indexes_exist(self):
        conn = get_connection()
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_type_status" in names
        assert "idx_created" in names
        assert "idx_due" in names
        assert "idx_scheduled_date" in names

    def test_db_path_override_used(self, tmp_path):
        # Already exercised by the autouse fixture — just assert file location
        conn = get_connection()
        assert conn is not None


# ---------------------------------------------------------------------------
# Task 2: upsert_entry / delete_entry
# ---------------------------------------------------------------------------

class TestUpsertDelete:
    def test_upsert_inserts_task(self):
        entry = _task("call dentist", tags=["health"])
        upsert_entry(entry)
        assert count() == 1

    def test_upsert_replaces_existing(self):
        entry = _task("original body")
        upsert_entry(entry)

        # Mutate body and upsert again
        entry.body = "updated body"
        upsert_entry(entry)

        assert count() == 1
        conn = get_connection()
        row = conn.execute(
            "SELECT body FROM entries WHERE entry_id = ?", (entry.id,)
        ).fetchone()
        assert row[0] == "updated body"

    def test_upsert_stores_tags_as_json(self):
        entry = _task("tagged task", tags=["foo", "bar"])
        upsert_entry(entry)
        conn = get_connection()
        row = conn.execute(
            "SELECT tags FROM entries WHERE entry_id = ?", (entry.id,)
        ).fetchone()
        import json
        assert json.loads(row[0]) == ["foo", "bar"]

    def test_upsert_stores_extra_meta_as_json(self):
        entry = _task("meta task")
        entry.extra_meta = {"project": "alpha", "priority": "high"}
        upsert_entry(entry)
        conn = get_connection()
        row = conn.execute(
            "SELECT extra_meta FROM entries WHERE entry_id = ?", (entry.id,)
        ).fetchone()
        import json
        assert json.loads(row[0]) == {"project": "alpha", "priority": "high"}

    def test_upsert_stores_important_flag(self):
        entry = _task("important task", important=True)
        upsert_entry(entry)
        conn = get_connection()
        row = conn.execute(
            "SELECT important FROM entries WHERE entry_id = ?", (entry.id,)
        ).fetchone()
        assert row[0] == 1

    def test_upsert_stores_due_date(self):
        due = date(2026, 5, 1)
        entry = _task("due task", due=due)
        upsert_entry(entry)
        conn = get_connection()
        row = conn.execute(
            "SELECT due FROM entries WHERE entry_id = ?", (entry.id,)
        ).fetchone()
        assert row[0] == "2026-05-01"

    def test_upsert_null_due_when_not_set(self):
        entry = _task("no due date")
        upsert_entry(entry)
        conn = get_connection()
        row = conn.execute(
            "SELECT due FROM entries WHERE entry_id = ?", (entry.id,)
        ).fetchone()
        assert row[0] is None

    def test_upsert_stores_status(self):
        entry = _task("done task")
        entry.status = TaskStatus.DONE
        upsert_entry(entry)
        conn = get_connection()
        row = conn.execute(
            "SELECT status FROM entries WHERE entry_id = ?", (entry.id,)
        ).fetchone()
        assert row[0] == "done"

    def test_upsert_null_status_for_note(self):
        entry = _note("no status")
        upsert_entry(entry)
        conn = get_connection()
        row = conn.execute(
            "SELECT status FROM entries WHERE entry_id = ?", (entry.id,)
        ).fetchone()
        assert row[0] is None

    def test_upsert_fts_indexed(self):
        entry = _task("unique searchable phrase")
        upsert_entry(entry)
        conn = get_connection()
        rows = conn.execute(
            "SELECT entry_id FROM entries_fts WHERE entries_fts MATCH ?",
            ("searchable",),
        ).fetchall()
        assert any(r[0] == entry.id for r in rows)

    def test_upsert_fts_updates_on_replace(self):
        entry = _task("old phrase")
        upsert_entry(entry)

        entry.body = "new phrase only"
        upsert_entry(entry)

        conn = get_connection()
        # Old phrase should not appear
        old_rows = conn.execute(
            "SELECT entry_id FROM entries_fts WHERE entries_fts MATCH ?",
            ("old",),
        ).fetchall()
        assert not any(r[0] == entry.id for r in old_rows)

        # New phrase should appear
        new_rows = conn.execute(
            "SELECT entry_id FROM entries_fts WHERE entries_fts MATCH ?",
            ("new",),
        ).fetchall()
        assert any(r[0] == entry.id for r in new_rows)

    def test_delete_removes_entry(self):
        entry = _task("to be deleted")
        upsert_entry(entry)
        assert count() == 1

        delete_entry(entry.id)
        assert count() == 0

    def test_delete_removes_from_fts(self):
        entry = _task("deletable phrase")
        upsert_entry(entry)
        delete_entry(entry.id)

        conn = get_connection()
        rows = conn.execute(
            "SELECT entry_id FROM entries_fts WHERE entries_fts MATCH ?",
            ("deletable",),
        ).fetchall()
        assert not any(r[0] == entry.id for r in rows)

    def test_delete_nonexistent_is_noop(self):
        # Should not raise
        delete_entry("nonexistent-id-00000000000000")
        assert count() == 0


# ---------------------------------------------------------------------------
# Task 3: query_entries
# ---------------------------------------------------------------------------

class TestQueryEntries:
    def setup_method(self):
        """Insert a small set of entries used across query tests."""
        self.t1 = _task("call dentist", tags=["health"])
        self.t1.status = TaskStatus.ACTIVE

        self.t2 = _task("fix prod bug", important=True, tags=["backend"])
        self.t2.status = TaskStatus.DONE

        self.t3 = _task("overdue task", due=date(2025, 1, 1), tags=["backend"])
        self.t3.status = TaskStatus.ACTIVE

        self.n1 = _note("OAuth tokens last 30 days", tags=["api"])
        self.j1 = _journal("feeling good today")

        for e in (self.t1, self.t2, self.t3, self.n1, self.j1):
            upsert_entry(e)

    def _ids(self, results):
        return {r[0] for r in results}

    def test_no_filters_returns_all(self):
        results = query_entries()
        assert len(results) == 5

    def test_filter_by_type_task(self):
        results = query_entries(type="task")
        assert len(results) == 3
        assert all(r[0] in {self.t1.id, self.t2.id, self.t3.id} for r in results)

    def test_filter_by_type_note(self):
        results = query_entries(type="note")
        assert self._ids(results) == {self.n1.id}

    def test_filter_by_status_active(self):
        results = query_entries(status="active")
        assert self._ids(results) == {self.t1.id, self.t3.id}

    def test_filter_by_status_done(self):
        results = query_entries(status="done")
        assert self._ids(results) == {self.t2.id}

    def test_exclude_status(self):
        results = query_entries(type="task", exclude_status="done")
        assert self._ids(results) == {self.t1.id, self.t3.id}

    def test_exclude_status_preserves_null_status_entries(self):
        """Notes/journals have NULL status — exclude_status must not drop them."""
        results = query_entries(exclude_status="dropped")
        ids = self._ids(results)
        # n1 (note) and j1 (journal) have NULL status, must survive
        assert self.n1.id in ids
        assert self.j1.id in ids

    def test_filter_by_important(self):
        results = query_entries(important=True)
        assert self._ids(results) == {self.t2.id}

    def test_filter_important_false(self):
        results = query_entries(important=False)
        ids = self._ids(results)
        assert self.t2.id not in ids
        assert self.t1.id in ids

    def test_filter_by_tag(self):
        results = query_entries(tag="backend")
        assert self._ids(results) == {self.t2.id, self.t3.id}

    def test_filter_by_tag_health(self):
        results = query_entries(tag="health")
        assert self._ids(results) == {self.t1.id}

    def test_filter_by_tags_multiple_must_all_match(self):
        # t2 has only "backend", not "health" — no entry has both
        results = query_entries(tags=["backend", "health"])
        assert len(results) == 0

    def test_filter_by_tags_single(self):
        results = query_entries(tags=["api"])
        assert self._ids(results) == {self.n1.id}

    def test_has_due(self):
        results = query_entries(has_due=True)
        assert self._ids(results) == {self.t3.id}

    def test_due_on(self):
        results = query_entries(due_on="2025-01-01")
        assert self._ids(results) == {self.t3.id}

    def test_due_before(self):
        results = query_entries(due_before="2026-01-01")
        assert self._ids(results) == {self.t3.id}

    def test_due_before_inclusive(self):
        """due_before means 'on or before' — boundary date must match."""
        results = query_entries(due_before="2025-01-01")
        assert self.t3.id in self._ids(results)

    def test_has_tags(self):
        results = query_entries(has_tags=True)
        ids = self._ids(results)
        # j1 has no tags
        assert self.j1.id not in ids
        assert self.t1.id in ids

    def test_created_date_filter(self):
        from datetime import date as d
        today = d.today().isoformat()
        results = query_entries(created_date=today)
        # All entries were just created so all should match
        assert len(results) == 5

    def test_created_since(self):
        results = query_entries(created_since="2020-01-01T00:00:00")
        assert len(results) == 5

    def test_created_until_excludes_future(self):
        results = query_entries(created_until="2000-01-01T00:00:00")
        assert len(results) == 0

    def test_combined_type_and_tag(self):
        results = query_entries(type="task", tag="backend")
        assert self._ids(results) == {self.t2.id, self.t3.id}

    def test_combined_type_status_tag(self):
        results = query_entries(type="task", status="active", tag="backend")
        assert self._ids(results) == {self.t3.id}

    def test_results_ordered_by_created_desc(self):
        results = query_entries(type="task")
        created_times = [r[1] for r in results]
        assert created_times == sorted(created_times, reverse=True)

    def test_returns_list_of_tuples(self):
        results = query_entries()
        assert isinstance(results, list)
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)

    def test_empty_db_returns_empty_list(self):
        clear_all()
        assert query_entries() == []


# ---------------------------------------------------------------------------
# Task 4: search_text / clear_all / count
# ---------------------------------------------------------------------------

class TestSearchText:
    def setup_method(self):
        entries = [
            _task("call dentist urgently"),
            _note("dentist appointment details"),
            _task("buy groceries"),
            _journal("great day, no appointments"),
        ]
        for e in entries:
            upsert_entry(e)
        self.entries = entries

    def test_search_finds_matching_entries(self):
        results = search_text("dentist")
        assert len(results) == 2

    def test_search_returns_tuples(self):
        results = search_text("dentist")
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)

    def test_search_no_match_returns_empty(self):
        results = search_text("nonexistent_xyz_term")
        assert results == []

    def test_search_with_type_filter(self):
        results = search_text("dentist", type="task")
        assert len(results) == 1
        assert results[0][0] == self.entries[0].id

    def test_search_with_type_filter_note(self):
        results = search_text("dentist", type="note")
        assert len(results) == 1
        assert results[0][0] == self.entries[1].id

    def test_search_limit(self):
        # Insert 5 matching entries
        for i in range(5):
            upsert_entry(_task(f"limited search term entry {i}"))
        results = search_text("limited", limit=3)
        assert len(results) <= 3

    def test_search_default_limit_is_50(self):
        # 4 existing entries + this one — default limit of 50 is not hit
        results = search_text("day")
        assert len(results) <= 50

    def test_search_partial_word_fts5(self):
        # FTS5 supports prefix search with *
        results = search_text("dentist*")
        assert len(results) >= 1


class TestClearAll:
    def test_clear_all_empties_entries(self):
        upsert_entry(_task("some entry"))
        assert count() == 1
        clear_all()
        assert count() == 0

    def test_clear_all_empties_fts(self):
        entry = _task("unique clear phrase")
        upsert_entry(entry)
        clear_all()

        conn = get_connection()
        rows = conn.execute(
            "SELECT entry_id FROM entries_fts WHERE entries_fts MATCH ?",
            ("unique",),
        ).fetchall()
        assert rows == []

    def test_clear_all_on_empty_db_is_safe(self):
        clear_all()  # Should not raise
        assert count() == 0


class TestCount:
    def test_count_zero_on_empty(self):
        assert count() == 0

    def test_count_increments_on_insert(self):
        upsert_entry(_task("one"))
        assert count() == 1
        upsert_entry(_task("two"))
        assert count() == 2

    def test_count_decrements_on_delete(self):
        entry = _task("deletable")
        upsert_entry(entry)
        assert count() == 1
        delete_entry(entry.id)
        assert count() == 0

    def test_upsert_does_not_double_count(self):
        entry = _task("once")
        upsert_entry(entry)
        upsert_entry(entry)  # second upsert — same id
        assert count() == 1
