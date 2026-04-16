# Replace @today/@thisweek with Date Fields — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `@today` and `@thisweek` system tags with proper `focus_date` and `week_date` fields on `Entry`, eliminating tag rot and enabling date-based retrospectives.

**Architecture:** Add two `Optional[date]` fields to the Entry dataclass and YAML frontmatter. All code that reads/writes/filters these tags switches to the new fields. A migration script converts existing tagged entries. The SQLite index gets two new columns.

**Tech Stack:** Python dataclasses, YAML frontmatter, SQLite

---

### Task 1: Add fields to Entry model and storage

**Files:**
- Modify: `src/bute/models.py:37-110`
- Modify: `src/bute/storage.py:61-91`
- Test: `tests/test_action.py` (existing fixtures create entries)

- [ ] **Step 1: Add fields to Entry dataclass**

In `src/bute/models.py`, add after line 50 (`repeat` field):

```python
    focus_date: Optional[date] = None
    week_date: Optional[date] = None
```

- [ ] **Step 2: Add fields to Entry.create() factory**

In `src/bute/models.py`, add parameters to `create()` after `repeat`:

```python
        focus_date: date | None = None,
        week_date: date | None = None,
```

And in the `cls()` call, add:

```python
            focus_date=focus_date,
            week_date=week_date,
```

- [ ] **Step 3: Add fields to to_frontmatter_dict()**

In `src/bute/models.py`, add after the `repeat` block (after line 103):

```python
        if self.focus_date is not None:
            d["focus_date"] = self.focus_date.isoformat()
        if self.week_date is not None:
            d["week_date"] = self.week_date.isoformat()
```

- [ ] **Step 4: Update SYSTEM_TAGS**

In `src/bute/models.py` line 34, change:

```python
SYSTEM_TAGS = {"goal", "today", "thisweek", "habit"}
```

to:

```python
SYSTEM_TAGS = {"goal", "habit"}
```

- [ ] **Step 5: Read new fields in load_entry()**

In `src/bute/storage.py`, add `"focus_date"` and `"week_date"` to the `known_keys` set at line 67:

```python
    known_keys = {
        "id", "type", "created", "status", "important",
        "due", "date", "time", "repeat", "tags", "completions",
        "focus_date", "week_date",
    }
```

And add to the `Entry()` constructor call (after `repeat=` at line 87):

```python
        focus_date=_parse_date(post.metadata.get("focus_date")),
        week_date=_parse_date(post.metadata.get("week_date")),
```

- [ ] **Step 6: Run tests to verify nothing breaks**

Run: `uv run pytest tests/test_action.py tests/test_views.py -x -q`
Expected: All pass (new fields default to None, no behavior change yet)

- [ ] **Step 7: Commit**

```bash
git add src/bute/models.py src/bute/storage.py
git commit -m "feat: add focus_date and week_date fields to Entry model"
```

---

### Task 2: Add columns to SQLite index

**Files:**
- Modify: `src/bute/db.py:79-97` (schema)
- Modify: `src/bute/db.py:249-290` (upsert)
- Modify: `src/bute/db.py:305-407` (query)

- [ ] **Step 1: Add columns to schema**

In `src/bute/db.py`, add two columns to the CREATE TABLE at line 91 (before `extra_meta`):

```python
            focus_date     TEXT,
            week_date      TEXT,
```

And add indexes after line 97:

```python
        CREATE INDEX IF NOT EXISTS idx_focus_date ON entries(focus_date);
        CREATE INDEX IF NOT EXISTS idx_week_date ON entries(week_date);
```

- [ ] **Step 2: Update upsert_entry()**

In `src/bute/db.py` `upsert_entry()`, add variables after `sched_date_str`:

```python
    focus_date_str = entry.focus_date.isoformat() if entry.focus_date else None
    week_date_str = entry.week_date.isoformat() if entry.week_date else None
```

Update the INSERT statement to include the new columns and values. Add `focus_date, week_date` to the column list and `focus_date_str, week_date_str` to the values tuple (before `created_str`).

