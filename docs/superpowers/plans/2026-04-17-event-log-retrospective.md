# Event Log Retrospective Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-entry event log so `bt m` renders each day as a snapshot of every lifecycle event (capture, focus, schedule, complete, drop, undrop), with state-at-start-of-day context — making the monthly log a true BuJo retrospective artifact.

**Architecture:** Events are stored as a YAML array `events` in each entry's frontmatter (`.md` remains source of truth). Every mutation site (capture, action, rituals) appends one event via `Entry.add_event(action, **kw)`. `bt m` collects each entry's events (real, or render-time synthesized from existing date fields for pre-feature entries), filters to the month, groups by day, and replays state up to each day to render `[state-at-start-of-day] → action` rows.

**Tech Stack:** Python 3.13, `python-frontmatter` (YAML), `rich` (tables), `click` (CLI), `pytest`.

---

## File Structure

| File | Role |
|------|------|
| `src/bute/models.py` | Add `events: list[dict]` field + `Entry.add_event()` helper + emit `captured` in `Entry.create()`. Serialize in `to_frontmatter_dict()`. |
| `src/bute/storage.py` | Deserialize events in `load_entry()`; add `events` to `known_keys`. |
| `src/bute/events.py` | **NEW.** Event action constants, `synthesize_events(entry)` (for legacy entries), `replay_state(events, up_to_date)`. Pure functions, no I/O. |
| `src/bute/commands/capture.py` | Unchanged (capture event is emitted by `Entry.create`). |
| `src/bute/commands/action.py` | Each mutation site (done/drop/later/backlog/schedule/focus-via-tag-today) appends an event before `update_entry`. |
| `src/bute/commands/rituals.py` | `dp_cmd` & `wp_cmd` emit `focused` events when they set `focus_date`/`week_date`. Rewrite `_build_month_data` to use events. |
| `tests/test_events.py` | **NEW.** Covers: field round-trip, `add_event`, synthesis, replay. |
| `tests/test_action.py` | Extend to assert events are appended by each action. |

---

## Event Schema

Each event is a dict in the entry's `events` list:

```yaml
events:
  - {date: '2026-04-07', action: captured}
  - {date: '2026-04-10', action: focused, focus_date: '2026-04-10'}
  - {date: '2026-04-15', action: scheduled, scheduled_date: '2026-04-20'}
  - {date: '2026-04-20', action: dropped}
  - {date: '2026-04-21', action: undropped}
  - {date: '2026-04-21', action: focused, focus_date: '2026-04-21'}
  - {date: '2026-04-21', action: done}
```

**Action constants** (string enum, lowercase):
- `captured` — entry created
- `focused` — `focus_date` set (carries new value)
- `unfocused` — `focus_date` cleared (e.g. `bt later`, `bt backlog`)
- `scheduled` — `scheduled_date` set (carries new value); also on reschedule
- `unscheduled` — `scheduled_date` cleared
- `due_set` / `due_cleared`
- `done` — status → DONE
- `dropped` — status → DROPPED
- `undropped` — status reverted to ACTIVE (from done or dropped)
- `week_planned` — `week_date` set (wp)
- `modified` — body changed (optional, emit once per `mod`)

Tag add/remove and important-toggle are intentionally **not** logged in this first pass — they're metadata churn, not BuJo-reflection events.

---

### Task 1: Add `events` field to `Entry` + `add_event()` helper

**Files:**
- Modify: `src/bute/models.py`
- Create: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_events.py -v
```
Expected: FAIL — `AttributeError: 'Entry' object has no attribute 'events'` (or `add_event`).

- [ ] **Step 3: Implement field + helper**

Edit `src/bute/models.py`. In the `Entry` dataclass, add immediately after `completions`:

```python
events: list[dict] = field(default_factory=list)
```

And add a method on `Entry`:

```python
def add_event(self, action: str, on: date | None = None, **context) -> None:
    """Append an event to this entry's log.

    Args:
        action: one of the event action constants (see bute.events).
        on: date of the event (defaults to today).
        **context: extra fields serialized as ISO strings for date/datetime.
    """
    event_date = (on or date.today()).isoformat()
    event: dict = {"date": event_date, "action": action}
    for k, v in context.items():
        if isinstance(v, date):
            event[k] = v.isoformat()
        else:
            event[k] = v
    self.events.append(event)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_events.py -v
