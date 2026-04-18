# Unify Habits With Repeat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse two overlapping concepts — `@habit`-tagged tasks and generic `repeat` tasks — into one model: any task with `repeat` uses the per-date `completions` list, shows in a single "Habits" section of the Focus Log, and is tracked by `bt streak`.

**Architecture:** The selector for "this is a recurring-tracked task" changes from the `@habit` tag to the `repeat` field being set. All recurring tasks (`repeat=daily|weekly|monthly|yearly`) use the existing per-date `completions` model (already implemented in `Entry`). They render as a compact ○/● grid section (formerly "habits only") and are excluded from the main Focus Log list. `bt streak` becomes a view over all recurring tasks. `bt h <name>` stays as an ergonomic shortcut but no longer force-adds the `@habit` tag — it just sets `repeat=daily`. `@habit` remains as a plain tag (no semantic meaning).

**Tech Stack:** Python 3, Click, Rich, pytest. Same stack as rest of bt — no new deps.

**Scope:** ~5 files modified. The `handle_done` path already does the right thing for recurring tasks (appends to `completions` instead of setting status=DONE). The `Entry` model already has `completions` and `recurs_on()`. The structural work is selector swap + Focus Log dedup + removing the now-dead "recurring-not-habit surfaces in main list" fallback.

---

## File Map

**Modify:**
- `src/bute/commands/habits.py` — change `_get_habit_entries` selector from tag to `has_repeat`; simplify `handle_habit_add` to not force `@habit` tag
- `src/bute/ritual_ops.py` — replace `"habit" in e.tags` checks with `e.is_recurring()`; delete the now-redundant "recurring non-habit in main Focus Log" block (lines 116-121)
- `src/bute/commands/views.py` — replace `"habit" in e.tags` tag filters with `not e.is_recurring()` in task-view exclusions
- `src/bute/cli.py` — help text labels (leave "Habits" label — still the user-facing concept)

**Test:**
- `tests/test_habit_storage.py` — assertions on selector now use `repeat` field not `@habit` tag
- `tests/test_ritual_ops.py` — Focus Log excludes recurring tasks regardless of tag
- `tests/test_action.py` — recurring `done` toggles already works, add regression guard

---

### Task 1: Selector swap — recurring tasks identified by `repeat`, not `@habit` tag

**Files:**
- Modify: `src/bute/commands/habits.py` (lines 16-22, the `_get_habit_entries` function)
- Test: `tests/test_habit_storage.py`

- [ ] **Step 1.1: Write a failing test for the new selector**

Append to `tests/test_habit_storage.py`:

```python
def test_get_habit_entries_selects_by_repeat_not_tag(tmp_path, monkeypatch):
    """All recurring tasks qualify as habits, @habit tag is not required."""
    from bute.commands.habits import _get_habit_entries
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    monkeypatch.setenv("BT_DATA_DIR", str(tmp_path))
    config = {"paths": {"data_dir": str(tmp_path)}}

    # Recurring task WITHOUT @habit tag — should now qualify
    recurring_no_tag = Entry.create(
        entry_type=EntryType.TASK,
        body="daily meditation",
        repeat="daily",
    )
    save_entry(recurring_no_tag, config)

    # Non-recurring task WITH @habit tag — should NOT qualify
    tagged_no_repeat = Entry.create(
        entry_type=EntryType.TASK,
        body="misleading legacy tag",
        tags=["habit"],
    )
    save_entry(tagged_no_repeat, config)

    # Recurring weekly task — should qualify (formerly excluded)
    weekly = Entry.create(
        entry_type=EntryType.TASK,
        body="friday status update",
        repeat="weekly",
    )
    save_entry(weekly, config)

    bodies = {e.body for e in _get_habit_entries(config)}
    assert "daily meditation" in bodies
    assert "friday status update" in bodies
    assert "misleading legacy tag" not in bodies
```

- [ ] **Step 1.2: Run test and confirm failure**

Run: `uv run pytest tests/test_habit_storage.py::test_get_habit_entries_selects_by_repeat_not_tag -v`
Expected: FAIL — current selector filters by `tag="habit"`, so recurring-without-tag is missed and tagged-without-repeat is included.

- [ ] **Step 1.3: Update the selector to use `has_repeat`**

In `src/bute/commands/habits.py`, replace the body of `_get_habit_entries` (lines 16-22):

```python
def _get_habit_entries(config) -> list:
    """Get all recurring task entries (any task with `repeat` set), sorted by creation."""
    entries = query_and_load(config, type="task", status="active", has_repeat=True)
    return sorted(entries, key=lambda e: e.created)
```

