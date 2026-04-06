# Guided Tour Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive guided tour that runs on first `bt` invocation when no entries exist, teaching the user every core concept by having them type real commands.

**Architecture:** A new `tour.py` module defines 11 phases as data (intro text, steps with prompts/validation/feedback). A REPL loop iterates through phases and steps, executing each user command via Click's `main()` and validating the result. `cli.py` gains a lightweight check: no entries + no `.tour_done` marker → launch tour.

**Tech Stack:** Click (CLI framework), Rich (terminal rendering), existing bt command infrastructure.

**Spec:** `docs/superpowers/specs/2026-04-05-guided-tour-design.md`

---

## File Structure

| File | Role |
|------|------|
| Create: `src/bute/commands/tour.py` | Phase definitions, validation, coaching REPL loop |
| Modify: `src/bute/cli.py:444-471` | Add tour trigger before dp/Focus Log logic |
| Modify: `src/bute/config.py:7-11` | Add `TOUR_DONE` and `TOUR_PROGRESS` path constants |
| Create: `tests/test_tour.py` | Tests for tour phases, validation, REPL, trigger |

---

### Task 1: Tour state helpers — progress tracking and completion marker

**Files:**
- Modify: `src/bute/config.py:7-11`
- Create: `src/bute/commands/tour.py` (initial skeleton)
- Create: `tests/test_tour.py`

- [ ] **Step 1: Write failing tests for tour state helpers**

```python
# tests/test_tour.py
"""Tests for the guided tour."""

from bute.commands.tour import (
    is_tour_done,
    mark_tour_done,
    load_tour_progress,
    save_tour_progress,
)


def test_tour_not_done_initially(tmp_config):
    assert is_tour_done() is False


def test_mark_tour_done(tmp_config):
    mark_tour_done()
    assert is_tour_done() is True


def test_tour_progress_default(tmp_config):
    assert load_tour_progress() == 0


def test_save_and_load_progress(tmp_config):
    save_tour_progress(5)
    assert load_tour_progress() == 5


def test_mark_done_clears_progress(tmp_config):
    save_tour_progress(7)
    mark_tour_done()
    assert load_tour_progress() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tour.py -v`
Expected: ImportError — `tour` module doesn't exist yet.

- [ ] **Step 3: Add path constants to config.py**

In `src/bute/config.py`, after line 11 (`DEMO_DATA_DIR = ...`), add:

```python
TOUR_DONE = CONFIG_DIR / ".tour_done"
TOUR_PROGRESS = CONFIG_DIR / ".tour_progress"
```

- [ ] **Step 4: Implement tour state helpers**

Create `src/bute/commands/tour.py`:

```python
"""Guided tour — interactive first-run onboarding for bt."""

from bute.config import CONFIG_DIR, TOUR_DONE, TOUR_PROGRESS


def is_tour_done() -> bool:
    """Check if the tour has been completed."""
    return TOUR_DONE.exists()


def mark_tour_done() -> None:
    """Mark the tour as complete. Clears progress file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOUR_DONE.touch()
    if TOUR_PROGRESS.exists():
        TOUR_PROGRESS.unlink()


def load_tour_progress() -> int:
    """Load the current phase index (0-based). Returns 0 if no progress saved."""
    if not TOUR_PROGRESS.exists():
        return 0
    try:
        return int(TOUR_PROGRESS.read_text().strip())
    except (ValueError, OSError):
        return 0


def save_tour_progress(phase: int) -> None:
    """Save the current phase index for resume on Ctrl+C."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOUR_PROGRESS.write_text(str(phase))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tour.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/bute/config.py src/bute/commands/tour.py tests/test_tour.py
git commit -m "feat(tour): add tour state helpers — progress tracking and completion marker"
```

---

### Task 2: Phase and step data model

**Files:**
- Modify: `src/bute/commands/tour.py`
- Modify: `tests/test_tour.py`

- [ ] **Step 1: Write failing tests for phase data model**

Append to `tests/test_tour.py`:

```python
from bute.commands.tour import PHASES, Phase, Step


def test_phases_exist():
    assert len(PHASES) == 11


def test_phase_has_intro_and_steps():
    phase = PHASES[0]
    assert isinstance(phase, Phase)
    assert phase.name == "Tasks"
    assert len(phase.intro) > 0
    assert len(phase.steps) >= 1


def test_step_has_required_fields():
    step = PHASES[0].steps[0]
    assert isinstance(step, Step)
    assert len(step.prompt) > 0
    assert step.validate is not None
    assert len(step.feedback) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tour.py::test_phases_exist -v`
