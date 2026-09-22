"""Tests for Markdown file I/O."""

from datetime import date

from bute.models import Entry, EntryType, TaskStatus
from bute.storage import entry_path_from_id, load_entries_by_date, load_entries_by_filter, load_entry, save_entry


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
    assert "/entries/task/" in str(path)
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


def test_save_path_includes_type(tmp_data):
    entry = Entry.create(EntryType.TASK, "test path")
    path = save_entry(entry)
    assert "/entries/task/" in str(path)


def test_save_path_note_type(tmp_data):
    entry = Entry.create(EntryType.NOTE, "test note path")
    path = save_entry(entry)
    assert "/entries/note/" in str(path)


def test_save_path_journal_type(tmp_data):
    entry = Entry.create(EntryType.JOURNAL, "test journal path")
    path = save_entry(entry)
    assert "/entries/journal/" in str(path)


def test_save_path_calendar_type(tmp_data):
    entry = Entry.create(EntryType.CALENDAR, "test calendar path")
    path = save_entry(entry)
    assert "/entries/calendar/" in str(path)


def test_entry_path_from_id_finds_task(tmp_data):
    entry = Entry.create(EntryType.TASK, "findable task")
    save_entry(entry)
    path = entry_path_from_id(entry.id)
    assert path is not None
    assert path.exists()
    assert "/entries/task/" in str(path)


def test_entry_path_from_id_finds_journal(tmp_data):
    entry = Entry.create(EntryType.JOURNAL, "findable journal")
    save_entry(entry)
    path = entry_path_from_id(entry.id)
    assert path is not None
    assert "/entries/journal/" in str(path)


def test_entry_path_from_id_returns_none_for_missing(tmp_data):
    path = entry_path_from_id("01ZZZZZZZZZZZZZZZZZZZZZZZZ")
    assert path is None


def test_load_entries_by_date_across_types(tmp_data):
    task = Entry.create(EntryType.TASK, "today task")
    note = Entry.create(EntryType.NOTE, "today note")
    journal = Entry.create(EntryType.JOURNAL, "today journal")
    for e in [task, note, journal]:
        save_entry(e)

    entries = load_entries_by_date(date.today())
    types = {e.type for e in entries}
    assert EntryType.TASK in types
    assert EntryType.NOTE in types
    assert EntryType.JOURNAL in types
    assert len(entries) == 3


def test_load_entries_by_filter_finds_all_types(tmp_data):
    task = Entry.create(EntryType.TASK, "filter task")
    note = Entry.create(EntryType.NOTE, "filter note")
    for e in [task, note]:
        save_entry(e)

    entries = load_entries_by_filter(lambda e: True)
    assert len(entries) == 2
    types = {e.type for e in entries}
    assert EntryType.TASK in types
    assert EntryType.NOTE in types


def _entry_at(created):
    """An entry whose ULID and created timestamp both point at `created`."""
    from ulid import ULID

    entry = Entry.create(EntryType.JOURNAL, "couldn't sleep")
    entry.id = str(ULID.from_datetime(created))
    entry.created = created
    return entry


def test_path_from_id_finds_entry_filed_in_next_local_month(tmp_data):
    """UTC+3 at 01:30 on Oct 1 is still Sep 30 in UTC — the ULID's month.

    save_entry files by the local month (2026-10), so the lookup must not
    stop at the ULID's UTC month (2026-09).
    """
    from datetime import datetime, timedelta, timezone

    created = datetime(2026, 10, 1, 1, 30, tzinfo=timezone(timedelta(hours=3)))
    path = save_entry(_entry_at(created))
    assert path.parent.name == "2026-10"

    assert entry_path_from_id(path.stem) == path


def test_path_from_id_finds_entry_filed_in_previous_local_month(tmp_data):
    """UTC-5 at 21:00 on Sep 30 is already Oct 1 in UTC."""
    from datetime import datetime, timedelta, timezone

    created = datetime(2026, 9, 30, 21, 0, tzinfo=timezone(timedelta(hours=-5)))
    path = save_entry(_entry_at(created))
    assert path.parent.name == "2026-09"

    assert entry_path_from_id(path.stem) == path


def test_path_from_id_rolls_over_the_year(tmp_data):
    """UTC+3 at 02:00 on Jan 1 is Dec 31 in UTC — next month is next year."""
    from datetime import datetime, timedelta, timezone

    created = datetime(2027, 1, 1, 2, 0, tzinfo=timezone(timedelta(hours=3)))
    path = save_entry(_entry_at(created))
    assert path.parent.name == "2027-01"

    assert entry_path_from_id(path.stem) == path
