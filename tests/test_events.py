# tests/test_events.py
from datetime import date, datetime, timezone

from bute.models import Entry, EntryType


def test_entry_has_captured_event_on_create():
    from bute import events as ev
    e = Entry.create(EntryType.NOTE, "hello")
    assert len(e.events) == 1
    assert e.events[0]["action"] == ev.CAPTURED


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


def test_events_normalize_yaml_date_objects(tmp_path, monkeypatch):
    """Hand-edited YAML can contain unquoted dates that parse as date objects.
    Load should coerce them to ISO strings so downstream replay works."""
    from bute.storage import load_entry

    md = tmp_path / "01X.md"
    # unquoted 2026-04-10 -> yaml parses as datetime.date
    md.write_text(
        "---\n"
        "id: 01X\n"
        "type: task\n"
        "created: '2026-04-07T10:00:00+00:00'\n"
        "status: active\n"
        "events:\n"
        "  - date: 2026-04-07\n"
        "    action: captured\n"
        "  - date: 2026-04-10\n"
        "    action: focused\n"
        "    focus_date: 2026-04-10\n"
        "---\n"
        "body"
    )
    e = load_entry(md)
    assert e.events[0]["date"] == "2026-04-07"
    assert isinstance(e.events[0]["date"], str)
    assert e.events[1]["focus_date"] == "2026-04-10"
    assert isinstance(e.events[1]["focus_date"], str)


def test_event_constants_exist():
    from bute import events as ev
    assert ev.CAPTURED == "captured"
    assert ev.FOCUSED == "focused"
    assert ev.UNFOCUSED == "unfocused"
    assert ev.SCHEDULED == "scheduled"
    assert ev.UNSCHEDULED == "unscheduled"
    assert ev.DONE == "done"
    assert ev.DROPPED == "dropped"
    assert ev.UNDROPPED == "undropped"
    assert ev.WEEK_PLANNED == "week_planned"
    assert ev.MODIFIED == "modified"
    assert ev.DUE_SET == "due_set"
    assert ev.DUE_CLEARED == "due_cleared"


def test_entry_create_emits_captured_event():
    from bute import events as ev

    e = Entry.create(EntryType.TASK, "fix auth bug")
    assert len(e.events) == 1
    assert e.events[0]["action"] == ev.CAPTURED
    assert e.events[0]["date"] == date.today().isoformat()


def test_entry_create_emits_focus_event_when_focus_date_set():
    from bute import events as ev

    e = Entry.create(EntryType.TASK, "t", focus_date=date.today())
    actions = [x["action"] for x in e.events]
    assert ev.CAPTURED in actions
    assert ev.FOCUSED in actions


def test_entry_create_emits_scheduled_event_when_scheduled_date_set():
    from bute import events as ev

    e = Entry.create(EntryType.CALENDAR, "meeting", scheduled_date=date(2026, 5, 1))
    actions = [x["action"] for x in e.events]
    assert ev.SCHEDULED in actions


def test_synthesize_events_from_legacy_entry():
    """Legacy entry with no events gets synthesized from date fields."""
    from bute.events import synthesize_events
    from bute.models import Entry, EntryType, TaskStatus
    from datetime import datetime, timezone

    e = Entry(
        id="01K",
        type=EntryType.TASK,
        body="legacy task",
        created=datetime(2026, 4, 7, 10, tzinfo=timezone.utc),
        status=TaskStatus.DONE,
        focus_date=date(2026, 4, 14),
        completed_date=date(2026, 4, 21),
    )
    e.events = []  # simulate pre-feature entry

    synth = synthesize_events(e)
    actions = [(x["date"], x["action"]) for x in synth]
    assert ("2026-04-07", "captured") in actions
    assert ("2026-04-14", "focused") in actions
    assert ("2026-04-21", "done") in actions