Expected: ImportError — `PHASES`, `Phase`, `Step` not defined.

- [ ] **Step 3: Define Phase and Step dataclasses and all 11 phases**

Add to `src/bute/commands/tour.py`, after the state helper functions:

```python
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Step:
    """A single step within a tour phase."""
    prompt: str          # What to show the user (suggestion text)
    validate: Callable   # fn(user_input: str, config) -> bool
    feedback: str        # Rich markup shown after successful validation
    hint: str = ""       # Extra hint if validation fails


@dataclass
class Phase:
    """A tour phase — intro text + ordered steps."""
    name: str
    intro: str           # Rich markup intro text
    steps: list[Step] = field(default_factory=list)


def _has_new_entry(entry_type: str, config) -> bool:
    """Check if at least one entry of the given type exists."""
    from bute.storage import load_entries_by_filter
    from bute.models import EntryType
    type_map = {"task": EntryType.TASK, "note": EntryType.NOTE,
                "journal": EntryType.JOURNAL, "calendar": EntryType.CALENDAR}
    et = type_map.get(entry_type)
    if not et:
        return False
    entries = load_entries_by_filter(lambda e: e.type == et, config)
    return len(entries) > 0


def _count_entries(config) -> int:
    """Count total entries."""
    from bute.storage import load_entries_by_filter
    return len(load_entries_by_filter(lambda e: True, config))


def _last_entry(config):
    """Return the most recently created entry, or None."""
    from bute.storage import load_entries_by_filter
    entries = load_entries_by_filter(lambda e: True, config)
    return entries[0] if entries else None


def _last_entry_has_tag(config) -> bool:
    """Check if the most recent entry has at least one tag."""
    entry = _last_entry(config)
    return bool(entry and entry.tags)


def _last_entry_is_important(config) -> bool:
    """Check if the most recent entry is marked important."""
    entry = _last_entry(config)
    return bool(entry and entry.important)


def _last_entry_is_type(entry_type: str, config) -> bool:
    """Check if the most recent entry matches the given type."""
    from bute.models import EntryType
    type_map = {"task": EntryType.TASK, "note": EntryType.NOTE,
                "journal": EntryType.JOURNAL, "calendar": EntryType.CALENDAR}
    entry = _last_entry(config)
    return bool(entry and entry.type == type_map.get(entry_type))


def _get_used_tags(config) -> list[str]:
    """Get all tags used across entries, for suggesting in phase 6."""
    from bute.models import SYSTEM_TAGS
    from bute.storage import load_entries_by_filter
    entries = load_entries_by_filter(lambda e: True, config)
    tags = set()
    for e in entries:
        tags.update(e.tags)
    return sorted(tags - SYSTEM_TAGS)


# --- Validation functions ---
# Each takes (user_input: str, config) and returns bool.

def _validate_any_task(user_input, config):
    return _last_entry_is_type("task", config)

def _validate_task_with_tag(user_input, config):
    return _last_entry_is_type("task", config) and _last_entry_has_tag(config)

def _validate_important_task(user_input, config):
    return _last_entry_is_type("task", config) and _last_entry_is_important(config)

def _validate_note_with_tag(user_input, config):
    return _last_entry_is_type("note", config) and _last_entry_has_tag(config)

def _validate_any_journal(user_input, config):
    return _last_entry_is_type("journal", config)

def _validate_journal_with_tag(user_input, config):
    return _last_entry_is_type("journal", config) and _last_entry_has_tag(config)

def _validate_any_calendar(user_input, config):
    return _last_entry_is_type("calendar", config)

def _validate_always(user_input, config):
    """For steps where we just need the user to run a view command."""
    return True


# --- Phase definitions ---

PHASES = [
    # Phase 1: Tasks
    Phase(
        name="Tasks",
        intro="Tasks are things you need to do. The letter [bold cyan]t[/bold cyan] captures a task.",
        steps=[
            Step(
                prompt="Try it — type something like: [bold]t call dentist[/bold]",
                validate=_validate_any_task,
                feedback="That dot means [bold cyan]task[/bold cyan].",
                hint="Type [bold]t[/bold] followed by your task text.",
            ),
            Step(
                prompt="Tags help you organize. Add one with @. Try: [bold]t read book @health[/bold]",
                validate=_validate_task_with_tag,
                feedback="You can filter by tags later.",
                hint="Type [bold]t[/bold] followed by text and [bold]@sometag[/bold].",
            ),
            Step(
                prompt="Mark something urgent with [bold red]![/bold red]. Try: [bold]t! fix the leak @home[/bold]",
                validate=_validate_important_task,
                feedback="The [bold red]![/bold red] marks it important. It'll stand out in every view.",
                hint="Type [bold]t![/bold] followed by your task text.",
            ),
        ],
    ),
    # Phase 2: Notes
    Phase(
        name="Notes",
        intro="Notes are ideas, facts, things worth remembering.",
        steps=[
            Step(
                prompt="Capture a note with [bold yellow]n[/bold yellow]. Try: [bold]n check OAuth token expiry @backend @security[/bold]",
                validate=_validate_note_with_tag,
                feedback="Notes use the dash. Multiple tags work too.",
                hint="Type [bold]n[/bold] followed by text and at least one [bold]@tag[/bold].",
            ),
        ],
    ),
    # Phase 3: Journals
    Phase(
        name="Journals",
        intro="Journals are reflections — what you're thinking or feeling.",
        steps=[
            Step(
                prompt="Type: [bold]j excited to try this[/bold]",
                validate=_validate_any_journal,
                feedback="Journals use the equals sign.",
                hint="Type [bold]j[/bold] followed by what's on your mind.",
            ),
            Step(
                prompt="Journals can have tags too. Try: [bold]j need to be more focused @growth[/bold]",
                validate=_validate_journal_with_tag,
                feedback="Tags work on every entry type.",
                hint="Type [bold]j[/bold] followed by text and [bold]@sometag[/bold].",
            ),
        ],
    ),
    # Phase 4: Calendar
    Phase(
        name="Calendar",
        intro="Calendar events have dates and times. [bold]d:[/bold] sets the date, [bold]t:[/bold] sets the time.",
        steps=[
            Step(
                prompt="Try: [bold]c dentist appointment d:tomorrow t:14.30[/bold]",
                validate=_validate_any_calendar,
                feedback="Calendar events use the [bold green]○[/bold green] signifier.",
                hint="Type [bold]c[/bold] followed by text. Add [bold]d:tomorrow[/bold] and [bold]t:14.30[/bold] for date and time.",
            ),
        ],
    ),
    # Phase 5: Focus Log
    Phase(
        name="Focus Log",
        intro="Let's see everything together.",
        steps=[
            Step(
                prompt="Type: [bold]bt[/bold]",
                validate=_validate_always,
                feedback="This is your [bold]Focus Log[/bold] — your home screen. Everything that matters today, in one place.",
            ),
        ],
    ),
    # Phase 6: Tag Filter
    Phase(
        name="Tag Filter",
        intro="Remember the @tags you've been adding? They work across everything.",
        steps=[
            Step(
                prompt="",  # Filled dynamically with a tag the user actually used
                validate=_validate_always,
                feedback="Tasks, notes, journals, calendar — tags cut across all of them.",
            ),
        ],
    ),
    # Phase 7: Habits
    Phase(
        name="Habits",
        intro="Track daily habits you want to build.",
        steps=[
            Step(
                prompt="Type: [bold]h reading[/bold]",
                validate=_validate_always,
                feedback="Habit tracked. It'll show up in your Focus Log every day.",
                hint="Type [bold]h[/bold] followed by a habit name.",
            ),
        ],
    ),
    # Phase 8: Logs
    Phase(
        name="Logs",
        intro="Logs show everything for a time period — like zooming out.",
        steps=[
            Step(
                prompt="Type: [bold]d[/bold]",
                validate=_validate_always,
                feedback="The daily log shows everything that happened today.",
            ),
            Step(
                prompt="Type: [bold]w[/bold]",
                validate=_validate_always,
                feedback="Same idea, wider lens. [dim]w last[/dim] for last week, [dim]w 14[/dim] for week 14.",
            ),
            Step(
                prompt="Type: [bold]m[/bold]",
                validate=_validate_always,
                feedback="Monthly view. [dim]m jan[/dim] for January, [dim]m 2026[/dim] for a full year.",
            ),
        ],
    ),
    # Phase 9: Views
    Phase(
        name="Views",
        intro="Views filter by entry type — like zooming in.",
        steps=[
            Step(
                prompt="Type: [bold]t[/bold]",
                validate=_validate_always,
                feedback="Just your tasks. [dim]n[/dim] for notes, [dim]b[/dim] for the full backlog.",
            ),
            Step(
                prompt="Type: [bold]b[/bold]",
                validate=_validate_always,
                feedback="The backlog is every active task. [dim]bt t[/dim] shows this week's focus.",
            ),
        ],
    ),
    # Phase 10: Actions
    Phase(
        name="Actions",
        intro="Act on entries by their number. Let's see the list first.",
        steps=[
            Step(
                prompt="Type: [bold]bt[/bold]",
                validate=_validate_always,
                feedback="Each entry has a number. Use it to act.",
            ),
            Step(
                prompt="Type: [bold]1 done[/bold]",
                validate=_validate_always,
                feedback="Done. Strikethrough means completed.",
            ),
            Step(
                prompt="Type: [bold]2 ![/bold]",
                validate=_validate_always,
                feedback="Toggled important. [dim]drop[/dim] consciously deletes, [dim]@tag[/dim] adds a tag.",
            ),
            Step(
                prompt="Type: [bold]bt[/bold]",
                validate=_validate_always,
                feedback="See the changes? That's the capture → view → act loop.",
            ),
        ],
    ),
    # Phase 11: Daily Plan
    Phase(
        name="Daily Plan",
        intro="You've learned the pieces. The Daily Plan ties them together as a morning ritual.",
        steps=[
            Step(
                prompt="Type: [bold]dp[/bold]",
                validate=_validate_always,
                feedback="Start every morning with [bold cyan]bt dp[/bold cyan]. It walks you through planning your day.",
            ),
        ],
    ),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tour.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/tour.py tests/test_tour.py
git commit -m "feat(tour): define Phase/Step data model and all 11 phases"
```

