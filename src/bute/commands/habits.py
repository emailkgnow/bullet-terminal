"""Recurring task helpers and `bt streak` view."""

from datetime import date, timedelta

import click
from rich.console import Console
from rich.table import Table

from bute.storage import query_and_load

console = Console()


def _get_habit_entries(config) -> list:
    """Get all recurring task entries (any task with `repeat` set), sorted by creation."""
    entries = query_and_load(config, type="task", status="active", has_repeat=True)
    return sorted(entries, key=lambda e: e.created)


@click.command("streak")
@click.pass_context
def streak_cmd(ctx):
    """Recurring task streaks — 7-day grid, current streak, 30-day rate."""
    config = ctx.obj.get("config")
    habits = _get_habit_entries(config)

    if not habits:
        console.print(
            "  [dim]No recurring tasks. Add one:[/dim] "
            "[bold]bt t <text> repeat:daily[/bold]"
        )
        return

    today = date.today()
    days_7 = [today - timedelta(days=6 - i) for i in range(7)]
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    table = Table(
        title="Recurring Tasks — Last 7 Days",
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Task", ratio=1)
    for d in days_7:
        table.add_column(weekdays[d.weekday()], width=3, justify="center")
    table.add_column("Streak", justify="right", width=10)
    table.add_column("30 days", justify="right", width=12)

    for entry in habits:
        completions_set = set(entry.completions)
        row = [entry.body]

        for d in days_7:
            if d.isoformat() in completions_set:
                row.append("[green]●[/green]")
            else:
                row.append("[dim]○[/dim]")

        streak = 0
        d = today - timedelta(days=1)
        while d.isoformat() in completions_set:
            streak += 1
            d -= timedelta(days=1)
        if today.isoformat() in completions_set:
            streak += 1
        row.append(f"streak: {streak}")

        days_30 = [today - timedelta(days=i) for i in range(30)]
        done_count = sum(1 for d in days_30 if d.isoformat() in completions_set)
        pct = round(done_count / 30 * 100)
        row.append(f"{done_count}/30 ({pct}%)")

        table.add_row(*row)

    console.print()
    console.print(table)
