# Weekly Plan Trigger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic weekly plan triggering to `bt` so that `wp` fires on a configurable day (default Sunday) before `dp`, mirroring the daily plan's trigger-and-gate pattern.

**Architecture:** Two new state functions (`mark_wp_done`, `is_wp_done_this_week`) store the ISO week number in `.wp_date`. A config key `core.wp_day` sets the trigger day. The `bt` no-args block in `cli.py` checks wp before dp. The `wp_cmd` gains carryover highlighting (last week's `@thisweek` tasks shown with `↩`) and calls `mark_wp_done` at the end.

**Tech Stack:** Python, Click, tomlkit, questionary, pytest

---

### Task 1: State Functions — `mark_wp_done` and `is_wp_done_this_week`

**Files:**
- Modify: `src/bute/state.py:40-51` (add after `is_dp_done_today`)
- Test: `tests/test_rituals.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_rituals.py` after the dp tests (line 59), before the `# --- Weekly Plan (wp) command tests ---` comment:

```python
def test_wp_marks_done(runner, tmp_config, tmp_data):
    """wp -y marks weekly plan as done for the current week."""
    from bute.state import is_wp_done_this_week

    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["wp", "--non-interactive"])
    assert result.exit_code == 0
    assert is_wp_done_this_week()


def test_wp_not_done_by_default(tmp_config, tmp_data):
    """wp is not done when no .wp_date file exists."""
    from bute.state import is_wp_done_this_week

    _setup_config(tmp_config, tmp_data)
    assert not is_wp_done_this_week()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rituals.py::test_wp_marks_done tests/test_rituals.py::test_wp_not_done_by_default -v`
Expected: FAIL — `ImportError: cannot import name 'is_wp_done_this_week'`

- [ ] **Step 3: Implement state functions**

Add to `src/bute/state.py` after `is_dp_done_today` (after line 51):

```python
def mark_wp_done(config=None) -> None:
    """Record that weekly plan was completed this week."""
    path = get_data_dir(config) / ".wp_date"
    path.write_text(date.today().strftime("%G-W%V"))


def is_wp_done_this_week(config=None) -> bool:
    """Check if weekly plan was already completed this week."""
    path = get_data_dir(config) / ".wp_date"
    if not path.exists():
        return False
    return path.read_text().strip() == date.today().strftime("%G-W%V")
```

Note: `%G-W%V` produces ISO week strings like `"2026-W15"`. `%G` is the ISO year, `%V` is the ISO week number.

- [ ] **Step 4: Add `mark_wp_done` call to `wp_cmd`**

In `src/bute/commands/rituals.py`, add at the end of `wp_cmd` (after line 361, before the `# --- Recap ---` comment). The call must happen after both the non-interactive and interactive paths:

Replace the end of `wp_cmd` — the section starting from the `except ImportError` block through the end of the function. The current function ends at line 361. Add the `mark_wp_done` call after the try/except block so it runs in all cases:

```python
    except ImportError:
        console.print("  [dim]questionary not available — skipping selection[/dim]")

    from bute.state import mark_wp_done
    mark_wp_done(config)
```

Also add `mark_wp_done` after the early `return` in the non-interactive path. Replace lines 329-335:

```python
    if non_interactive:
        thisweek = [e for e in active if "thisweek" in e.tags]
        if thisweek:
            display_entry_list(thisweek, "This week's tasks")
        else:
            display_entry_list(active, "Task Backlog (none selected for week)")
        from bute.state import mark_wp_done
        mark_wp_done(config)
        return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_rituals.py::test_wp_marks_done tests/test_rituals.py::test_wp_not_done_by_default -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/bute/state.py src/bute/commands/rituals.py tests/test_rituals.py
git commit -m "feat: add mark_wp_done/is_wp_done_this_week state functions"
```

---

### Task 2: Config Key — `core.wp_day`

**Files:**
- Modify: `src/bute/config.py:69-103` (add `wp_day` to `default_config`)
- Test: `tests/test_rituals.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rituals.py` after the wp state tests:

```python
def test_wp_day_config_default(tmp_config, tmp_data):
    """wp_day defaults to sunday when not set in config."""
    _setup_config(tmp_config, tmp_data)
    from bute.config import load_config
    config = load_config()
    wp_day = config.get("core", {}).get("wp_day", "sunday")
    assert wp_day == "sunday"
```

- [ ] **Step 2: Run test to verify it passes (it should — default fallback)**

Run: `uv run pytest tests/test_rituals.py::test_wp_day_config_default -v`
Expected: PASS (the fallback `"sunday"` is hardcoded in the test itself — this test documents the contract)

- [ ] **Step 3: Add `wp_day` to `default_config`**

In `src/bute/config.py`, in the `default_config` function, add `wp_day` to the `core` table. After line 84 (`core.add("data_dir", "~/bullet-terminal")`), add:

```python
    core.add(tomlkit.comment("Day to trigger weekly plan: monday-sunday"))
    core.add("wp_day", "sunday")
```

- [ ] **Step 4: Add helper function to resolve wp_day to weekday number**

Add to `src/bute/config.py` after `ensure_data_dirs` (after line 130):

```python
DAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def get_wp_day(config=None) -> int:
    """Return the weekday number (0=Mon, 6=Sun) for weekly plan trigger."""
    if config and "core" in config and "wp_day" in config["core"]:
        day_name = config["core"]["wp_day"].lower()
        return DAY_NAMES.get(day_name, 6)
    return 6  # default: Sunday
```

- [ ] **Step 5: Write test for `get_wp_day`**

Add to `tests/test_rituals.py`:

```python
def test_get_wp_day_default():
    """get_wp_day returns 6 (Sunday) when no config."""
    from bute.config import get_wp_day
    assert get_wp_day() == 6


def test_get_wp_day_from_config(tmp_config, tmp_data):
    """get_wp_day reads from config."""
    from bute.config import get_wp_day
    _setup_config(tmp_config, tmp_data)
    from bute.config import load_config
    config = load_config()
    config["core"]["wp_day"] = "monday"
    assert get_wp_day(config) == 0
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_rituals.py::test_wp_day_config_default tests/test_rituals.py::test_get_wp_day_default tests/test_rituals.py::test_get_wp_day_from_config -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/bute/config.py tests/test_rituals.py
git commit -m "feat: add core.wp_day config key with get_wp_day helper"
```

---

### Task 3: CLI Trigger — wp check before dp in `bt` no-args

**Files:**
- Modify: `src/bute/cli.py:464-501`
- Test: `tests/test_rituals.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rituals.py`:

```python
def test_bt_triggers_wp_on_trigger_day(runner, tmp_config, tmp_data, monkeypatch):
    """bt (no args) triggers wp when it's the trigger day and wp not done."""
    from datetime import date as _date

    _setup_config(tmp_config, tmp_data)
    # Create a task so wp has something to show
    e = Entry.create(EntryType.TASK, "plan this", tags=["thisweek"])
    save_entry(e)

    # Mock today to be Sunday (weekday 6)
    class FakeDate(_date):
        @classmethod
        def today(cls):
            # Find next Sunday from real today
            real = _date.today()
            days_ahead = 6 - real.weekday()
            if days_ahead < 0:
                days_ahead += 7
            return real + __import__("datetime").timedelta(days=days_ahead)

    monkeypatch.setattr("bute.state.date", FakeDate)
    monkeypatch.setattr("bute.config.date", FakeDate) if hasattr(__import__("bute.config"), "date") else None

    result = runner.invoke(main, ["wp", "--non-interactive"])
    assert result.exit_code == 0
    assert "Plan" in result.output

    from bute.state import is_wp_done_this_week
    assert is_wp_done_this_week()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_rituals.py::test_bt_triggers_wp_on_trigger_day -v`
Expected: PASS (this test calls wp directly — it verifies the mark_wp_done integration from Task 1)

- [ ] **Step 3: Write the trigger test**

Add to `tests/test_rituals.py`:

```python
def test_bt_noargs_chains_wp_then_dp(runner, tmp_config, tmp_data, monkeypatch):
    """bt (no args) on trigger day runs wp then dp in sequence."""
    _setup_config(tmp_config, tmp_data)
    # Mark tour as done so bt doesn't show tour
    from bute.config import TOUR_DONE
    TOUR_DONE.parent.mkdir(parents=True, exist_ok=True)
    TOUR_DONE.touch()

    # Force wp_day to today's weekday so trigger fires
    from bute.config import load_config, save_config
    config = load_config()
    import datetime
    today_name = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][date.today().weekday()]
    config["core"]["wp_day"] = today_name
    save_config(config)

    e = Entry.create(EntryType.TASK, "weekly task")
    save_entry(e)

    # bt (no args) should trigger wp (non-interactive fallback) then dp
    result = runner.invoke(main, [], input="\n")
    assert result.exit_code == 0
    # wp should have run (Plan header) and dp should have run (Daily Plan header)
    assert "Plan" in result.output
```

- [ ] **Step 4: Implement the trigger in `cli.py`**

In `src/bute/cli.py`, replace lines 475-501 (the dp check block) with the wp-then-dp cascade:

```python
        from bute.config import get_wp_day
        from bute.state import is_wp_done_this_week

        # Weekly plan trigger — on or after trigger day, if not done this week
        wp_day = get_wp_day(config)
        if date.today().weekday() >= wp_day and not is_wp_done_this_week(config):
            from bute.commands.rituals import wp_cmd
            ctx.invoke(wp_cmd, non_interactive=False)

        from bute.state import is_dp_done_today
        if is_dp_done_today(config):
            # Daily plan already done — show Focus Log
            from bute.display import display_entry_list
            from bute.ritual_ops import get_daily_log
            from bute.state import save_state

            entries = get_daily_log(config)
            from bute.models import EntryType as _ET
            has_tasks = any(e.type == _ET.TASK for e in entries)
            title = f"Focus Log — {date.today().strftime('%a %b %d')}"
            if not has_tasks:
                title = f"[strike]{title}[/strike]"
            display_entry_list(entries, title, hide_tags={"today", "thisweek"})

            # Show habits
            from bute.commands.views import _show_habits
            habit_names = _show_habits(config, len(entries))

            # Random old journal whisper (numbered after entries + habits)
            journal_id = _show_random_journal(config, len(entries) + len(habit_names))

            save_state("ls", [e.id for e in entries], config, habits=habit_names, extra_entries=[journal_id] if journal_id else None)

        else:
            from bute.commands.rituals import dp_cmd
            ctx.invoke(dp_cmd)
```

Note: the existing `from datetime import date` import at line 478 needs to move before the wp check. Since this block already has `config = ctx.obj["config"]` at line 467, and the tour check imports `date` for the Focus Log, add `from datetime import date` right after the tour check (before the wp check).

- [ ] **Step 5: Run all ritual tests**

Run: `uv run pytest tests/test_rituals.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/bute/cli.py tests/test_rituals.py
git commit -m "feat: trigger wp automatically before dp on configured day"
```

---

### Task 4: WP Carryover Highlight — `↩` for last week's tasks

**Files:**
- Modify: `src/bute/commands/rituals.py:288-362`
- Test: `tests/test_rituals.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rituals.py`:

```python
def test_wp_shows_carryover_icon(runner, tmp_config, tmp_data):
    """wp shows ↩ for tasks that had @thisweek from last week."""
    _setup_config(tmp_config, tmp_data)
    e1 = Entry.create(EntryType.TASK, "carried over", tags=["thisweek"])
    e2 = Entry.create(EntryType.TASK, "fresh task")
    save_entry(e1)
    save_entry(e2)

    # Non-interactive mode shows the task list — carryover tasks first
    result = runner.invoke(main, ["wp", "--non-interactive"])
    assert result.exit_code == 0
    assert "carried over" in result.output
    assert "fresh task" in result.output
```

- [ ] **Step 2: Run test to verify it passes (baseline)**

Run: `uv run pytest tests/test_rituals.py::test_wp_shows_carryover_icon -v`
Expected: PASS (both tasks already show — this is a baseline)

- [ ] **Step 3: Refactor `wp_cmd` to separate carryover from backlog**

Replace the entire `wp_cmd` function in `src/bute/commands/rituals.py` (lines 288-361):

```python
@click.command("wp")
@click.option("-y", "--non-interactive", is_flag=True, help="Skip prompts.")
@click.pass_context
def wp_cmd(ctx, non_interactive):
    """Weekly ritual — dump tasks, then select for the week."""
    config = ctx.obj.get("config")

    display_ritual_header("Plan", "Review your backlog and select for this week")

    # Separate carryover (@thisweek from last week) from fresh backlog
    active = get_all_active_tasks(config)
    carryover = [e for e in active if "thisweek" in e.tags]
    carryover_ids = {e.id for e in carryover}
    backlog = [e for e in active if e.id not in carryover_ids]

    all_tasks = carryover + backlog

    if not all_tasks and not non_interactive:
        # Show backlog empty but still allow dump
        console.print("  [dim]Backlog is empty.[/dim]")

    # Dump phase — add new tasks
    if not non_interactive:
        console.print("\n  [dim]Add tasks? One per line, blank when done.[/dim]")
        added = 0
        while True:
            try:
                line = click.prompt("", prompt_suffix="  > ", default="", show_default=False)
            except (EOFError, click.Abort):
                break
            if not line.strip():
                break
            entry = process_dump_line(f"t {line}", config, auto_tags=["thisweek"])
            if entry:
                confirm_capture(entry)
                added += 1
        if added:
            console.print(f"  [green]{added} tasks added.[/green]")
            # Reload with new tasks
            active = get_all_active_tasks(config)
            carryover = [e for e in active if "thisweek" in e.tags]
            carryover_ids = {e.id for e in carryover}
            backlog = [e for e in active if e.id not in carryover_ids]
            all_tasks = carryover + backlog

    if not all_tasks:
        console.print("  [dim]No tasks to plan. Capture some first.[/dim]")
        from bute.state import mark_wp_done
        mark_wp_done(config)
        return

    if non_interactive:
        if carryover:
            display_entry_list(carryover, "This week's tasks")
        if backlog:
            display_entry_list(backlog, "Backlog")
        if not carryover and not backlog:
            console.print("  [dim]No tasks.[/dim]")
        from bute.state import mark_wp_done
        mark_wp_done(config)
        return

    # Selection phase
    try:
        import questionary

        choices = []
        for e in carryover:
            label = f"\u21a9 {e.body}"
            choices.append(questionary.Choice(
                label, value=e.id, checked=True,
            ))
        for e in backlog:
            choices.append(questionary.Choice(
                e.body, value=e.id, checked=False,
            ))

        selected = questionary.checkbox(
            "Select tasks for this week:", choices=choices
        ).ask()

        if selected is None:
            from bute.state import mark_wp_done
            mark_wp_done(config)
            return  # user cancelled

        cleared = clear_weekly_selection(config)
        tagged = set_weekly_selection(selected, config)
        console.print(f"\n  [green]{tagged} tasks selected for this week[/green]")

    except ImportError:
        console.print("  [dim]questionary not available — skipping selection[/dim]")

    from bute.state import mark_wp_done
    mark_wp_done(config)
```

- [ ] **Step 4: Run all ritual tests**

Run: `uv run pytest tests/test_rituals.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/rituals.py tests/test_rituals.py
git commit -m "feat: wp shows carryover tasks with arrow icon, mirrors dp pattern"
```

---

### Task 5: Update CLAUDE.md and Full Test Run

**Files:**
- Modify: `CLAUDE.md`
- Run: full test suite

- [ ] **Step 1: Update CLAUDE.md**

In `CLAUDE.md`, update the Rituals section (line 166-174) to reflect the new wp trigger:

```
**Rituals**:
```
bute                # entry point — weekly plan (on trigger day) → daily plan → Focus Log
bute dp             # morning ritual — pick today's tasks
bute wp             # weekly plan — select tasks for the week (auto-triggers on configured day)
bute recap week     # AI analysis of a period (day, week, month, year)
bute habit <name>   # track habits
bute streak         # habit streaks and 30-day stats
```
```

Also update the Design Decisions section. Find the line about `bute` with no args (line 188) and update:

```
- **`bute` with no args** = planning entry point. On the trigger day (default Sunday), runs weekly plan then daily plan. Other days, runs daily plan only. If both are done, shows Focus Log.
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 3: Reinstall bt globally**

Run: `uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall`

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for wp trigger feature"
```