---

### Task 3: Tour REPL loop

**Files:**
- Modify: `src/bute/commands/tour.py`
- Modify: `tests/test_tour.py`

- [ ] **Step 1: Write failing tests for the tour REPL**

Append to `tests/test_tour.py`:

```python
from unittest.mock import patch
from click.testing import CliRunner
from bute.cli import main


def test_tour_runs_on_empty_system(runner, tmp_config, tmp_data):
    """Tour triggers when no entries exist and tour not done."""
    # Simulate user typing /done to exit immediately
    result = runner.invoke(main, [], input="/done\n")
    assert result.exit_code == 0
    assert "Tasks" in result.output  # Phase 1 intro


def test_tour_skips_when_done(runner, tmp_config, tmp_data):
    """Tour does not trigger when .tour_done marker exists."""
    from bute.commands.tour import mark_tour_done
    mark_tour_done()
    # With no entries and tour done, dp would run (and show empty state)
    result = runner.invoke(main, [], input="")
    assert "Tasks are things" not in result.output


def test_tour_skip_command(runner, tmp_config, tmp_data):
    """User can /skip to advance to next phase."""
    result = runner.invoke(main, [], input="/skip\n/done\n")
    assert result.exit_code == 0
    # Should have shown Phase 1 intro, then Phase 2 intro after /skip
    assert "Notes" in result.output


def test_tour_phase1_capture(runner, tmp_config, tmp_data):
    """Capturing a task in phase 1 advances the step."""
    result = runner.invoke(main, [], input="t call dentist\n/done\n")
    assert result.exit_code == 0
    assert "dot means" in result.output  # Phase 1 Step A feedback


def test_tour_outro_shown(runner, tmp_config, tmp_data):
    """Completing all phases shows the outro."""
    # Skip through all 11 phases
    skip_all = "/skip\n" * 11
    result = runner.invoke(main, [], input=skip_all)
    assert result.exit_code == 0
    assert "bt start" in result.output  # Outro mentions cheat sheet
    assert "bt -h" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tour.py::test_tour_runs_on_empty_system -v`