- [ ] **Step 3: Add query filters**

In `src/bute/db.py` `query_entries()`, add new keyword parameters:

```python
    focus_date: str | None = None,
    week_date: str | None = None,
    has_focus_date: bool = False,
    has_week_date: bool = False,
```

And add conditions:

```python
    if focus_date is not None:
        conditions.append("focus_date = ?")
        params.append(focus_date)

    if week_date is not None:
        conditions.append("week_date = ?")
        params.append(week_date)

    if has_focus_date:
        conditions.append("focus_date IS NOT NULL")

    if has_week_date:
        conditions.append("week_date IS NOT NULL")
```

- [ ] **Step 4: Rebuild the index**

The schema changed, so existing DBs need a rebuild. Run:

```bash
uv run bt rebuild
```

This drops and recreates the index from .md files, picking up the new columns.

- [ ] **Step 5: Commit**

```bash
git add src/bute/db.py
git commit -m "feat: add focus_date and week_date columns to SQLite index"
```

---

### Task 3: Update capture to use date fields instead of tags

**Files:**
- Modify: `src/bute/commands/capture.py:96-106`
- Modify: `src/bute/commands/capture.py:171-178`
- Modify: `src/bute/ritual_ops.py:240-256` (process_dump_line)

- [ ] **Step 1: Add _this_monday helper**

In `src/bute/commands/capture.py`, add near the top (after imports):

```python
from datetime import timedelta

def _this_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())
```

- [ ] **Step 2: Update inline capture auto-tagging**

In `src/bute/commands/capture.py`, replace lines 96-106:

```python
    # Auto-tag tasks based on flags:
    #   default  → @thisweek + @today (Focus Log)
    #   -l       → @thisweek only (Task log, not today)
    #   -b       → no focus tags (Backlog)
    has_future_date = entry.scheduled_date and entry.scheduled_date > date.today()
    has_future_due = entry.due and entry.due > date.today()
    if entry.type == EntryType.TASK and not backlog and not has_future_date and not has_future_due:
        if "thisweek" not in entry.tags:
            entry.tags.append("thisweek")
        if not later and "today" not in entry.tags:
            entry.tags.append("today")
```

with:

```python
    # Set focus dates on tasks based on flags:
    #   default  → focus_date + week_date (Focus Log)
    #   -l       → week_date only (Task log, not today)
    #   -b       → no focus dates (Backlog)
    has_future_date = entry.scheduled_date and entry.scheduled_date > date.today()
    has_future_due = entry.due and entry.due > date.today()
    if entry.type == EntryType.TASK and not backlog and not has_future_date and not has_future_due:
        entry.week_date = _this_monday()
        if not later:
            entry.focus_date = date.today()
```

- [ ] **Step 3: Update editor capture auto-tagging**

In `src/bute/commands/capture.py`, replace lines 171-178:

```python
        # Auto-tag tasks (same logic as inline capture)
        has_future_date = edited.scheduled_date and edited.scheduled_date > date.today()
        has_future_due = edited.due and edited.due > date.today()
        if edited.type == EntryType.TASK and not has_future_date and not has_future_due:
            if "thisweek" not in edited.tags:
                edited.tags.append("thisweek")
            if "today" not in edited.tags:
                edited.tags.append("today")
```

with:

```python
        # Set focus dates on tasks (same logic as inline capture)
        has_future_date = edited.scheduled_date and edited.scheduled_date > date.today()
        has_future_due = edited.due and edited.due > date.today()
        if edited.type == EntryType.TASK and not has_future_date and not has_future_due:
            from bute.commands.capture import _this_monday
            edited.week_date = _this_monday()
            edited.focus_date = date.today()
```

- [ ] **Step 4: Update process_dump_line in ritual_ops.py**

In `src/bute/ritual_ops.py`, replace lines 251-255:

```python
    # Auto-tag tasks (e.g. @thisweek during rituals)
    if auto_tags and entry.type == EntryType.TASK:
        for tag in auto_tags:
            if tag not in entry.tags:
                entry.tags.append(tag)
```

