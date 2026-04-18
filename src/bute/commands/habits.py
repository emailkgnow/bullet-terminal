"""Habit commands — bt h (list), bt h <text> (add), bt h <n> done/undo/delete."""

from datetime import date, timedelta

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from bute.state import load_state, save_state
from bute.storage import query_and_load, update_entry

console = Console()


def _get_habit_entries(config) -> list:
    """Get all recurring task entries (any task with `repeat` set), sorted by creation."""
    entries = query_and_load(config, type="task", status="active", has_repeat=True)
    return sorted(entries, key=lambda e: e.created)


def _resolve_habit_entries(numbers: list[int], config) -> list:
    """Map display numbers to habit Entry objects from state."""
    from bute.storage import entry_path_from_id, load_entry

    state = load_state(config)
    if state.get("view") == "habits":
        ids = state.get("entries", [])
    else:
        ids = state.get("habits", [])
    entries = []
    for n in numbers:
        if n < 1 or n > len(ids):
            console.print(f"  [red]Habit #{n} out of range (1-{len(ids)}).[/red]")
            continue
        path = entry_path_from_id(ids[n - 1], config)
        if path:
            entries.append(load_entry(path))
    return entries


def display_habits(config) -> None:
    """Show numbered habit list with today's status."""
    habits = _get_habit_entries(config)
    if not habits:
        console.print("  [dim]No habits. Add one:[/dim] [bold]bt h <name>[/bold]")
        return

    today = date.today()
    save_state("habits", [e.id for e in habits], config)

    table = Table(
        show_header=False,
        show_edge=False,
        pad_edge=False,
        box=None,
        padding=(0, 1),
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("", width=1)
    table.add_column("", ratio=1)

    for i, entry in enumerate(habits, 1):
        completed = entry.is_completed_for_date(today)
        icon = Text("●", style="green") if completed else Text("○", style="dim")
        table.add_row(str(i), icon, entry.body)

    console.print(f"\n  [bold]Habits[/bold]")
    console.print(table)


def handle_habit_action(tokens: list[str], config) -> None:
    """Handle bt h <n> done/undo/delete."""
    numbers = []
    rest = list(tokens)
    while rest and rest[0].isdigit():
        numbers.append(int(rest.pop(0)))

    if not numbers:
        console.print("  [red]No habit number provided.[/red]")
        return

    entries = _resolve_habit_entries(numbers, config)
    if not entries:
        return

    today = date.today()

    if not rest:
        # Bare number — toggle: done if not done today, undo if already done
        action = "undo" if entries[0].is_completed_for_date(today) else "done"
    else:
        action = rest[0]

    if action == "done":
        today_iso = today.isoformat()
        for entry in entries:
            if today_iso not in entry.completions:
                entry.completions.append(today_iso)
                update_entry(entry, config)
            console.print(f"  [green]●[/green] [bold]\\[done][/bold] {entry.body}")

    elif action == "undo":
        today_iso = today.isoformat()
        for entry in entries:
            if today_iso in entry.completions:
                entry.completions.remove(today_iso)
                update_entry(entry, config)
            console.print(f"  [dim]○[/dim] [bold]\\[undo][/bold] {entry.body}")

    elif action == "delete":
        from bute.models import TaskStatus
        for entry in entries:
            entry.status = TaskStatus.DROPPED
            update_entry(entry, config)
            console.print(f"  [red]✕[/red] [bold]\\[delete][/bold] {entry.body}")

    else:
        console.print(f"  [red]Unknown action: '{action}'. Use: done, undo, delete[/red]")


def handle_habit_add(text: str, config) -> None:
    """Add a new habit as a recurring task entry."""
    from bute.ai import embed_entry
    from bute.display import confirm_capture
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    name = text.strip()

    # Check for duplicate
    existing = _get_habit_entries(config)
    if any(e.body == name for e in existing):
        console.print(f"  [dim]{name} already exists.[/dim]")
        return

    entry = Entry.create(
        entry_type=EntryType.TASK,
        body=name,
        repeat="daily",
    )
    # Habits don't need @today/@thisweek
    save_entry(entry, config)
    embed_entry(entry.id, entry.body, config)
    console.print(f"  [green]●[/green] Added habit: [bold]{name}[/bold]")


@click.command("habits", hidden=True)
@click.argument("tokens", nargs=-1)
@click.pass_context
def habits_cmd(ctx, tokens):
    """Habit tracking — list, add, done, undo, delete."""
    config = ctx.obj.get("config")

    if not tokens:
        display_habits(config)
        return

    if tokens[0].isdigit():
        handle_habit_action(list(tokens), config)
        return

    handle_habit_add(" ".join(tokens), config)


@click.command("streak")
@click.pass_context
def streak_cmd(ctx):
    """Habit streaks — 7-day grid, current streak, 30-day rate."""
    config = ctx.obj.get("config")
    habits = _get_habit_entries(config)

    if not habits:
        console.print("  [dim]No habits. Add with[/dim] [bold]bt h <name>[/bold]")
        return

    today = date.today()
    days_7 = [today - timedelta(days=6 - i) for i in range(7)]
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    table = Table(
        title="Habits — Last 7 Days",
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Habit", ratio=1)
    for d in days_7:
        table.add_column(weekdays[d.weekday()], width=3, justify="center")
    table.add_column("Streak", justify="right", width=10)
    table.add_column("30 days", justify="right", width=12)

    for entry in habits:
        completions_set = set(entry.completions)
        row = [entry.body]

        # 7-day dots
        for d in days_7:
            if d.isoformat() in completions_set:
                row.append("[green]●[/green]")
            else:
                row.append("[dim]○[/dim]")

        # Streak — consecutive days backwards from yesterday
        streak = 0
        d = today - timedelta(days=1)
        while d.isoformat() in completions_set:
            streak += 1
            d -= timedelta(days=1)
        # Include today if done
        if today.isoformat() in completions_set:
            streak += 1
        row.append(f"streak: {streak}")

        # 30-day rate
        days_30 = [today - timedelta(days=i) for i in range(30)]
        done_count = sum(1 for d in days_30 if d.isoformat() in completions_set)
        pct = round(done_count / 30 * 100)
        row.append(f"{done_count}/30 ({pct}%)")

        table.add_row(*row)

    console.print()
    console.print(table)


@click.command("migrate-habits")
@click.pass_context
def migrate_habits_cmd(ctx):
    """Migrate config-based habits to entry-based habits."""
    import yaml

    from bute.ai import embed_entry
    from bute.config import get_data_dir
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    config = ctx.obj.get("config")

    # Get old config-based habits
    old_habits = []
    if config and "habits" in config and "list" in config["habits"]:
        old_habits = list(config["habits"]["list"])

    if not old_habits:
        console.print("  [dim]No config-based habits to migrate.[/dim]")
        return

    # Check what's already migrated
    existing = _get_habit_entries(config)
    existing_names = {e.body for e in existing}

    data_dir = get_data_dir(config)
    habits_dir = data_dir / "habits"

    for name in old_habits:
        if name in existing_names:
            console.print(f"  [dim]{name} already migrated.[/dim]")
            continue

        # Collect completion dates from YAML files
        completions = []
        if habits_dir.exists():
            for yml_file in sorted(habits_dir.glob("*.yml")):
                month_data = yaml.safe_load(yml_file.read_text()) or {}
                for date_key, day_data in month_data.items():
                    if isinstance(day_data, dict) and day_data.get(name) is True:
                        completions.append(str(date_key))

        entry = Entry.create(
            entry_type=EntryType.TASK,
            body=name,
            tags=["habit"],
            repeat="daily",
        )
        entry.completions = sorted(completions)
        save_entry(entry, config)
        embed_entry(entry.id, entry.body, config)
        console.print(
            f"  [green]●[/green] Migrated: {name} ({len(completions)} completions)"
        )

    console.print(f"\n  [bold]Migration complete.[/bold]")
    console.print(f"  [dim]Old YAML files preserved in {habits_dir}[/dim]")
