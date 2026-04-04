"""Tests for Entry data model."""

from datetime import date

from bute.models import Entry, EntryType, TaskStatus


def test_create_task():
    entry = Entry.create(EntryType.TASK, "test task")
    assert len(entry.id) == 26  # ULID length
    assert entry.type == EntryType.TASK
    assert entry.body == "test task"
    assert entry.status == TaskStatus.ACTIVE
    assert entry.important is False
    assert entry.created is not None


def test_create_note_has_no_status():
    entry = Entry.create(EntryType.NOTE, "some note")
    assert entry.status is None


def test_create_journal_has_no_status():
    entry = Entry.create(EntryType.JOURNAL, "feeling good")
    assert entry.status is None


def test_create_calendar_has_no_status():
    entry = Entry.create(EntryType.CALENDAR, "team standup")
    assert entry.status is None


def test_create_with_tags():
    entry = Entry.create(EntryType.TASK, "fix bug", tags=["backend", "urgent"])
    assert entry.tags == ["backend", "urgent"]


def test_create_important():
    entry = Entry.create(EntryType.TASK, "fix bug", important=True)
    assert entry.important is True


def test_create_with_due():
    entry = Entry.create(EntryType.TASK, "call dentist", due=date(2026, 3, 24))
    assert entry.due == date(2026, 3, 24)


def test_frontmatter_dict_basic():
    entry = Entry.create(EntryType.TASK, "test")
    d = entry.to_frontmatter_dict()
    assert d["id"] == entry.id
    assert d["type"] == "task"
    assert d["status"] == "active"
    assert "created" in d


def test_frontmatter_dict_omits_none():
    entry = Entry.create(EntryType.TASK, "test")
    d = entry.to_frontmatter_dict()
    assert "due" not in d
    assert "date" not in d
    assert "time" not in d
    assert "repeat" not in d


def test_frontmatter_dict_omits_empty_tags():
    entry = Entry.create(EntryType.TASK, "test")
    d = entry.to_frontmatter_dict()
    assert "tags" not in d


def test_frontmatter_dict_includes_tags():
    entry = Entry.create(EntryType.TASK, "test", tags=["a", "b"])
    d = entry.to_frontmatter_dict()
    assert d["tags"] == ["a", "b"]


def test_frontmatter_dict_includes_important():
    entry = Entry.create(EntryType.TASK, "test", important=True)
    d = entry.to_frontmatter_dict()
    assert d["important"] is True


def test_frontmatter_dict_omits_important_when_false():
    entry = Entry.create(EntryType.TASK, "test", important=False)
    d = entry.to_frontmatter_dict()
    assert "important" not in d


def test_frontmatter_dict_note_has_no_status():
    entry = Entry.create(EntryType.NOTE, "test")
    d = entry.to_frontmatter_dict()
    assert "status" not in d


def test_system_tags_is_set():
    from bute.models import SYSTEM_TAGS
    assert isinstance(SYSTEM_TAGS, set)
    assert "goal" in SYSTEM_TAGS
    assert "today" in SYSTEM_TAGS
    assert "thisweek" in SYSTEM_TAGS