def test_synthesize_events_from_legacy_dropped_entry():
    """Dropped legacy entry synthesizes 'dropped' on completed_date."""
    from bute.events import synthesize_events
    from bute.models import Entry, EntryType, TaskStatus
    from datetime import datetime, timezone

    e = Entry(
        id="01K",
        type=EntryType.TASK,
        body="gave up",
        created=datetime(2026, 4, 1, tzinfo=timezone.utc),
        status=TaskStatus.DROPPED,
        completed_date=date(2026, 4, 10),
    )
    e.events = []
    actions = [x["action"] for x in synthesize_events(e)]
    assert "captured" in actions
    assert "dropped" in actions


def test_synthesize_events_prefers_real_events():
    """If entry has real events, synthesize returns them (not a synthesized set)."""
    from bute.events import synthesize_events
    from bute.models import Entry, EntryType

    e = Entry.create(EntryType.TASK, "t")
    # Entry.create emits CAPTURED — so entry.events has one real event
    assert len(e.events) == 1
    result = synthesize_events(e)
    assert result == e.events


def test_synthesize_events_sorted_by_date():
    """Synthesized events are sorted in chronological order."""
    from bute.events import synthesize_events
    from bute.models import Entry, EntryType, TaskStatus
    from datetime import datetime, timezone

    e = Entry(
        id="01K",
        type=EntryType.TASK,
        body="t",
        created=datetime(2026, 4, 1, tzinfo=timezone.utc),
        status=TaskStatus.DONE,
        scheduled_date=date(2026, 4, 5),
        focus_date=date(2026, 4, 10),
        completed_date=date(2026, 4, 20),
    )
    e.events = []
    dates = [x["date"] for x in synthesize_events(e)]
    assert dates == sorted(dates)


def test_synthesize_events_skips_scheduled_equal_to_created():
    """Don't emit a SCHEDULED event if scheduled_date equals created.date() —
    the capture event already covers that day."""
    from bute.events import synthesize_events
    from bute.models import Entry, EntryType
    from datetime import datetime, timezone

    e = Entry(
        id="01K",
        type=EntryType.CALENDAR,
        body="standup",
        created=datetime(2026, 4, 7, 10, tzinfo=timezone.utc),
        scheduled_date=date(2026, 4, 7),  # same as created.date()
    )
    e.events = []
    synth = synthesize_events(e)
    # Should have 'captured' but NOT an extra 'scheduled' on the same day
    actions_on_4_7 = [x["action"] for x in synth if x["date"] == "2026-04-07"]
    assert actions_on_4_7 == ["captured"]


def test_replay_state_returns_state_before_day():
    from bute.events import replay_state

    events = [
        {"date": "2026-04-07", "action": "captured"},
        {"date": "2026-04-10", "action": "focused", "focus_date": "2026-04-10"},
        {"date": "2026-04-20", "action": "dropped"},
        {"date": "2026-04-21", "action": "undropped"},
        {"date": "2026-04-21", "action": "done"},
    ]

    # Before Apr 7 — not yet captured
    s = replay_state(events, date(2026, 4, 7))
    assert s["status"] == "absent"

    # Start of Apr 10 — captured but not focused yet
    s = replay_state(events, date(2026, 4, 10))
    assert s["status"] == "active"
    assert s.get("focus_date") is None

    # Start of Apr 20 — focused, still active
    s = replay_state(events, date(2026, 4, 20))
    assert s["status"] == "active"
    assert s.get("focus_date") == "2026-04-10"

    # Start of Apr 21 — dropped
    s = replay_state(events, date(2026, 4, 21))
    assert s["status"] == "dropped"

    # Start of Apr 22 — done (after undrop+done on 21)
    s = replay_state(events, date(2026, 4, 22))
    assert s["status"] == "done"


def test_replay_state_handles_empty_events():
    from bute.events import replay_state
    s = replay_state([], date(2026, 4, 7))
    assert s["status"] == "absent"


def test_replay_state_tracks_scheduled_date():
    from bute.events import replay_state

    events = [
        {"date": "2026-04-07", "action": "captured"},
        {"date": "2026-04-08", "action": "scheduled", "scheduled_date": "2026-04-15"},
        {"date": "2026-04-12", "action": "unscheduled"},
    ]
    assert replay_state(events, date(2026, 4, 10))["scheduled_date"] == "2026-04-15"
    assert replay_state(events, date(2026, 4, 13))["scheduled_date"] is None