Note: `is_recurring()` check is redundant since `has_repeat=True` guarantees it; skip the filter.

- [ ] **Step 1.4: Run the new test and confirm pass**

Run: `uv run pytest tests/test_habit_storage.py::test_get_habit_entries_selects_by_repeat_not_tag -v`
Expected: PASS.

- [ ] **Step 1.5: Run full habit storage tests to verify no regressions**

Run: `uv run pytest tests/test_habit_storage.py -v`
Expected: all tests pass. If any test asserts `@habit` tag is the selector, update it to use `repeat` instead, referencing the new contract.

- [ ] **Step 1.6: Commit**

```bash
git add src/bute/commands/habits.py tests/test_habit_storage.py
git commit -m "refactor(habits): select by repeat field, not @habit tag

Recurring tasks are now identified by the repeat field alone. @habit
becomes a plain tag with no structural meaning. Weekly/monthly recurring
tasks now correctly surface in habit views."
```

---

### Task 2: `bt h <name>` add path — drop forced `@habit` tag, keep `repeat=daily`

**Files:**
- Modify: `src/bute/commands/habits.py` (the `handle_habit_add` function, ~lines 125-149)
- Test: `tests/test_habit_storage.py`

- [ ] **Step 2.1: Write a failing test**

Append to `tests/test_habit_storage.py`:

```python
def test_habit_add_sets_repeat_not_tag(tmp_data):
    """bt h <name> creates a recurring task without forcing an @habit tag."""
    from bute.commands.habits import _get_habit_entries, handle_habit_add

    handle_habit_add("morning walk", None)

    entries = _get_habit_entries(None)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.body == "morning walk"
    assert entry.repeat == "daily"
    assert "habit" not in entry.tags  # no forced tag
```

Note: `tmp_data` fixture from `tests/conftest.py` monkeypatches `bute.config.DATA_DIR_DEFAULT`. Pass `config=None` so bt resolves the data dir from that default.

- [ ] **Step 2.2: Run test and confirm failure**

Run: `uv run pytest tests/test_habit_storage.py::test_habit_add_sets_repeat_not_tag -v`
Expected: FAIL — current add forces `tags=["habit"]`.

- [ ] **Step 2.3: Update `handle_habit_add` — remove forced tag**

In `src/bute/commands/habits.py`, replace the `Entry.create(...)` call inside `handle_habit_add` (around line 140):

```python
    entry = Entry.create(
        entry_type=EntryType.TASK,
        body=name,
        repeat="daily",
    )
```

(Remove `tags=["habit"]`.)

- [ ] **Step 2.4: Run test and confirm pass**

Run: `uv run pytest tests/test_habit_storage.py::test_habit_add_sets_repeat_not_tag -v`
Expected: PASS.

- [ ] **Step 2.5: Commit**

```bash
git add src/bute/commands/habits.py tests/test_habit_storage.py
git commit -m "refactor(habits): bt h <name> no longer forces @habit tag

Recurrence is the structural identifier; tags stay plain labels."
```

---

### Task 3: Focus Log — exclude recurring by `is_recurring()`, not by tag

**Files:**
- Modify: `src/bute/ritual_ops.py` (lines 72-73, 90, 116-121)
- Test: `tests/test_ritual_ops.py`

- [ ] **Step 3.1: Write a failing test**

Append to `tests/test_ritual_ops.py`:

```python
def test_focus_log_excludes_recurring_tasks(tmp_data):
    """Recurring tasks are surfaced via the Habits section, not the main Focus Log."""
    from datetime import date
    from bute.models import Entry, EntryType
    from bute.ritual_ops import get_daily_log
    from bute.storage import save_entry

    # Regular task in today's focus — should show
    regular = Entry.create(
        entry_type=EntryType.TASK,
        body="call dentist",
        focus_date=date.today(),
    )
    save_entry(regular)

    # Recurring task (no @habit tag) — should be excluded from main log
    recurring = Entry.create(
        entry_type=EntryType.TASK,
        body="meditate",
        repeat="daily",
        focus_date=date.today(),
    )
    save_entry(recurring)

    bodies = {e.body for e in get_daily_log(None)}
    assert "call dentist" in bodies
    assert "meditate" not in bodies
```

Note: `tmp_data` fixture from `tests/conftest.py` monkeypatches `bute.config.DATA_DIR_DEFAULT`. Pass `config=None` to let bt resolve.