with:

```python
    # Set week_date on tasks captured during rituals
    if entry.type == EntryType.TASK:
        from datetime import timedelta
        today = date.today()
        entry.week_date = today - timedelta(days=today.weekday())
```

Also update the caller in `wp_cmd` (rituals.py line 319) — change:
```python
entry = process_dump_line(f"t {line}", config, auto_tags=["thisweek"])
```
to:
```python
entry = process_dump_line(f"t {line}", config)
```

And update `process_dump_line` signature to remove `auto_tags` parameter.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/ -x -q --ignore=tests/test_habit_storage.py --ignore=tests/test_export.py --ignore=tests/test_rituals.py --ignore=tests/test_tour.py`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/bute/commands/capture.py src/bute/ritual_ops.py src/bute/commands/rituals.py
git commit -m "feat: capture sets focus_date/week_date instead of @today/@thisweek tags"
```

---

### Task 4: Update Focus Log and weekly task queries

**Files:**
- Modify: `src/bute/ritual_ops.py:46-114` (get_daily_log)
- Modify: `src/bute/ritual_ops.py:196-209` (get_weekly_active_tasks)
- Modify: `src/bute/ritual_ops.py:263-297` (set/clear functions)

- [ ] **Step 1: Update get_daily_log() to filter on focus_date**

In `src/bute/ritual_ops.py`, replace the task filter at line 60-63:

```python
        if e.type == EntryType.TASK:
            # Only active tasks tagged @today (exclude habits — shown separately)
            if "today" in e.tags and e.status == TaskStatus.ACTIVE and "habit" not in e.tags:
                result.append(e)
```

with:

```python
        if e.type == EntryType.TASK:
            # Only active tasks with focus_date == today (exclude habits)
            if e.focus_date == today and e.status == TaskStatus.ACTIVE and "habit" not in e.tags:
                result.append(e)
```

- [ ] **Step 2: Update the cross-day @today query**

Replace lines 72-80:

```python
    # Also include active tasks tagged @today but created on a different day
    from bute.storage import query_and_load
    today_tasks = query_and_load(config, type="task", status="active", tag="today")
    today_tasks = [e for e in today_tasks if e.created.date() != today and "habit" not in e.tags]
    seen = {e.id for e in result}
    for e in today_tasks:
        if e.id not in seen:
            seen.add(e.id)
            result.append(e)
```

with:

```python
    # Also include active tasks with focus_date == today but created on a different day
    from bute.storage import query_and_load
    today_tasks = query_and_load(config, type="task", status="active", focus_date=today.isoformat())
    today_tasks = [e for e in today_tasks if e.created.date() != today and "habit" not in e.tags]
    seen = {e.id for e in result}
    for e in today_tasks:
        if e.id not in seen:
            seen.add(e.id)
            result.append(e)
```

- [ ] **Step 3: Update get_weekly_active_tasks()**

Replace lines 196-209:

```python
def get_weekly_active_tasks(config=None) -> list[Entry]:
    """Active tasks selected for this week (@thisweek tag).

    Falls back to all active tasks if none are tagged @thisweek
    (e.g. user hasn't run bt wp yet). Excludes habits — they have
    their own view (bt streak).
    """
    from bute.storage import query_and_load
    weekly = query_and_load(config, type="task", status="active", tag="thisweek")
    weekly = [e for e in weekly if "habit" not in e.tags]
    if weekly:
        return weekly
    fallback = get_all_active_tasks(config)
    return [e for e in fallback if "habit" not in e.tags]
```

with:

```python
def get_weekly_active_tasks(config=None) -> list[Entry]:
    """Active tasks selected for this week (week_date == this Monday).

    Falls back to all active tasks if none have week_date set
    (e.g. user hasn't run bt wp yet). Excludes habits.
    """
    from datetime import timedelta
    from bute.storage import query_and_load
    this_monday = date.today() - timedelta(days=date.today().weekday())
    weekly = query_and_load(config, type="task", status="active", week_date=this_monday.isoformat())
    weekly = [e for e in weekly if "habit" not in e.tags]
    if weekly:
        return weekly
    fallback = get_all_active_tasks(config)
    return [e for e in fallback if "habit" not in e.tags]
```