```
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/bute/models.py tests/test_events.py
git commit -m "feat(model): add events field and add_event helper to Entry"
```

---

### Task 2: Serialize/deserialize `events` in YAML frontmatter

**Files:**
- Modify: `src/bute/models.py` (`to_frontmatter_dict`)
- Modify: `src/bute/storage.py` (`load_entry`, `known_keys`)
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_events.py`:

```python
def test_events_round_trip(tmp_path, monkeypatch):
    from bute.config import load_config
    from bute.storage import save_entry, load_entry

    monkeypatch.setenv("BUTE_DATA_DIR", str(tmp_path))
    config = load_config()

    e = Entry.create(EntryType.TASK, "fix auth bug")
    e.add_event("focused", on=date(2026, 4, 10), focus_date=date(2026, 4, 10))
    e.add_event("done", on=date(2026, 4, 21))
    path = save_entry(e, config)

    loaded = load_entry(path)
    assert len(loaded.events) == len(e.events)
    # captured event from Entry.create (Task 4) + the two we added above
    assert loaded.events[-2:] == [
        {"date": "2026-04-10", "action": "focused", "focus_date": "2026-04-10"},
        {"date": "2026-04-21", "action": "done"},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_events.py::test_events_round_trip -v
```
Expected: FAIL — events lost on load (`events` not in known_keys, falls into extra_meta).

- [ ] **Step 3: Implement serialization**

Edit `src/bute/models.py`, in `to_frontmatter_dict()` just before the `completions` block:

```python
if self.events:
    d["events"] = self.events
```

Edit `src/bute/storage.py`:

1. Add `"events"` to the `known_keys` set in `load_entry()`:

```python
known_keys = {
    "id", "type", "created", "status", "important",
    "due", "date", "time", "repeat", "tags", "completions",
    "focus_date", "week_date", "completed_date", "events",
}
```

2. In the `Entry(...)` constructor call in `load_entry()`, add:

```python
events=list(post.metadata.get("events", []) or []),
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/test_events.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bute/models.py src/bute/storage.py tests/test_events.py
git commit -m "feat(storage): round-trip events list through YAML frontmatter"
```

---

### Task 3: Create `events.py` module with action constants

**Files:**
- Create: `src/bute/events.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_events.py`:

```python
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
```

- [ ] **Step 2: Verify fails**

```bash
uv run pytest tests/test_events.py::test_event_constants_exist -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'bute.events'`.

- [ ] **Step 3: Implement**

Create `src/bute/events.py`:

```python
"""Event log for entry lifecycle (capture, focus, schedule, complete, etc.).

Events are stored as a list of dicts on each Entry; this module defines
the action constants and pure helpers for synthesis (legacy entries)
and replay (state-at-a-given-day).
"""

from datetime import date
from typing import Iterable

from bute.models import Entry, EntryType, TaskStatus


# --- Action constants ---
CAPTURED = "captured"
FOCUSED = "focused"
UNFOCUSED = "unfocused"
SCHEDULED = "scheduled"
UNSCHEDULED = "unscheduled"
DONE = "done"
DROPPED = "dropped"
UNDROPPED = "undropped"
WEEK_PLANNED = "week_planned"
MODIFIED = "modified"
DUE_SET = "due_set"
DUE_CLEARED = "due_cleared"


ALL_ACTIONS = {
    CAPTURED, FOCUSED, UNFOCUSED, SCHEDULED, UNSCHEDULED,
    DONE, DROPPED, UNDROPPED, WEEK_PLANNED, MODIFIED,
    DUE_SET, DUE_CLEARED,
}
```

- [ ] **Step 4: Verify passes**

```bash
uv run pytest tests/test_events.py::test_event_constants_exist -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bute/events.py tests/test_events.py
git commit -m "feat(events): add events module with action constants"
```

---

### Task 4: Emit `captured` event at `Entry.create()`

**Files:**
- Modify: `src/bute/models.py` (`Entry.create`)
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_events.py`:

```python
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
```

- [ ] **Step 2: Verify fails**

```bash
uv run pytest tests/test_events.py -v -k "create_emits"
```
Expected: FAIL — events list is empty (Entry.create doesn't emit).

- [ ] **Step 3: Implement**

Edit `Entry.create()` in `src/bute/models.py` — at the end, just before the `return cls(...)` call, build the entry and then emit events. Simplest: change the body to construct via `cls(...)`, assign to a variable, emit events, then return:

```python
@classmethod
def create(cls, entry_type, body, important=False, tags=None, due=None,
           scheduled_date=None, scheduled_time=None, repeat=None,
           focus_date=None, week_date=None, completed_date=None,
           extra_meta=None) -> "Entry":
    """Factory that generates a ULID and sets the created timestamp."""
    now = datetime.now(timezone.utc).astimezone()
    entry = cls(
        id=str(ULID()),
        type=entry_type,
        body=body,
        created=now,
        status=TaskStatus.ACTIVE if entry_type == EntryType.TASK else None,
        important=important,
        due=due,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        repeat=repeat,
        focus_date=focus_date,
        week_date=week_date,
        completed_date=completed_date,
        tags=tags or [],
        extra_meta=extra_meta or {},
    )

    # Initial events — late import to avoid cycle
    from bute import events as ev
    today = now.date()
    entry.add_event(ev.CAPTURED, on=today)
    if focus_date is not None:
        entry.add_event(ev.FOCUSED, on=today, focus_date=focus_date)
    if scheduled_date is not None:
        entry.add_event(ev.SCHEDULED, on=today, scheduled_date=scheduled_date)
    if due is not None:
        entry.add_event(ev.DUE_SET, on=today, due=due)
    if week_date is not None:
        entry.add_event(ev.WEEK_PLANNED, on=today, week_date=week_date)
    return entry
```

- [ ] **Step 4: Verify passes**

```bash
uv run pytest tests/test_events.py -v
```
Expected: PASS (all events tests, including Task 1 tests now count 1 captured + the manual adds).

- [ ] **Step 5: Update & commit**

Adjust the Task 1 test `test_entry_has_empty_events_by_default` — after this task, it should assert `len(e.events) == 1` and `e.events[0]["action"] == "captured"`. Edit:

```python
def test_entry_has_captured_event_on_create():
    from bute import events as ev
    e = Entry.create(EntryType.NOTE, "hello")
    assert len(e.events) == 1
    assert e.events[0]["action"] == ev.CAPTURED
```

Rename the test (replace the earlier `test_entry_has_empty_events_by_default`).

Run the full file:
```bash
uv run pytest tests/test_events.py -v
```

```bash
git add src/bute/models.py tests/test_events.py
git commit -m "feat(events): emit captured/focused/scheduled events from Entry.create"
```

---

### Task 5: Emit events in `action.py` (done, drop, focus, later, backlog, schedule)

**Files:**
- Modify: `src/bute/commands/action.py`
- Modify: `tests/test_action.py`

Review the mutation sites already identified:
- `done` path: sets `status = DONE`, `completed_date = today` — emit `DONE`
- `drop` path: sets `status = DROPPED`, `completed_date = today` — emit `DROPPED`
- focus ritual (via action): sets `focus_date`, `week_date` — emit `FOCUSED`
- `later` / `backlog` paths: clear `focus_date`/`week_date` — emit `UNFOCUSED`
- `d:<date>` action: sets `scheduled_date` — emit `SCHEDULED` (or `UNSCHEDULED` if clearing)
- `clear due` / `due:` action: emit `DUE_SET` / `DUE_CLEARED`
- `mod <text>`: emit `MODIFIED`
- `undo` of done/drop: if status reverts from DONE/DROPPED → emit `UNDROPPED`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_action.py`:

```python
def test_action_done_emits_done_event(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry, load_entry, entry_path
    _setup_config(tmp_config, tmp_data)  # existing helper

    e = Entry.create(EntryType.TASK, "ship it")
    save_entry(e)

    # display it (populate .state.json so "1" resolves) — emulate a prior view
    from bute.state import save_state
    save_state("tasks", [e.id])

    result = runner.invoke(main, ["1", "done"])
    assert result.exit_code == 0

    reloaded = load_entry(entry_path(e))
    actions = [ev["action"] for ev in reloaded.events]
    assert "done" in actions


def test_action_drop_emits_dropped_event(runner, tmp_config, tmp_data):
    # Same pattern: create, display, drop, reload, assert "dropped" in events
    ...  # fill in identically to the above, substituting "drop"


def test_action_later_emits_unfocused_event(runner, tmp_config, tmp_data):
    # Create with focus_date=today, call "1 later", reload, assert "unfocused"
    ...
```

(Include all three tests; the ellipses in the second/third are spelled out below in Step 2 of sibling tasks if needed — but the above pattern is the recipe.)

- [ ] **Step 2: Verify the tests fail**

```bash
uv run pytest tests/test_action.py -k "emits" -v
```
Expected: FAIL — events don't include the new actions.

- [ ] **Step 3: Implement**

Edit `src/bute/commands/action.py`. At each mutation site, call `entry.add_event(...)` **before** `update_entry(entry)`. Use late import at top of the function: `from bute import events as ev`.

Specific edits (line numbers are approximate — search for the exact assignments):

**Done** — near `entry.status = TaskStatus.DONE; entry.completed_date = date.today()`:
```python
entry.status = TaskStatus.DONE
entry.completed_date = date.today()
entry.add_event(ev.DONE)
```

**Drop** — near `entry.status = TaskStatus.DROPPED`:
```python
entry.status = TaskStatus.DROPPED
entry.completed_date = date.today()
entry.add_event(ev.DROPPED)
```

**Focus (via action — e.g. the `bt <n> @today`-style path that sets focus_date)** — near `entry.focus_date = today; entry.week_date = monday`:
```python
entry.focus_date = today
entry.week_date = monday
entry.add_event(ev.FOCUSED, focus_date=today)
```

**Later / Backlog** — near both occurrences of `entry.focus_date = None`:
```python
entry.focus_date = None
# the backlog path also clears week_date:
entry.week_date = None
entry.add_event(ev.UNFOCUSED)
```

**Schedule via `d:<date>`** — the two `entry.scheduled_date = ...` sites:
```python
entry.scheduled_date = None
entry.add_event(ev.UNSCHEDULED)
```
and
```python
entry.scheduled_date = resolve_date(raw_date)
entry.add_event(ev.SCHEDULED, scheduled_date=entry.scheduled_date)
```

**`mod <text>`** — find the line body reassignment (`entry.body = ...`) and add:
```python
entry.add_event(ev.MODIFIED)
```

**Undo handler** — in the block that reverts status:
```python
entry.status = TaskStatus(prev["status"])
entry.completed_date = date_type.fromisoformat(prev_completed) if prev_completed else None
if entry.status == TaskStatus.ACTIVE:
    entry.add_event(ev.UNDROPPED)
```

- [ ] **Step 4: Verify passes**

```bash
uv run pytest tests/test_action.py -v
```
Expected: PASS (new events tests + all existing tests still pass).

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/action.py tests/test_action.py
git commit -m "feat(events): emit events from action.py mutation sites"
```

---

### Task 6: Emit `focused`/`week_planned` events in rituals (dp, wp)

**Files:**
- Modify: `src/bute/commands/rituals.py`
- Modify: `tests/test_rituals.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rituals.py`:

```python
def test_dp_emits_focused_event(runner, tmp_config, tmp_data, monkeypatch):
    _setup_config(tmp_config, tmp_data)
    from bute.models import Entry, EntryType
    from bute.storage import save_entry, load_entry, entry_path

    t = Entry.create(EntryType.TASK, "plan me")  # no focus_date
    save_entry(t)

    # Mock questionary to select our task
    import questionary
    monkeypatch.setattr(
        questionary, "checkbox",
        lambda *a, **kw: type("Q", (), {"ask": lambda self: [f"plan me ({t.id[:8]})"]})()
    )

    result = runner.invoke(main, ["dp"], input="\n")
    assert result.exit_code == 0

    reloaded = load_entry(entry_path(t))
    assert any(e["action"] == "focused" for e in reloaded.events)
```

- [ ] **Step 2: Verify fails**

```bash
uv run pytest tests/test_rituals.py::test_dp_emits_focused_event -v
```
Expected: FAIL — dp doesn't emit focus events.

- [ ] **Step 3: Implement**

In `src/bute/commands/rituals.py`, find each site in `dp_cmd` and `wp_cmd` where `entry.focus_date = today` or `entry.week_date = monday` is set. Emit:

```python
from bute import events as ev
# ... setting focus_date/week_date ...
entry.focus_date = today
entry.week_date = monday
entry.add_event(ev.FOCUSED, focus_date=today)
# wp path also emits week_planned:
entry.add_event(ev.WEEK_PLANNED, week_date=monday)
```

- [ ] **Step 4: Verify passes**

```bash
uv run pytest tests/test_rituals.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/rituals.py tests/test_rituals.py
git commit -m "feat(events): emit focused/week_planned events from dp and wp"
```

---

### Task 7: Render-time event synthesis for legacy entries

**Files:**
- Modify: `src/bute/events.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_events.py`:

```python
def test_synthesize_events_from_legacy_entry():
    """Legacy entry with no events gets synthesized from date fields."""
    from bute import events as ev
    from bute.events import synthesize_events
    from datetime import datetime, timezone

    e = Entry(
        id="01K",
        type=EntryType.TASK,
        body="legacy task",
        created=datetime(2026, 4, 7, tzinfo=timezone.utc),
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


def test_synthesize_events_prefers_real_events():
    """If entry has real events, synthesize returns them as-is."""
    from bute.events import synthesize_events
    e = Entry.create(EntryType.TASK, "t")
    # Has a real captured event
    assert len(synthesize_events(e)) == 1
    assert synthesize_events(e) is e.events or synthesize_events(e) == e.events
```

- [ ] **Step 2: Verify fails**

```bash
uv run pytest tests/test_events.py -k "synthesize" -v
```
Expected: FAIL — `synthesize_events` doesn't exist.

- [ ] **Step 3: Implement**

Append to `src/bute/events.py`:

```python
def synthesize_events(entry: Entry) -> list[dict]:
    """Return an event list for an entry, synthesizing from date fields
    when the entry has no stored events (legacy entries from before the
    event-log feature).

    Priority:
    - If entry.events is non-empty → return entry.events unchanged.
    - Else synthesize from: created, scheduled_date, focus_date,
      completed_date (status dictates done vs dropped).
    """
    if entry.events:
        return entry.events

    synth: list[dict] = []
    created_date = entry.created.date()
    synth.append({"date": created_date.isoformat(), "action": CAPTURED})

    if entry.scheduled_date is not None and entry.scheduled_date != created_date:
        synth.append({
            "date": entry.scheduled_date.isoformat(),
            "action": SCHEDULED,
            "scheduled_date": entry.scheduled_date.isoformat(),
        })

    if entry.focus_date is not None and entry.focus_date != created_date:
        synth.append({
            "date": entry.focus_date.isoformat(),
            "action": FOCUSED,
            "focus_date": entry.focus_date.isoformat(),
        })

    if entry.completed_date is not None:
        action = DONE if entry.status == TaskStatus.DONE else (
            DROPPED if entry.status == TaskStatus.DROPPED else None
        )
        if action:
            synth.append({
                "date": entry.completed_date.isoformat(),
                "action": action,
            })

    synth.sort(key=lambda x: x["date"])
    return synth
```

- [ ] **Step 4: Verify passes**

```bash
uv run pytest tests/test_events.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bute/events.py tests/test_events.py
git commit -m "feat(events): synthesize events from date fields for legacy entries"
```

---

### Task 8: Event replay → state-at-start-of-day

**Files:**
- Modify: `src/bute/events.py`
- Modify: `tests/test_events.py`

The replay returns a dict representing the entry's state as of the start of a given day (i.e. after replaying all events strictly before that date).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_events.py`:

```python
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
    assert s == {"status": "absent"}

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
```

- [ ] **Step 2: Verify fails**

```bash
uv run pytest tests/test_events.py::test_replay_state_returns_state_before_day -v
```
Expected: FAIL — `replay_state` doesn't exist.

- [ ] **Step 3: Implement**

Append to `src/bute/events.py`:

```python
def replay_state(events: Iterable[dict], up_to: date) -> dict:
    """Return the entry state as of the start of `up_to`.

    Replays all events strictly before up_to (events on up_to are NOT
    applied — they *happen on* that day). Returns a dict with keys:
    status ("absent"/"active"/"done"/"dropped"),
    focus_date, scheduled_date (isoformat strings or None).

    "absent" means the entry hadn't been captured yet at start-of-day.
    """
    state: dict = {
        "status": "absent",
        "focus_date": None,
        "scheduled_date": None,
    }
    for ev in events:
        ev_date = date.fromisoformat(ev["date"])
        if ev_date >= up_to:
            break  # events are sorted; we're done
        action = ev["action"]
        if action == CAPTURED:
            state["status"] = "active"
        elif action == FOCUSED:
            state["focus_date"] = ev.get("focus_date")
        elif action == UNFOCUSED:
            state["focus_date"] = None
        elif action == SCHEDULED:
            state["scheduled_date"] = ev.get("scheduled_date")
        elif action == UNSCHEDULED:
            state["scheduled_date"] = None
        elif action == DONE:
            state["status"] = "done"
        elif action == DROPPED:
            state["status"] = "dropped"
        elif action == UNDROPPED:
            state["status"] = "active"
        # MODIFIED, WEEK_PLANNED, DUE_* don't change core status/focus
    return state
```

- [ ] **Step 4: Verify passes**

```bash
uv run pytest tests/test_events.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bute/events.py tests/test_events.py
git commit -m "feat(events): add replay_state for start-of-day reconstruction"
```

---

### Task 9: Rewrite `_build_month_data` to use events

**Files:**
- Modify: `src/bute/commands/rituals.py`
- Modify: `tests/test_rituals.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rituals.py`:

```python
def test_monthly_log_shows_entry_on_each_event_day(runner, tmp_config, tmp_data):
    """An entry captured Apr 7 and completed Apr 21 should show on both days."""
    from datetime import datetime, timezone, date
    from bute.models import Entry, EntryType, TaskStatus
    from bute.storage import save_entry
    _setup_config(tmp_config, tmp_data)

    e = Entry(
        id="01KLEGACY",
        type=EntryType.TASK,
        body="fix auth bug",
        created=datetime(2026, 4, 7, 10, tzinfo=timezone.utc),
        status=TaskStatus.DONE,
        focus_date=date(2026, 4, 14),
        completed_date=date(2026, 4, 21),
        events=[],  # legacy — will be synthesized
    )
    save_entry(e)

    result = runner.invoke(main, ["m", "2026-04"])
    assert result.exit_code == 0
    # Body should appear multiple times in the month view
    assert result.output.count("fix auth bug") >= 3  # captured, focused, done
```

- [ ] **Step 2: Verify fails**

```bash
uv run pytest tests/test_rituals.py::test_monthly_log_shows_entry_on_each_event_day -v
```
Expected: FAIL — current `_build_month_data` only shows each entry once (on creation day).

- [ ] **Step 3: Implement**

Replace `_build_month_data` in `src/bute/commands/rituals.py` with an event-driven version.

```python
def _build_month_data(target: date, config) -> dict[int, list[str]]:
    """Build a month's log: dict of day_num -> list of rendered strings.

    Each entry surfaces on every day any of its events fall on. Each row
    includes a state-at-start-of-day bracket and the event's verb.
    """
    import calendar
    from bute.display import _preview
    from bute.events import (
        CAPTURED, FOCUSED, UNFOCUSED, SCHEDULED, UNSCHEDULED,
        DONE, DROPPED, UNDROPPED, WEEK_PLANNED, MODIFIED,
        synthesize_events, replay_state,
    )
    from bute.models import EntryType
    from bute.storage import query_and_load

    first_day = date(target.year, target.month, 1)
    _, last = calendar.monthrange(target.year, target.month)
    last_day = date(target.year, target.month, last)
    today = date.today()
    if last_day > today:
        last_day = today

    # Collect every entry that had at least one event in this month. Cheapest
    # pass: load all entries with an event touching the month range, OR whose
    # date fields fall in range (for legacy synthesis).
    entries = query_and_load(config)  # all entries; optimize later with SQLite

    lines_by_day: dict[int, list[str]] = {}

    verb = {
        CAPTURED: "captured",
        FOCUSED: "focused",
        UNFOCUSED: "unfocused",
        SCHEDULED: "scheduled",
        UNSCHEDULED: "unscheduled",
        DONE: "done ✓",
        DROPPED: "dropped ✗",
        UNDROPPED: "undropped",
        WEEK_PLANNED: "week planned",
        MODIFIED: "modified",
    }
    type_sigil = {
        EntryType.TASK: "[cyan].[/cyan]",
        EntryType.NOTE: "[yellow]-[/yellow]",
        EntryType.JOURNAL: "[magenta]=[/magenta]",
        EntryType.CALENDAR: "[green]o[/green]",
    }

    for e in entries:
        events = synthesize_events(e)
        for ev in events:
            ev_date = date.fromisoformat(ev["date"])
            if ev_date < first_day or ev_date > last_day:
                continue

            state = replay_state(events, ev_date)
            sigil = type_sigil[e.type]
            preview = _preview(e.body)

            # Dim the entry if it was already done/dropped at start of day
            state_mark = ""
            if state["status"] == "done":
                preview = f"[strike dim]{preview}[/strike dim]"
            elif state["status"] == "dropped":
                preview = f"[dim]{preview}[/dim]"
            elif state["status"] == "absent":
                state_mark = ""  # fresh capture — no prefix needed

            line = f"{sigil} {preview}  [dim]→ {verb.get(ev['action'], ev['action'])}[/dim]"
            lines_by_day.setdefault(ev_date.day, []).append(line)

    return lines_by_day
```

Note: the existing `_render_month_table` is kept untouched — it already renders `day_num -> list[str]`. Only the data-building function changes.

- [ ] **Step 4: Verify passes**

```bash
uv run pytest tests/test_rituals.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/rituals.py tests/test_rituals.py
git commit -m "feat(bt m): render entries per event-day with state replay"
```

---

### Task 10: Smoke test on real data

**Files:** none (manual verification)

- [ ] **Step 1: Reinstall**

```bash
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest -q --ignore=tests/test_habit_storage.py --ignore=tests/test_export.py
```
Expected: only the pre-existing `test_bt_noargs_skips_wp_when_done` failure (documented in prior session). Everything else PASS.

- [ ] **Step 3: Check `bt m` on real data**

```bash
bt m
```
Expected: for a month with activity, you see entries surface on their event days. Legacy entries (no stored events) use synthesized events from `created`/`focus_date`/`completed_date`. New entries captured after this change surface on real event days.

- [ ] **Step 4: Check a specific month and verify lifecycle coverage**

```bash
bt m 2026-03
```
Spot-check: pick one completed task you remember and verify it surfaces on both its capture day AND completion day (at minimum).

- [ ] **Step 5: Commit the CLAUDE.md update**

Update CLAUDE.md "Design Decisions" section — add after the `Logs are derived` line:

```
- **`bt m` is event-driven** — each entry surfaces on every day any of its lifecycle events occurred (captured, focused, scheduled, completed, dropped, undropped). Events stored as a YAML list in the entry's frontmatter; legacy entries without events use render-time synthesis from existing date fields. This makes `bt m` a BuJo-style retrospective — you can relive each day of the month.
```

```bash
git add CLAUDE.md
git commit -m "docs: note event-driven bt m retrospective"
```

---

### Task 11 (optional): `bt m <n>` timeline view for a single entry

Deferred unless desired. Adds a new action: `bt m <n>` opens the timeline of entry N from the last view.

Out of scope for this plan — ship Tasks 1–10 first and live with the new `bt m` before adding extras.

---

## Self-Review Notes

- **Spec coverage:** Tasks 1–2 cover the schema. Tasks 3–4 add constants and initial emission. Tasks 5–6 instrument every mutation site. Task 7 backfills legacy entries (render-time synthesis). Task 8 is the replay primitive. Task 9 is the rendering rewrite. Task 10 is the smoke test.
- **Placeholder scan:** Task 5's tests are written as a pattern (three tests, ellipses show repetition) — the implementer must spell out all three bodies using the shown recipe. If that is judged too loose, expand during execution. All other steps have complete code.
- **Type consistency:** `entry.events` is `list[dict]`; all events use `{"date": isoformat_str, "action": constant_str, **context}`. `replay_state` returns `{"status", "focus_date", "scheduled_date"}` as documented. `synthesize_events` returns a sorted list of the same dict shape.
- **Known risks:** (a) `query_and_load(config)` without filters in Task 9 loads every entry — OK for hundreds of entries, may need an index-backed query at scale. (b) `bt undo` currently rolls back fields but doesn't remove events — undone events remain in the log. Acceptable: the log is an event *record*, not an editable state. (c) Backfill is render-time only; we never persist synthesized events, so they regenerate each time `bt m` runs. Cheap and correct.