Expected: FAIL — tour REPL not implemented yet.

- [ ] **Step 3: Implement the tour REPL loop**

Add to `src/bute/commands/tour.py`, after the PHASES list:

```python
import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

_console = Console()


def _has_entries(config) -> bool:
    """Check if any entries exist on disk."""
    from bute.config import get_data_dir
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return False
    for month_dir in entries_dir.iterdir():
        if month_dir.is_dir() and any(month_dir.glob("*.md")):
            return True
    return False


def should_run_tour(config) -> bool:
    """Determine if the tour should run: no entries and not completed."""
    return not is_tour_done() and not _has_entries(config)


def _execute_command(args: list[str], ctx: click.Context) -> None:
    """Run a bt command inside the tour REPL."""
    from bute.cli import main as bt_main
    try:
        bt_main(args, standalone_mode=False, parent=ctx)
    except click.exceptions.UsageError as e:
        _console.print(f"  [red]{e.format_message()}[/red]")
    except SystemExit:
        pass
    except Exception as e:
        _console.print(f"  [red]{e}[/red]")


def _show_phase_intro(phase: Phase) -> None:
    """Display the phase intro banner."""
    _console.print()
    title = Text(f" {phase.name} ", style="bold")
    _console.print(Panel(
        Text.from_markup(f"  {phase.intro}"),
        title=title,
        border_style="cyan",
        padding=(0, 1),
    ))
    _console.print()


def _show_step_prompt(step: Step) -> None:
    """Display the step prompt/suggestion."""
    _console.print(f"  {step.prompt}")
    _console.print()


def _show_feedback(step: Step) -> None:
    """Display feedback after a successful step."""
    _console.print()
    _console.print(f"  [green]✓[/green] {step.feedback}")
    _console.print()


def _show_outro() -> None:
    """Display the tour outro."""
    _console.print()
    outro = Text.from_markup(
        "[bold]That's bt.[/bold] Capture fast, act by number, plan each morning.\n"
        "\n"
        "  [bold cyan]bt -i[/bold cyan]      interactive mode (like this tour)\n"
        "  [bold]bt t[/bold] call mom  in the terminal, prefix with bt\n"
        "  [bold]bt init[/bold]     set up AI features (search, chat, analysis)\n"
        "\n"
        "  [dim]Cheat sheet:[/dim] [bold]bt start[/bold]  ·  [dim]Full help:[/dim] [bold]bt -h[/bold]"
    )
    _console.print(Panel(outro, border_style="green", padding=(1, 2)))
    _console.print()


def run_tour(ctx: click.Context) -> None:
    """Run the interactive guided tour."""
    from bute.config import ensure_data_dirs
    config = ctx.obj.get("config")
    ensure_data_dirs(config)

    _console.print()
    _console.print("  [bold]Welcome to bt![/bold] Let's learn the basics by doing.")
    _console.print("  [dim]Type /skip to skip a section, /done to finish early.[/dim]")

    start_phase = load_tour_progress()

    for phase_idx in range(start_phase, len(PHASES)):
        phase = PHASES[phase_idx]
        save_tour_progress(phase_idx)

        # Dynamic prompt for Phase 6 (Tag Filter) — suggest a real tag
        if phase.name == "Tag Filter":
            used_tags = _get_used_tags(config)
            if used_tags:
                tag = used_tags[0]
                phase.steps[0].prompt = f"Type: [bold]@{tag}[/bold]"
            else:
                phase.steps[0].prompt = "Type: [bold]@health[/bold]"

        _show_phase_intro(phase)

        skip_phase = False
        for step in phase.steps:
            if step.prompt:
                _show_step_prompt(step)

            while True:
                try:
                    user_input = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    _console.print()
                    _console.print("  [dim]Tour paused. Run [bold]bt[/bold] to pick up where you left off.[/dim]")
                    save_tour_progress(phase_idx)
                    return

                if not user_input:
                    if step.prompt:
                        _show_step_prompt(step)
                    continue

                if user_input == "/done":
                    mark_tour_done()
                    _show_outro()
                    return

                if user_input == "/skip":
                    skip_phase = True
                    break

                # Parse and execute the command
                args = user_input.split()
                if args and args[0] == "bt":
                    args = args[1:]

                # Snapshot entry count before executing
                count_before = _count_entries(config)

                _execute_command(args, ctx)

                # Validate
                if step.validate(user_input, config):
                    _show_feedback(step)
                    break
                else:
                    # Command ran but didn't match expected action
                    if step.hint:
                        _console.print(f"  [dim]{step.hint}[/dim]")
                    elif step.prompt:
                        _show_step_prompt(step)

            if skip_phase:
                break

    # All phases complete
    mark_tour_done()
    _show_outro()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tour.py -v`