- [ ] **Step 4: Update set_weekly_selection()**

Replace lines 263-277:

```python
def set_weekly_selection(entry_ids: list[str], config=None) -> int:
    """Tag entries with +thisweek. Returns count tagged."""
    from bute.storage import entry_path_from_id, load_entry

    count = 0
    for eid in entry_ids:
        path = entry_path_from_id(eid, config)
        if path is None:
            continue
        entry = load_entry(path)
        if "thisweek" not in entry.tags:
            entry.tags.append("thisweek")
        update_entry(entry, config)
        count += 1
    return count
```

with:

```python
def set_weekly_selection(entry_ids: list[str], config=None) -> int:
    """Set week_date on entries. Returns count updated."""
    from datetime import timedelta
    from bute.storage import entry_path_from_id, load_entry

    this_monday = date.today() - timedelta(days=date.today().weekday())
    count = 0
    for eid in entry_ids:
        path = entry_path_from_id(eid, config)
        if path is None:
            continue
        entry = load_entry(path)
        entry.week_date = this_monday
        update_entry(entry, config)
        count += 1
    return count
```

- [ ] **Step 5: Replace clear functions**

Replace `clear_weekly_selection()` (lines 280-287):

```python
def clear_weekly_selection(config=None) -> int:
    """Clear week_date from all entries. Returns count cleared."""
    from bute.storage import query_and_load
    entries = query_and_load(config, has_week_date=True)
    for entry in entries:
        entry.week_date = None
        update_entry(entry, config)
    return len(entries)
```

Replace `clear_daily_focus()` (lines 290-297):

```python
def clear_daily_focus(config=None) -> int:
    """Clear focus_date from all entries. Returns count cleared."""
    from bute.storage import query_and_load
    entries = query_and_load(config, has_focus_date=True)
    for entry in entries:
        entry.focus_date = None
        update_entry(entry, config)
    return len(entries)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/ -x -q --ignore=tests/test_habit_storage.py --ignore=tests/test_export.py --ignore=tests/test_rituals.py --ignore=tests/test_tour.py`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/bute/ritual_ops.py
git commit -m "feat: Focus Log and weekly queries use focus_date/week_date fields"
```

---

### Task 5: Update action handlers (later, focus, backlog)

**Files:**
- Modify: `src/bute/commands/action.py:141-183` (handlers)
- Modify: `src/bute/commands/action.py:390-404` (undo for later/backlog/focus)

- [ ] **Step 1: Update handle_later()**

Replace lines 141-149:

```python
def handle_later(entry: Entry, args: list[str], config) -> None:
    """Remove @today tag — defer task to Task log."""
    _require_task(entry, "later")
    if "today" in entry.tags:
        record_undo(entry.id, "later", {"tag": "today"}, config)
        entry.tags.remove("today")
        update_entry(entry, config)
    else:
        Console().print(f"  [dim]Not in today's log[/dim]")
```

with:

```python
def handle_later(entry: Entry, args: list[str], config) -> None:
    """Clear focus_date — defer task to Task log."""
    _require_task(entry, "later")
    if entry.focus_date is not None:
        record_undo(entry.id, "later", {"focus_date": entry.focus_date.isoformat()}, config)
        entry.focus_date = None
        update_entry(entry, config)
    else:
        Console().print(f"  [dim]Not in today's log[/dim]")
```

- [ ] **Step 2: Update handle_focus()**

Replace lines 152-166:

```python
def handle_focus(entry: Entry, args: list[str], config) -> None:
    """Add @today and @thisweek — pull task into Focus Log."""
    _require_task(entry, "focus")
    added = []
    if "thisweek" not in entry.tags:
        entry.tags.append("thisweek")
        added.append("thisweek")
    if "today" not in entry.tags:
        entry.tags.append("today")
        added.append("today")
    if added:
        record_undo(entry.id, "focus", {"tags": added}, config)
        update_entry(entry, config)
    else:
        Console().print(f"  [dim]Already in Focus Log[/dim]")
