# tests/test_events.py
from datetime import date, datetime, timezone

from bute.models import Entry, EntryType


def test_entry_has_empty_events_by_default():
    e = Entry.create(EntryType.NOTE, "hello")
    # captured event is emitted by Entry.create (Task 4); here we only
    # verify the field exists and is a list
    assert isinstance(e.events, list)


def test_add_event_appends_dict():
    e = Entry(
        id="01K",
        type=EntryType.TASK,
        body="t",
        created=datetime.now(timezone.utc),
    )
    e.add_event("focused", focus_date=date(2026, 4, 10))
    assert e.events == [
        {"date": date.today().isoformat(), "action": "focused", "focus_date": "2026-04-10"}
    ]


def test_add_event_preserves_order():
    e = Entry(id="01K", type=EntryType.TASK, body="t", created=datetime.now(timezone.utc))
    e.add_event("focused", focus_date=date(2026, 4, 10))
    e.add_event("done")
    assert [ev["action"] for ev in e.events] == ["focused", "done"]


def test_add_event_accepts_explicit_date():
    e = Entry(id="01K", type=EntryType.TASK, body="t", created=datetime.now(timezone.utc))
    e.add_event("done", on=date(2026, 4, 21))
    assert e.events[0] == {"date": "2026-04-21", "action": "done"}


def test_events_round_trip(tmp_path, monkeypatch):
    from bute.config import load_config
    from bute.storage import save_entry, load_entry

    monkeypatch.setattr("bute.config.DATA_DIR_DEFAULT", tmp_path)
    config = load_config()

    e = Entry.create(EntryType.TASK, "fix auth bug")
    e.add_event("focused", on=date(2026, 4, 10), focus_date=date(2026, 4, 10))
    e.add_event("done", on=date(2026, 4, 21))
    path = save_entry(e, config)

    loaded = load_entry(path)
    assert len(loaded.events) == len(e.events)
    # The last two events we added should round-trip exactly
    assert loaded.events[-2:] == [
        {"date": "2026-04-10", "action": "focused", "focus_date": "2026-04-10"},
        {"date": "2026-04-21", "action": "done"},
    ]