Expected: All tour tests PASS (except `test_tour_runs_on_empty_system` and `test_tour_skips_when_done` — those depend on the `cli.py` trigger, which is Task 4).

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/tour.py tests/test_tour.py
git commit -m "feat(tour): implement coaching REPL loop with phase navigation"
```

---

### Task 4: Wire tour trigger into cli.py

**Files:**
- Modify: `src/bute/cli.py:444-471`
- Modify: `tests/test_tour.py`

- [ ] **Step 1: Write failing test for the CLI trigger**

The tests `test_tour_runs_on_empty_system` and `test_tour_skips_when_done` from Task 3 already cover this. Verify they fail:

Run: `uv run pytest tests/test_tour.py::test_tour_runs_on_empty_system tests/test_tour.py::test_tour_skips_when_done -v`
Expected: FAIL — `cli.py` doesn't invoke the tour yet.

- [ ] **Step 2: Add tour trigger to cli.py main()**

In `src/bute/cli.py`, replace the block at lines 444-471:

```python
    if not ctx.invoked_subcommand:
        from bute.state import is_dyts_done_today

        config = ctx.obj["config"]
        if is_dyts_done_today(config):
            # Daily plan already done — show Focus Log
            ...
        else:
            ctx.invoke(dp_cmd)
```

With:

```python
    if not ctx.invoked_subcommand:
        from bute.commands.tour import should_run_tour

        config = ctx.obj["config"]

        # First-run tour — no entries and tour not completed
        if should_run_tour(config):
            from bute.commands.tour import run_tour
            run_tour(ctx)
            return

        from bute.state import is_dyts_done_today

        if is_dyts_done_today(config):
            # Daily plan already done — show Focus Log
            from datetime import date
            from bute.display import display_entry_list
            from bute.ritual_ops import get_daily_log
            from bute.state import save_state

            entries = get_daily_log(config)
            display_entry_list(entries, f"Focus Log — {date.today().strftime('%a %b %d')}", hide_tags={"today", "thisweek"})

            # Show habits
            from bute.commands.views import _show_habits
            habit_names = _show_habits(config, len(entries))

            # Random old journal whisper (numbered after entries + habits)
            journal_id = _show_random_journal(config, len(entries) + len(habit_names))

            save_state("ls", [e.id for e in entries], config, habits=habit_names, extra_entries=[journal_id] if journal_id else None)

            from rich.console import Console
            console = Console()
            console.print(f"\n  [dim]Focus logged. Run [bold]bt dp[/bold] to redo.[/dim]")
        else:
            ctx.invoke(dp_cmd)