```

with:

```python
def handle_focus(entry: Entry, args: list[str], config) -> None:
    """Set focus_date and week_date — pull task into Focus Log."""
    from datetime import timedelta
    _require_task(entry, "focus")
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    if entry.focus_date == today and entry.week_date == this_monday:
        Console().print(f"  [dim]Already in Focus Log[/dim]")
        return
    prev = {
        "focus_date": entry.focus_date.isoformat() if entry.focus_date else None,
        "week_date": entry.week_date.isoformat() if entry.week_date else None,
    }
    record_undo(entry.id, "focus", prev, config)
    entry.focus_date = today
    entry.week_date = this_monday
    update_entry(entry, config)
```

- [ ] **Step 3: Update handle_backlog()**

Replace lines 169-183:

```python
def handle_backlog(entry: Entry, args: list[str], config) -> None:
    """Remove @today and @thisweek — send task to Backlog."""
    _require_task(entry, "backlog")
    removed = []
    if "today" in entry.tags:
        entry.tags.remove("today")
        removed.append("today")
    if "thisweek" in entry.tags:
        entry.tags.remove("thisweek")
        removed.append("thisweek")
    if removed:
        record_undo(entry.id, "backlog", {"tags": removed}, config)
        update_entry(entry, config)
    else:
        Console().print(f"  [dim]Already in backlog[/dim]")
```

with:

```python
def handle_backlog(entry: Entry, args: list[str], config) -> None:
    """Clear focus_date and week_date — send task to Backlog."""
    _require_task(entry, "backlog")
    if entry.focus_date is None and entry.week_date is None:
        Console().print(f"  [dim]Already in backlog[/dim]")
        return
    prev = {
        "focus_date": entry.focus_date.isoformat() if entry.focus_date else None,
        "week_date": entry.week_date.isoformat() if entry.week_date else None,
    }
    record_undo(entry.id, "backlog", prev, config)
    entry.focus_date = None
    entry.week_date = None
    update_entry(entry, config)
```

- [ ] **Step 4: Update undo handlers**

Replace the `later` undo at lines 390-394:

```python
    elif action == "later":
        tag = prev["tag"]
        if tag not in entry.tags:
            entry.tags.append(tag)
        update_entry(entry, config)
```

with:

```python
    elif action == "later":
        from datetime import date as date_type
        entry.focus_date = date_type.fromisoformat(prev["focus_date"]) if prev.get("focus_date") else None
        update_entry(entry, config)
```

Replace the `backlog` undo at lines 395-399:

```python
    elif action == "backlog":
        for tag in prev["tags"]:
            if tag not in entry.tags:
                entry.tags.append(tag)
        update_entry(entry, config)
```

with:

```python
    elif action == "backlog":
        from datetime import date as date_type
        entry.focus_date = date_type.fromisoformat(prev["focus_date"]) if prev.get("focus_date") else None
        entry.week_date = date_type.fromisoformat(prev["week_date"]) if prev.get("week_date") else None
        update_entry(entry, config)
```

Replace the `focus` undo at lines 400-404:

```python
    elif action == "focus":
        for tag in prev["tags"]:
            if tag in entry.tags:
                entry.tags.remove(tag)
        update_entry(entry, config)
```

with:

```python
    elif action == "focus":
        from datetime import date as date_type
        entry.focus_date = date_type.fromisoformat(prev["focus_date"]) if prev.get("focus_date") else None
        entry.week_date = date_type.fromisoformat(prev["week_date"]) if prev.get("week_date") else None
        update_entry(entry, config)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_action.py -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/bute/commands/action.py
