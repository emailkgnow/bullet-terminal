"""View commands for bute (ls, tasks, notes, journals, calendar, active, tag filter)."""

from datetime import date, datetime

import click

from rich.console import Console
from rich.table import Table

from bute.display import display_entry_list, display_entry_list_grouped
from bute.models import EntryType, TaskStatus
from bute.ritual_ops import get_daily_log, get_weekly_active_tasks
from bute.state import save_state
from bute.storage import load_entries_by_filter

console = Console()


@click.command("ls")
@click.pass_context
def ls_cmd(ctx):
    """Today's daily log — focus tasks, events, journals, notes."""
    config = ctx.obj.get("config")
    entries = get_daily_log(config)
    title = f"Today — {date.today().strftime('%a %b %d')}"
    display_entry_list(entries, title)
    habit_names = _show_habits(config, len(entries))
    save_state("ls", [e.id for e in entries], config, habits=habit_names)

    # Evening reminder
    from bute.state import is_recap_done_today
    if datetime.now().hour >= 18 and not is_recap_done_today(config):
        console.print("  [dim]Run[/dim] [bold]bt recap[/bold] [dim]for your day summary[/dim]")


def _show_habits(config, entry_count=0) -> list[str]:
    """Show numbered habit rows if habits are configured. Returns habit names."""
    configured = []
    if config and "habits" in config and "list" in config["habits"]:
        configured = list(config["habits"]["list"])
    if not configured:
        return []
    from bute.display import display_habit_line
    from bute.habit_storage import get_habit_summary
    habits = get_habit_summary(date.today(), configured, config)
    start_num = entry_count + 1 if entry_count > 0 else 0
    display_habit_line(habits, configured, start_num=start_num)
    return configured


def _dimension_command(name, entry_type, label, group_by_date=False):
    """Factory for dimension view commands (tasks, notes, journals, calendar)."""

    @click.command(name)
    @click.argument("tag", required=False, default=None)
    @click.option("--all", "-a", "show_all", is_flag=True, help="Include done/dropped.")
    @click.pass_context
    def cmd(ctx, tag, show_all):
        config = ctx.obj.get("config")

        def predicate(e):
            if e.type != entry_type:
                return False
            if tag and tag not in e.tags:
                return False
            if not show_all and entry_type == EntryType.TASK and e.status != TaskStatus.ACTIVE:
                return False
            return True

        entries = load_entries_by_filter(predicate, config)

        title_parts = [label]
        if tag:
            title_parts.append(f"@{tag}")
        if show_all and entry_type == EntryType.TASK:
            title_parts[0] = f"All {label}"
        title = " ".join(title_parts)

        if group_by_date:
            display_entry_list_grouped(entries, title)
        else:
            display_entry_list(entries, title)
        save_state(name, [e.id for e in entries], config)

    cmd.__doc__ = f"Show {label.lower()}. Optional @tag to filter."
    return cmd


tasks_cmd = _dimension_command("tasks", EntryType.TASK, "Task Log")
notes_cmd = _dimension_command("notes", EntryType.NOTE, "Notes", group_by_date=True)
journals_cmd = _dimension_command("journals", EntryType.JOURNAL, "Journals", group_by_date=True)
calendar_cmd = _dimension_command("calendar", EntryType.CALENDAR, "Calendar", group_by_date=True)


@click.command("active")
@click.pass_context
def active_cmd(ctx):
    """Show this week's focus tasks (@thisweek). Falls back to all active if none tagged."""
    config = ctx.obj.get("config")

    entries = get_weekly_active_tasks(config)
    display_entry_list(entries, "This Week")
    save_state("active", [e.id for e in entries], config)


@click.command("tag_filter", hidden=True)
@click.argument("tag")
@click.pass_context
def tag_filter_cmd(ctx, tag):
    """Show all entries with a given tag."""
    config = ctx.obj.get("config")

    entries = load_entries_by_filter(
        lambda e: tag in e.tags,
        config,
    )
    display_entry_list(entries, f"@{tag}")
    save_state("tag_filter", [e.id for e in entries], config)


@click.command("tags")
@click.pass_context
def tags_cmd(ctx):
    """List all tags with entry counts."""
    config = ctx.obj.get("config")

    entries = load_entries_by_filter(lambda e: bool(e.tags), config)

    counts: dict[str, int] = {}
    for entry in entries:
        for tag in entry.tags:
            counts[tag] = counts.get(tag, 0) + 1

    if not counts:
        console.print("  [dim]No tags found.[/dim]")
        return

    table = Table(
        title="Tags",
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Tag", ratio=1)
    table.add_column("#", justify="right", width=5)

    for tag, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        table.add_row(f"@{tag}", str(count))

    console.print()
    console.print(table)