- [ ] **Step 3.2: Run test and confirm failure**

Run: `uv run pytest tests/test_ritual_ops.py::test_focus_log_excludes_recurring_tasks -v`
Expected: FAIL — current filter checks `"habit" in e.tags`, which is False for an untagged recurring task, so it leaks into the main log.

- [ ] **Step 3.3: Replace tag checks with `is_recurring()` checks**

In `src/bute/ritual_ops.py`, inside `get_daily_log`:

- Line ~72 — change `if "habit" in e.tags: continue` to `if e.is_recurring(): continue`
- Line ~90 — change `today_tasks = [e for e in today_tasks if e.created.date() != today and "habit" not in e.tags]` to `today_tasks = [e for e in today_tasks if e.created.date() != today and not e.is_recurring()]`

- [ ] **Step 3.4: Delete the redundant "recurring-non-habit surfaces in main list" block**

In `src/bute/ritual_ops.py`, lines 116-121, delete:

```python
    # Also include recurring entries that match today (excluding @habit — shown separately)
    recurring = query_and_load(config, has_repeat=True, status="active")
    for e in recurring:
        if e.id not in seen and e.recurs_on(today) and "habit" not in e.tags:
            seen.add(e.id)
            result.append(e)
```

All recurring tasks now live in the Habits section (rendered by `_show_habits`). This block was the legacy fallback for "not tagged @habit but recurring" — no longer needed.

- [ ] **Step 3.5: Run test and confirm pass**

Run: `uv run pytest tests/test_ritual_ops.py::test_focus_log_excludes_recurring_tasks -v`
Expected: PASS.

- [ ] **Step 3.6: Run full ritual_ops tests — catch regressions**

Run: `uv run pytest tests/test_ritual_ops.py -v`
Expected: all pass. If a test assumed `"habit" in tags` as the exclusion criterion, update it to use `repeat="daily"` (or similar) and assert `is_recurring()` behavior.

- [ ] **Step 3.7: Commit**

```bash
git add src/bute/ritual_ops.py tests/test_ritual_ops.py
git commit -m "refactor(focus-log): exclude recurring tasks by is_recurring(), not @habit tag

All tasks with repeat set now render via the Habits section of the
Focus Log. Removes dead fallback branch that surfaced recurring-
non-habit tasks in the main list."
```

---

### Task 4: Task views — exclude recurring by `is_recurring()` in `bt t` / `bt b`

**Files:**
- Modify: `src/bute/commands/views.py` (lines 78, 104-105)
- Test: `tests/test_views.py`

- [ ] **Step 4.1: Write a failing test**

Append to `tests/test_views.py`:

```python
def test_tasks_view_excludes_recurring(tmp_data, runner):
    """bt t / bt b exclude recurring tasks regardless of @habit tag."""
    from bute.cli import main
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    regular = Entry.create(entry_type=EntryType.TASK, body="call dentist")
    save_entry(regular)

    recurring = Entry.create(entry_type=EntryType.TASK, body="meditate", repeat="daily")
    save_entry(recurring)

    result = runner.invoke(main, ["b"])
    assert "call dentist" in result.output
    assert "meditate" not in result.output
```

Note: `tmp_data` + `runner` fixtures from `tests/conftest.py`. CliRunner invocation with no `obj` param — `main()` loads config from the (monkeypatched) default path.

- [ ] **Step 4.2: Run test and confirm failure**

Run: `uv run pytest tests/test_views.py::test_tasks_view_excludes_recurring -v`
Expected: FAIL — current filter `"habit" not in e.tags` lets untagged recurring through.

- [ ] **Step 4.3: Update filters**

In `src/bute/commands/views.py`:

- Line ~78: change `entries = [e for e in entries if "habit" not in e.tags]` to `entries = [e for e in entries if not e.is_recurring()]`
- Line ~104-105: change `entries = [e for e in entries if "habit" not in e.tags]` (and its comment) to `entries = [e for e in entries if not e.is_recurring()]`

- [ ] **Step 4.4: Run test and confirm pass**

Run: `uv run pytest tests/test_views.py::test_tasks_view_excludes_recurring -v`
Expected: PASS.

- [ ] **Step 4.5: Run full views tests**

Run: `uv run pytest tests/test_views.py -v`
Expected: all pass. Update any test that relies on `@habit` tag being the exclusion criterion.

- [ ] **Step 4.6: Commit**

```bash
git add src/bute/commands/views.py tests/test_views.py
git commit -m "refactor(views): bt t / bt b exclude recurring tasks via is_recurring()

Matches the Focus Log treatment — recurrence is now the single
signal that a task belongs in the Habits view instead of a list."
```