git commit -m "feat: later/focus/backlog use focus_date/week_date instead of tags"
```

---

### Task 6: Update rituals (dp, wp)

**Files:**
- Modify: `src/bute/commands/rituals.py:29-95` (dp_cmd)
- Modify: `src/bute/commands/rituals.py:288-381` (wp_cmd)

- [ ] **Step 1: Update dp_cmd picker and tagging**

In `dp_cmd`, replace the checkbox checked logic at lines 60-66:

```python
                for e in yesterday:
                    label = f"\u21a9 {e.body}"
                    choices.append(questionary.Choice(
                        label, value=e.id, checked="today" in e.tags,
                    ))
                for e in pool:
                    choices.append(questionary.Choice(
                        e.body, value=e.id, checked="today" in e.tags,
                    ))
```

with:

```python
                today = date.today()
                for e in yesterday:
                    label = f"\u21a9 {e.body}"
                    choices.append(questionary.Choice(
                        label, value=e.id, checked=e.focus_date == today,
                    ))
                for e in pool:
                    choices.append(questionary.Choice(
                        e.body, value=e.id, checked=e.focus_date == today,
                    ))
```

Replace the selection tagging at lines 75-86:

```python
                    selected_set = set(selected)
                    for e in all_tasks:
                        path = entry_path_from_id(e.id, config)
                        if not path:
                            continue
                        entry = load_entry(path)
                        if e.id in selected_set and "today" not in entry.tags:
                            entry.tags.append("today")
                            update_entry(entry, config)
                        elif e.id not in selected_set and "today" in entry.tags:
                            entry.tags.remove("today")
                            update_entry(entry, config)
```

with:

```python
                    today = date.today()
                    selected_set = set(selected)
                    for e in all_tasks:
                        path = entry_path_from_id(e.id, config)
                        if not path:
                            continue
                        entry = load_entry(path)
                        if e.id in selected_set and entry.focus_date != today:
                            entry.focus_date = today
                            update_entry(entry, config)
                        elif e.id not in selected_set and entry.focus_date is not None:
                            entry.focus_date = None
                            update_entry(entry, config)
```

- [ ] **Step 2: Update wp_cmd carryover detection**

Replace lines 298-301:

```python
    active = get_all_active_tasks(config)
    carryover = [e for e in active if "thisweek" in e.tags]
    carryover_ids = {e.id for e in carryover}
    backlog = [e for e in active if e.id not in carryover_ids]
```

with:

```python
    from datetime import timedelta
    this_monday = date.today() - timedelta(days=date.today().weekday())
    active = get_all_active_tasks(config)
    carryover = [e for e in active if e.week_date is not None]
    carryover_ids = {e.id for e in carryover}
    backlog = [e for e in active if e.id not in carryover_ids]
```

And the same reload block at lines 326-330:

```python
            active = get_all_active_tasks(config)
            carryover = [e for e in active if "thisweek" in e.tags]
            carryover_ids = {e.id for e in carryover}
            backlog = [e for e in active if e.id not in carryover_ids]
```

with:

```python
            active = get_all_active_tasks(config)
            carryover = [e for e in active if e.week_date is not None]
            carryover_ids = {e.id for e in carryover}
            backlog = [e for e in active if e.id not in carryover_ids]
```

- [ ] **Step 3: Remove auto_tags from dump line call**

In `wp_cmd` line 319, change:

```python
entry = process_dump_line(f"t {line}", config, auto_tags=["thisweek"])
```

to:

```python
entry = process_dump_line(f"t {line}", config)
```

- [ ] **Step 4: Update wp_cmd imports**

In `rituals.py` imports (line 13-20), remove `clear_weekly_selection` from the import since it's still used at line 373 — actually keep it, as the function still exists (just uses week_date now). No import change needed.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/ -x -q --ignore=tests/test_habit_storage.py --ignore=tests/test_export.py --ignore=tests/test_tour.py`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/bute/commands/rituals.py
git commit -m "feat: dp/wp rituals use focus_date/week_date instead of tags"
```

---

### Task 7: Update display and CLI

**Files:**
- Modify: `src/bute/display.py:52,127`
- Modify: `src/bute/cli.py:499`
- Modify: `src/bute/commands/tour.py:373`
- Modify: `src/bute/commands/chat.py` (handle_later/focus/backlog inline actions)

- [ ] **Step 1: Remove hide_tags from Focus Log display**

In `src/bute/cli.py` line 499, change:

```python
            display_entry_list(entries, title, hide_tags={"today", "thisweek"})
