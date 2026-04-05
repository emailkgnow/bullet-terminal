"""Tests for Markdown file I/O."""

from datetime import date

from bute.models import Entry, EntryType, TaskStatus
from bute.storage import load_entry, save_entry


def test_save_creates_file(tmp_data):
    entry = Entry.create(EntryType.TASK, "test task", tags=["foo"])
    path = save_entry(entry)
    assert path.exists()
    assert path.suffix == ".md"


def test_save_file_contains_body(tmp_data):
    entry = Entry.create(EntryType.TASK, "test task")
    path = save_entry(entry)
    content = path.read_text()
    assert "test task" in content


def test_save_file_contains_frontmatter(tmp_data):
    entry = Entry.create(EntryType.TASK, "test task", tags=["backend"])
    path = save_entry(entry)
    content = path.read_text()
    assert "---" in content
    assert "type: task" in content
    assert "backend" in content


def test_save_path_structure(tmp_data):
    entry = Entry.create(EntryType.TASK, "test")
    path = save_entry(entry)
    # Path should be: tmp_data/entries/YYYY-MM/<ulid>.md
    assert "entries" in str(path)
    assert entry.id in path.name


def test_roundtrip_basic(tmp_data):
    original = Entry.create(EntryType.TASK, "test task")
    path = save_entry(original)
    loaded = load_entry(path)
    assert loaded.id == original.id
    assert loaded.type == original.type
    assert loaded.body == original.body
    assert loaded.status == TaskStatus.ACTIVE


def test_roundtrip_with_metadata(tmp_data):
    original = Entry.create(
        EntryType.TASK,
        "fix the bug",
        important=True,
        tags=["backend", "urgent"],
        due=date(2026, 3, 24),
    )
    path = save_entry(original)
    loaded = load_entry(path)
    assert loaded.important is True
    assert loaded.tags == ["backend", "urgent"]
    assert loaded.due == date(2026, 3, 24)


def test_roundtrip_calendar(tmp_data):
    original = Entry.create(
        EntryType.CALENDAR,
        "1:1 with Ahmed",
        scheduled_time="14:00",
        scheduled_date=date(2026, 3, 29),
        tags=["work"],
    )
    path = save_entry(original)
    loaded = load_entry(path)
    assert loaded.body == "1:1 with Ahmed"
    assert loaded.scheduled_time == "14:00"
    assert loaded.scheduled_date == date(2026, 3, 29)
    assert loaded.status is None  # Calendar has no status


def test_roundtrip_note(tmp_data):
    original = Entry.create(EntryType.NOTE, "OAuth2 tokens last 30 days")
    path = save_entry(original)
    loaded = load_entry(path)
    assert loaded.type == EntryType.NOTE
    assert loaded.status is None


def test_roundtrip_journal(tmp_data):
    original = Entry.create(EntryType.JOURNAL, "rough morning")
    path = save_entry(original)
    loaded = load_entry(path)
    assert loaded.type == EntryType.JOURNAL
    assert loaded.body == "rough morning"


def test_save_entry_writes_to_db(tmp_data):
    from bute.db import close, get_connection

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
    from bute.db import close, get_connection
    from bute.storage import update_entry

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
