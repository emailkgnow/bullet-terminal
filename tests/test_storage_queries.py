"""Tests for storage query functions."""

from datetime import date

from bute.models import Entry, EntryType, TaskStatus
from bute.storage import (
    entry_path_from_id,
    load_entries_by_date,
    load_entries_by_filter,
    save_entry,
    update_entry,
)


def test_load_entries_by_date_today(populated_data):
    entries = load_entries_by_date(date.today())
    assert len(entries) == 4


def test_load_entries_by_date_empty(tmp_data):
    entries = load_entries_by_date(date(2020, 1, 1))
    assert entries == []


def test_load_entries_by_date_sorted_chronologically(populated_data):
    entries = load_entries_by_date(date.today())
    for i in range(len(entries) - 1):
        assert entries[i].created <= entries[i + 1].created


def test_load_entries_by_filter_active_tasks(populated_data):
    entries = load_entries_by_filter(
        lambda e: e.type == EntryType.TASK and e.status == TaskStatus.ACTIVE
    )
    assert len(entries) == 2
    assert all(e.type == EntryType.TASK for e in entries)


def test_load_entries_by_filter_by_tag(populated_data):
    entries = load_entries_by_filter(lambda e: "backend" in e.tags)
    assert len(entries) == 1
    assert entries[0].body == "fix bug"


def test_load_entries_by_filter_no_matches(populated_data):
    entries = load_entries_by_filter(lambda e: "nonexistent" in e.tags)
    assert entries == []


def test_update_entry_changes_persisted(tmp_data):
    entry = Entry.create(EntryType.TASK, "original body")
    save_entry(entry)

    entry.body = "updated body"
    entry.important = True
    update_entry(entry)

    from bute.storage import load_entry, entry_path
    loaded = load_entry(entry_path(entry))
    assert loaded.body == "updated body"
    assert loaded.important is True


def test_entry_path_from_id_found(tmp_data):
    entry = Entry.create(EntryType.TASK, "test")
    save_entry(entry)
    path = entry_path_from_id(entry.id)
    assert path is not None
    assert path.exists()


def test_entry_path_from_id_not_found(tmp_data):
    path = entry_path_from_id("01AAAAAAAAAAAAAAAAAAAAAAAA")
    assert path is None
