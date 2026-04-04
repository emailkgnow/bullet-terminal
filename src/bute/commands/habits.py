"""Habit commands — bt h (list), bt h <text> (add), bt h <n> done/undo/delete."""

import click
from datetime import timedelta
from rich.console import Console
from rich.table import Table
from rich.text import Text

from bute.config import load_config, save_config
from bute.habit_storage import get_habit_summary, save_habit
from bute.state import load_state, save_state

console = Console()


def _get_configured(config) -> list[str]:
    """Get configured habit names from config."""
    if config and "habits" in config and "list" in config["habits"]:
        return list(config["habits"]["list"])
    return []


def _save_habit_list(habits: list[str]) -> None:
    """Persist the habit list to config.toml."""
    import tomlkit

    config = load_config()
    if "habits" not in config:
        config.add("habits", tomlkit.table())
    config["habits"]["list"] = habits
    save_config(config)


def _resolve_habit_numbers(numbers: list[int], config) -> list[str]:
    """Map display numbers to habit names from state."""
    state = load_state(config)
    # In habits-only view, habits are in "entries". In mixed views, in "habits".
    if state.get("view") == "habits":
        habits = state.get("entries", [])
    else:
        habits = state.get("habits", [])
    names = []
    for n in numbers:
        if n < 1 or n > len(habits):
            console.print(f"  [red]Habit #{n} out of range (1-{len(habits)}).[/red]")
            continue
        names.append(habits[n - 1])
    return names


def display_habits(config) -> None:
    """Show numbered habit list with today's status."""
    from datetime import date

    configured = _get_configured(config)
    if not configured:
        console.print("  [dim]No habits configured. Add one:[/dim] [bold]bt h <name>[/bold]")
        return

    habits = get_habit_summary(date.today(), configured, config)
    save_state("habits", configured, config)

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

    for i, name in enumerate(configured, 1):
        status = habits.get(name)
        if status is True:
            icon = Text("●", style="green")
        else:
            icon = Text("○", style="dim")
        table.add_row(str(i), icon, name)

    console.print(f"\n  [bold]Habits[/bold]")
    console.print(table)


def handle_habit_action(tokens: list[str], config) -> None:
    """Handle bt h <n> done/undo/delete."""
    from datetime import date

    # Parse leading numbers
    numbers = []
    rest = list(tokens)
    while rest and rest[0].isdigit():
        numbers.append(int(rest.pop(0)))

    if not numbers:
        console.print("  [red]No habit number provided.[/red]")
        return

    if not rest:
        # Bare number — toggle: done if not done today, undo if already done
        from bute.habit_storage import get_habit_summary
        names = _resolve_habit_numbers(numbers, config)
        configured = _get_configured(config)
        summary = get_habit_summary(date.today(), configured, config)
        # Use first habit's state to pick action (all in batch get same action)
        action = "undo" if names and summary.get(names[0]) else "done"
    else:
        action = rest[0]
    names = _resolve_habit_numbers(numbers, config)

    if action == "done":
        for name in names:
            save_habit(name, True, date.today(), config)
            console.print(f"  [green]●[/green] [bold]\\[done][/bold] {name}")

    elif action == "undo":
        from bute.habit_storage import remove_habit_entry

        for name in names:
            remove_habit_entry(name, date.today(), config)
            console.print(f"  [dim]○[/dim] [bold]\\[undo][/bold] {name}")

    elif action == "delete":
        configured = _get_configured(config)
        for name in names:
            if name in configured:
                configured.remove(name)
                console.print(f"  [red]✕[/red] [bold]\\[delete][/bold] {name}")
        _save_habit_list(configured)

    else:
        console.print(f"  [red]Unknown action: '{action}'. Use: done, undo, delete[/red]")


def handle_habit_add(text: str, config) -> None:
    """Add a new habit."""
    name = text.strip()
    configured = _get_configured(config)

    if name in configured:
        console.print(f"  [dim]{name} already exists.[/dim]")
        return

    configured.append(name)
    _save_habit_list(configured)
    console.print(f"  [green]●[/green] Added habit: [bold]{name}[/bold]")


@click.command("habits", hidden=True)
@click.argument("tokens", nargs=-1)
@click.pass_context
def habits_cmd(ctx, tokens):
    """Habit tracking — list, add, done, undo, delete."""
    config = ctx.obj.get("config")

    if not tokens:
        # bt h — list habits
        display_habits(config)
        return

    # bt h <n> <action> — number-action
    if tokens[0].isdigit():
        handle_habit_action(list(tokens), config)
        return

    # bt h <text> — add new habit
    handle_habit_add(" ".join(tokens), config)


@click.command("streak")
@click.pass_context
def streak_cmd(ctx):
    """Habit streaks — 7-day grid, current streak, 30-day rate."""
    from datetime import date

    from bute.habit_storage import compute_streak, get_habit_history

    config = ctx.obj.get("config")
    configured = _get_configured(config)

    if not configured:
        console.print("  [dim]No habits configured. Add with[/dim] [bold]bt h <name>[/bold]")
        return

    today = date.today()
    history = get_habit_history(30, configured, target_date=today, config=config)

    # Build 7-day range
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

    for name in configured:
        habit_data = history[name]
        row = [name]

        # 7-day dots
        for d in days_7:
            val = habit_data.get(d)
            if val is True:
                row.append("[green]●[/green]")
            else:
                row.append("[dim]○[/dim]")

        # Streak
        streak = compute_streak(history, name, target_date=today)
        row.append(f"streak: {streak}")

        # 30-day rate
        days_30 = [today - timedelta(days=i) for i in range(30)]
        done_count = sum(1 for d in days_30 if habit_data.get(d) is True)
        pct = round(done_count / 30 * 100)
        row.append(f"{done_count}/30 ({pct}%)")

        table.add_row(*row)

    console.print()
    console.print(table)