---

### Task 5: `get_weekly_active_tasks` — same tag→recurring swap

**Files:**
- Modify: `src/bute/ritual_ops.py` (lines 221-228)
- Test: `tests/test_ritual_ops.py`

- [ ] **Step 5.1: Write a failing test**

Append to `tests/test_ritual_ops.py`:

```python
def test_weekly_active_tasks_excludes_recurring(tmp_data):
    """Weekly task selection skips recurring tasks even without @habit tag."""
    from datetime import date
    from bute.models import Entry, EntryType
    from bute.ritual_ops import get_weekly_active_tasks, this_monday
    from bute.storage import save_entry

    monday = this_monday()
    planned = Entry.create(
        entry_type=EntryType.TASK, body="write report", week_date=monday
    )
    save_entry(planned)

    recurring = Entry.create(
        entry_type=EntryType.TASK, body="meditate", repeat="daily", week_date=monday
    )
    save_entry(recurring)

    bodies = {e.body for e in get_weekly_active_tasks(None)}
    assert "write report" in bodies
    assert "meditate" not in bodies
```

Note: `tmp_data` fixture from `tests/conftest.py`. Pass `config=None`.

- [ ] **Step 5.2: Run test and confirm failure**

Run: `uv run pytest tests/test_ritual_ops.py::test_weekly_active_tasks_excludes_recurring -v`
Expected: FAIL — filter checks tag.

- [ ] **Step 5.3: Update the function**

In `src/bute/ritual_ops.py`, in `get_weekly_active_tasks`:

- Replace `weekly = [e for e in weekly if "habit" not in e.tags]` with `weekly = [e for e in weekly if not e.is_recurring()]`
- Replace `return [e for e in fallback if "habit" not in e.tags]` with `return [e for e in fallback if not e.is_recurring()]`

- [ ] **Step 5.4: Run test and confirm pass**

Run: `uv run pytest tests/test_ritual_ops.py::test_weekly_active_tasks_excludes_recurring -v`
Expected: PASS.

- [ ] **Step 5.5: Commit**

```bash
git add src/bute/ritual_ops.py tests/test_ritual_ops.py
git commit -m "refactor(rituals): weekly task selection skips recurring via is_recurring()"
```

---

### Task 6: Full regression + reinstall + smoke check

**Files:** none modified; this is verification.

- [ ] **Step 6.1: Run the full test suite**

Run: `uv run pytest -q`
Expected: all tests pass. If any fail, investigate and fix. Do NOT paper over failures — they indicate real regressions from the selector swap.

- [ ] **Step 6.2: Reinstall bt globally**

Run: `uv tool install --from . --with fastembed --with sqlite-vec bute --force --reinstall`
Expected: install succeeds. bt CLI is live.

- [ ] **Step 6.3: Smoke test — capture, toggle, streak**

Run (in a scratch dir, not the user's real data):

```bash
export BT_DATA_DIR=$(mktemp -d)
bt init
bt h "smoke test habit"
bt streak
bt h   # should show the habit with ○ (not done today)
# Find the entry number (should be #1)
bt 1 done
bt streak   # should show ● for today
```

Expected:
- `bt h <name>` creates a recurring task without `@habit` tag (verify with `cat $BT_DATA_DIR/entries/task/*/*.md`)
- `bt streak` shows the entry
- Toggle via `bt 1 done` appends today's date to `completions` in the .md file

- [ ] **Step 6.4: Smoke test — weekly recurring task surfaces in streak**

```bash
bt t "friday review" r:weekly
bt streak   # weekly task now appears alongside the daily habit
```

Expected: `bt streak` shows both the daily habit and the weekly recurring task — no longer restricted to `@habit`-tagged entries.

- [ ] **Step 6.5: Commit the plan itself as a record**

```bash
git add docs/superpowers/plans/2026-04-18-unify-habits-with-repeat.md
git commit -m "docs: plan for unifying habits with repeat field"
```

---

## Non-Goals (explicitly out of scope)

- Removing the `bt h` / `bt habit` / `bt streak` commands. They stay as ergonomic shortcuts.
- Renaming user-facing "Habits" label. BuJo uses the term; users know it.
- Changing the per-date `completions` storage model. Already correct.
- Touching the `migrate-habits` legacy command. Harmless; leave alone.
- Changing how `bt <n> done` handles recurring tasks. `handle_done` already appends to `completions` correctly (action.py:55-61).