```

The only change is the 6-line tour check block at the top. The rest of the existing code stays identical.

- [ ] **Step 3: Run all tour tests**

Run: `uv run pytest tests/test_tour.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Run the full test suite to check for regressions**

Run: `uv run pytest -x -v`
Expected: All existing tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bute/cli.py
git commit -m "feat(tour): wire tour trigger into main() — auto-launch on first bt run"
```

---

### Task 5: Manual testing and edge case fixes

**Files:**
- Possibly modify: `src/bute/commands/tour.py`
- Possibly modify: `tests/test_tour.py`

- [ ] **Step 1: Install bt globally for manual testing**

```bash
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall
```

- [ ] **Step 2: Test fresh start**

Delete existing tour markers and entries to simulate a fresh install:

```bash
rm -f ~/.config/bute/.tour_done ~/.config/bute/.tour_progress
```

Then run `bt` and walk through the tour manually. Verify:
- Tour launches automatically
- Each phase intro and step prompt display correctly
- Typing real commands creates real entries
- Feedback shows after each successful step
- `/skip` advances to next phase
- `/done` exits and shows outro
- Ctrl+C saves progress and resume works
- After completion, `bt` shows dp or Focus Log (not tour)

- [ ] **Step 3: Test edge cases**

- Type wrong entry type (e.g., `n` when asked for `t`) — should show hint, not crash
- Type a view command mid-phase (e.g., `w`) — should execute and re-prompt
- Empty input — should re-show prompt
- Type `bt` prefix out of habit (e.g., `bt t call mom`) — should strip prefix and work

- [ ] **Step 4: Fix any issues found, add tests for fixes**

If any edge cases fail, fix them in `tour.py` and add regression tests to `test_tour.py`.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "fix(tour): edge case fixes from manual testing"
```

(Skip this commit if no fixes were needed.)

---

### Task 6: Update CLAUDE.md backlog

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add backlog items to CLAUDE.md**

In the Backlog section of `CLAUDE.md`, under `### Infrastructure`, add:

```markdown
- ~~**Guided tour — first-run onboarding**~~ ✓ Done — interactive REPL teaches core concepts on first `bt` run. 11 phases: capture → see → organize → act → plan.
```

Under `### Commands — High Value` (or create a new subsection), add:

```markdown
- **AI tour** — triggered after `bt init` configures an AI provider. Teaches search, chat, recap, nudges, analyze, tag-notes using real entries.
- **Redesign Daily Plan (`dp`)** — decompose Dump into individual entry types (t, n, j, c) mirroring the tour's layered approach. Rename to "Focus Process" since it flows into the Focus Log.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update backlog — tour done, add AI tour and Focus Process items"
```
