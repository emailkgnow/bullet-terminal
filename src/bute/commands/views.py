"""View commands for bute (ls, tasks, notes, journals, calendar, active, tag filter)."""

from datetime import date, datetime

import click

from rich.console import Console
from rich.table import Table

from bute.display import _build_entry_row, display_entry_list, display_entry_list_grouped
from bute.models import EntryType, TaskStatus
from bute.ritual_ops import get_daily_log, get_week_entries, get_weekly_active_tasks
from bute.state import save_state
from bute.storage import query_and_load

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

        kwargs = {"type": entry_type.value}
        if tag:
            kwargs["tag"] = tag
        if not show_all and entry_type == EntryType.TASK:
            kwargs["status"] = "active"
        entries = query_and_load(config, **kwargs)

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


@click.command("important", hidden=True)
@click.argument("entry_type", required=False, default=None)
@click.option("--all", "-a", "show_all", is_flag=True, help="Include done/dropped.")
@click.pass_context
def important_cmd(ctx, entry_type, show_all):
    """Show important entries. Optional type filter (task, note, journal, cal)."""
    config = ctx.obj.get("config")

    type_map = {
        "task": EntryType.TASK, "t": EntryType.TASK,
        "note": EntryType.NOTE, "n": EntryType.NOTE,
        "journal": EntryType.JOURNAL, "j": EntryType.JOURNAL,
        "cal": EntryType.CALENDAR, "c": EntryType.CALENDAR,
    }
    filter_type = type_map.get(entry_type) if entry_type else None

    kwargs = {"important": True}
    if filter_type:
        kwargs["type"] = filter_type.value
    if not show_all:
        kwargs["exclude_status"] = "dropped"
    entries = query_and_load(config, **kwargs)
    # Post-filter for task-specific status
    if not show_all:
        entries = [
            e for e in entries
            if not (e.type == EntryType.TASK and e.status != TaskStatus.ACTIVE)
        ]

    if filter_type:
        type_label = {
            EntryType.TASK: "Tasks",
            EntryType.NOTE: "Notes",
            EntryType.JOURNAL: "Journals",
            EntryType.CALENDAR: "Events",
        }[filter_type]
        title = f"{'All ' if show_all else ''}Important {type_label}"
    else:
        title = f"{'All ' if show_all else ''}Important"

    display_entry_list(entries, title)
    save_state("important", [e.id for e in entries], config)


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

    entries = query_and_load(config, tag=tag)
    display_entry_list(entries, f"@{tag}")
    save_state("tag_filter", [e.id for e in entries], config)


@click.command("tags")
@click.pass_context
def tags_cmd(ctx):
    """List all tags with entry counts and processing stage."""
    from bute.db import get_all_tag_stages

    config = ctx.obj.get("config")

    entries = query_and_load(config, has_tags=True)

    counts: dict[str, int] = {}
    for entry in entries:
        for tag in entry.tags:
            counts[tag] = counts.get(tag, 0) + 1

    if not counts:
        console.print("  [dim]No tags found.[/dim]")
        return

    stages = {s["tag"]: s["stage"] for s in get_all_tag_stages(config)}
    stage_colors = {"raw": "dim", "analyzed": "yellow", "executed": "green"}

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
    table.add_column("Stage")
    table.add_column("#", justify="right", width=5)

    for tag, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        stage = stages.get(tag, "raw")
        color = stage_colors.get(stage, "dim")
        table.add_row(f"@{tag}", f"[{color}]{stage}[/{color}]", str(count))

    console.print()
    console.print(table)


@click.command("week")
@click.argument("period", required=False, default=None)
@click.pass_context
def week_cmd(ctx, period):
    """Weekly spread — all entries Mon-Sun. 'bt week last' for last week."""
    from datetime import date, timedelta

    config = ctx.obj.get("config")
    today = date.today()

    if period == "last":
        target = today - timedelta(weeks=1)
    else:
        target = today

    monday = target - timedelta(days=target.weekday())
    sunday = monday + timedelta(days=6)
    title = f"Week of {monday.strftime('%b %d')} — {sunday.strftime('%b %d')}"

    entries = get_week_entries(target, config)
    if not entries:
        console.print(f"  [dim]No entries for {title}.[/dim]")
        return

    display_entry_list_grouped(entries, title)
    save_state("week", [e.id for e in entries], config)


@click.command("due")
@click.argument("scope", required=False, default=None)
@click.pass_context
def due_cmd(ctx, scope):
    """Show tasks by deadline. 'bt due all' for all tasks with due dates."""
    from datetime import timedelta

    config = ctx.obj.get("config")
    today = date.today()
    end_of_week = today + timedelta(days=(6 - today.weekday()))

    entries = query_and_load(config, type="task", status="active", has_due=True)

    if not entries:
        console.print("  [dim]No tasks with due dates.[/dim]")
        return

    entries.sort(key=lambda e: e.due)

    if scope == "all":
        display_entry_list(entries, "All Due Tasks")
        save_state("due", [e.id for e in entries], config)
        return

    overdue = [e for e in entries if e.due < today]
    due_today = [e for e in entries if e.due == today]
    due_week = [e for e in entries if today < e.due <= end_of_week]

    filtered = overdue + due_today + due_week
    if not filtered:
        console.print("  [dim]Nothing due this week.[/dim]")
        return

    # Build grouped table
    table = Table(
        title="Due Tasks",
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("", style="bold", width=10)
    table.add_column("#", style="bold dim", width=3, justify="right")
    table.add_column("", width=2)
    table.add_column("Entry", ratio=1, overflow="fold")
    table.add_column("Meta", style="dim")

    all_entries = []
    groups = [
        ("Overdue", overdue, "bold red"),
        ("Today", due_today, "bold yellow"),
        ("This Week", due_week, ""),
    ]

    for label, group, style in groups:
        if not group:
            continue
        for idx, entry in enumerate(group):
            all_entries.append(entry)
            num = len(all_entries)
            _, icon, body, meta = _build_entry_row(num, entry)
            group_label = f"[{style}]{label}[/{style}]" if style and idx == 0 else (label if idx == 0 else "")
            table.add_row(group_label, str(num), icon, body, meta)
        table.add_section()

    console.print()
    console.print(table)
    save_state("due", [e.id for e in all_entries], config)