```

to:

```python
            display_entry_list(entries, title)
```

- [ ] **Step 2: Remove hide_tags from tour**

In `src/bute/commands/tour.py` line 373, change:

```python
    display_entry_list(entries, f"Focus Log — {date.today().strftime('%a %b %d')}", hide_tags={"today", "thisweek"})
```

to:

```python
    display_entry_list(entries, f"Focus Log — {date.today().strftime('%a %b %d')}")
```

- [ ] **Step 3: Update chat.py inline actions**

In `src/bute/commands/chat.py`, find the inline action handling for `later`, `focus`, `backlog` that references tags. These go through `ACTION_HANDLERS` dict which calls the updated functions — no change needed if chat.py delegates to action.py handlers. Verify by checking the chat.py action dispatch uses `ACTION_HANDLERS`.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -x -q --ignore=tests/test_habit_storage.py --ignore=tests/test_export.py --ignore=tests/test_tour.py`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/bute/cli.py src/bute/commands/tour.py src/bute/display.py
git commit -m "feat: remove @today/@thisweek from display and hide_tags"
```

---

### Task 8: Migration script and cleanup

**Files:**
- Modify: existing entries on disk (via script)
- Modify: `src/bute/ritual_ops.py` (remove auto_tags parameter from process_dump_line)

- [ ] **Step 1: Run migration**

Run a one-time Python script to convert existing tagged entries:

```python
uv run python -c "
import os
from datetime import date, timedelta
from bute.config import load_config
from bute.storage import query_and_load, update_entry, entry_path

config = load_config()
today = date.today()
this_monday = today - timedelta(days=today.weekday())

# Migrate @today → focus_date
tagged_today = query_and_load(config, tag='today')
for e in tagged_today:
    e.focus_date = today
    e.tags.remove('today')
    p = entry_path(e, config)
    mtime = p.stat().st_mtime
    update_entry(e, config)
    os.utime(p, (mtime, mtime))  # preserve mtime
print(f'Migrated {len(tagged_today)} @today entries')

# Migrate @thisweek → week_date
tagged_week = query_and_load(config, tag='thisweek')
for e in tagged_week:
    e.week_date = this_monday
    e.tags.remove('thisweek')
    p = entry_path(e, config)
    mtime = p.stat().st_mtime
    update_entry(e, config)
    os.utime(p, (mtime, mtime))  # preserve mtime
print(f'Migrated {len(tagged_week)} @thisweek entries')
"
```

- [ ] **Step 2: Rebuild index**

```bash
uv run bt rebuild
```

- [ ] **Step 3: Verify Focus Log works**

```bash
bt
```

Expected: Focus Log shows the same entries as before, with no `@today`/`@thisweek` tags visible anywhere.

- [ ] **Step 4: Verify Task Log works**

```bash
bt t
```

Expected: Shows tasks with `week_date` set to this week's Monday.

- [ ] **Step 5: Verify actions work**

```bash
bt t
bt 1 later    # should remove from Focus Log
bt 1 focus    # should add back
bt 1 backlog  # should remove from both views
```

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -x -q --ignore=tests/test_habit_storage.py --ignore=tests/test_export.py --ignore=tests/test_tour.py`
Expected: All pass

- [ ] **Step 7: Reinstall and final smoke test**

```bash
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall
bt
bt t
bt d
bt dp -y
```

- [ ] **Step 8: Update CLAUDE.md backlog item**

Remove the stale `@today`/`@thisweek` backlog item from CLAUDE.md since it's now resolved.

- [ ] **Step 9: Commit and push**

```bash
git add -A
git commit -m "feat: complete migration from @today/@thisweek tags to date fields

Replaces system tags with focus_date and week_date fields on Entry.
Tags no longer rot — old dates expire naturally. Migrated all
existing entries and rebuilt the index."
git push
```
