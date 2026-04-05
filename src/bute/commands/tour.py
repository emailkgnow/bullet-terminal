"""Guided tour — interactive first-run onboarding for bt."""

import bute.config as _config
from dataclasses import dataclass, field
from typing import Callable


def is_tour_done() -> bool:
    """Check if the tour has been completed."""
    return _config.TOUR_DONE.exists()


def mark_tour_done() -> None:
    """Mark the tour as complete. Clears progress file."""
    _config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _config.TOUR_DONE.touch()
    if _config.TOUR_PROGRESS.exists():
        _config.TOUR_PROGRESS.unlink()


def load_tour_progress() -> int:
    """Load the current phase index (0-based). Returns 0 if no progress saved."""
    if not _config.TOUR_PROGRESS.exists():
        return 0
    try:
        return int(_config.TOUR_PROGRESS.read_text().strip())
    except (ValueError, OSError):
        return 0


def save_tour_progress(phase: int) -> None:
    """Save the current phase index for resume on Ctrl+C."""
    _config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _config.TOUR_PROGRESS.write_text(str(phase))


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Storage helpers (lazy imports to avoid circular dependencies)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Validation functions
# Each takes (user_input: str, config) and returns bool.
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Phase definitions — 11 phases following the arc:
# capture → see → organize → act → plan
# ---------------------------------------------------------------------------

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
