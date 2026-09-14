"""View commands for bute (tasks, backlog, notes, journals, calendar, tag filter)."""

from datetime import date

import click

from rich.console import Console
from rich.table import Table

from bute.completion import complete_tags
from bute.display import (
    _build_entry_row,
    _ZEBRA_STYLE,
    display_entry_list,
    display_entry_list_grouped,
    emit_json,
    entry_to_dict,
    json_mode,
)
from bute.models import EntryType, TaskStatus
from bute.ritual_ops import get_all_active_tasks, get_weekly_active_tasks
from bute.state import save_state
from bute.storage import query_and_load

console = Console()


def _show_habits(config, entry_count=0) -> list[str]:
    """Show numbered habit rows from entries. Returns habit entry IDs."""
    from bute.commands.habits import _get_habit_entries
    from bute.display import display_habit_line_entries
    habits = _get_habit_entries(config)
    if not habits:
        return []
    start_num = entry_count + 1 if entry_count > 0 else 0
    display_habit_line_entries(habits, date.today(), start_num=start_num)
    return [e.id for e in habits]


def _dimension_command(name, entry_type, label, group_by_date=False):
    """Factory for dimension view commands (tasks, notes, journals, calendar)."""

    @click.command(name)
    @click.argument("tag", required=False, default=None, shell_complete=complete_tags)
    @click.option("--all", "-a", "show_all", is_flag=True, help="Include done/dropped.")
    @click.pass_context
    def cmd(ctx, tag, show_all):
        config = ctx.obj.get("config")

        if tag and tag.startswith("@"):
            tag = tag[1:]

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


@click.command("tasks")
@click.argument("tag", required=False, default=None, shell_complete=complete_tags)
@click.option("--all", "-a", "show_all", is_flag=True, help="Include done/dropped.")
@click.pass_context
def tasks_cmd(ctx, tag, show_all):
    """Show this week's focus tasks (@thisweek). -a for done/dropped."""
    config = ctx.obj.get("config")

    if tag and tag.startswith("@"):
        tag = tag[1:]

    if show_all:
        kwargs = {"type": "task", "status": None}
        if tag:
            kwargs["tag"] = tag
        entries = query_and_load(config, **{k: v for k, v in kwargs.items() if v is not None})
        entries = [e for e in entries if not e.is_recurring()]
        title = f"All Tasks" + (f" @{tag}" if tag else "")
    else:
        entries = get_weekly_active_tasks(config)
        if tag:
            entries = [e for e in entries if tag in e.tags]
        title = "Task Log" + (f" @{tag}" if tag else "")

    display_entry_list(entries, title)
    save_state("tasks", [e.id for e in entries], config)


@click.command("backlog")
@click.argument("tag", required=False, default=None, shell_complete=complete_tags)
@click.option("--all", "-a", "show_all", is_flag=True, help="Include done/dropped.")
@click.pass_context
def backlog_cmd(ctx, tag, show_all):
    """Show all active tasks. -a for done/dropped."""
    config = ctx.obj.get("config")

    if tag and tag.startswith("@"):
        tag = tag[1:]

    kwargs = {"type": "task"}
    if tag:
        kwargs["tag"] = tag
    if not show_all:
        kwargs["status"] = "active"
    entries = query_and_load(config, **kwargs)
    # Exclude recurring tasks — they have their own view (bt streak)
    entries = [e for e in entries if not e.is_recurring()]

    title_parts = ["Task Backlog"]
    if tag:
        title_parts.append(f"@{tag}")
    if show_all:
        title_parts[0] = "All Tasks (Backlog)"
    title = " ".join(title_parts)

    display_entry_list(entries, title)
    save_state("backlog", [e.id for e in entries], config)


notes_cmd = _dimension_command("notes", EntryType.NOTE, "Notes", group_by_date=True)
journals_cmd = _dimension_command("journals", EntryType.JOURNAL, "Journals", group_by_date=True)
calendar_cmd = _dimension_command("calendar", EntryType.CALENDAR, "Calendar", group_by_date=True)


@click.command("important", hidden=True)
@click.argument("entry_type", required=False, default=None)
@click.option("--all", "-a", "show_all", is_flag=True, help="Include done/dropped.")
@click.pass_context
def important_cmd(ctx, entry_type, show_all):
    """Show important entries. Optional type filter (task, note, journal, calendar)."""
    config = ctx.obj.get("config")

    type_map = {
        "task": EntryType.TASK, "t": EntryType.TASK,
        "note": EntryType.NOTE, "n": EntryType.NOTE,
        "journal": EntryType.JOURNAL, "j": EntryType.JOURNAL,
        "calendar": EntryType.CALENDAR, "c": EntryType.CALENDAR,
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



@click.command("tag_filter", hidden=True)
@click.argument("tags", nargs=-1, shell_complete=complete_tags)
@click.option("--exclude", "-x", multiple=True, help="Exclude entries with this tag.")
@click.option("--all", "show_all", is_flag=True, hidden=True)
@click.pass_context
def tag_filter_cmd(ctx, tags, exclude, show_all):
    """Show entries filtered by tags. Multiple @tags = AND. -@tag = exclude."""
    config = ctx.obj.get("config")

    include_tags = [t for t in tags if t != "--all"]

    if include_tags:
        # Start with first tag, then intersect
        entries = query_and_load(config, tag=include_tags[0])
        for tag in include_tags[1:]:
            entries = [e for e in entries if tag in e.tags]
    elif show_all or exclude:
        # Exclude-only: start with all entries
        entries = query_and_load(config)
    else:
        entries = []

    # Apply exclusions
    for ex in exclude:
        entries = [e for e in entries if ex not in e.tags]

    # Build title
    parts = [f"@{t}" for t in include_tags]
    for ex in exclude:
        parts.append(f"-@{ex}")
    title = " ".join(parts) if parts else "All"

    display_entry_list(entries, title)
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

    if json_mode():
        import json as _json
        import click as _click
        ordered = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        _click.echo(_json.dumps({"view": "Tags", "tags": [{"tag": t, "count": c} for t, c in ordered]}))
        return

    if not counts:
        console.print("  [dim]No tags found.[/dim]")
        return

    stages = {s["tag"]: s["stage"] for s in get_all_tag_stages(config)}
    stage_colors = {"raw": "dim", "analyzed": "green"}

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

    for i, (tag, count) in enumerate(sorted(counts.items(), key=lambda x: x[1], reverse=True), 1):
        stage = stages.get(tag, "raw")
        color = stage_colors.get(stage, "dim")
        row_style = _ZEBRA_STYLE if i % 2 == 0 else ""
        table.add_row(f"@{tag}", f"[{color}]{stage}[/{color}]", str(count), style=row_style)

    console.print()
    console.print(table)


@click.command("due")
@click.argument("scope", required=False, default=None)
@click.pass_context
def due_cmd(ctx, scope):
    """Show tasks by deadline. 'bt due all' for all tasks with due dates."""
    from datetime import timedelta

    config = ctx.obj.get("config")
    today = date.today()
    end_of_week = today + timedelta(days=7)

    entries = query_and_load(config, type="task", status="active", has_due=True)

    if not entries:
        if json_mode():
            emit_json("Due Tasks", [])
        else:
            console.print("  [dim]No tasks with due dates.[/dim]")
        return

    entries.sort(key=lambda e: (e.due, not e.important))

    if scope == "all":
        display_entry_list(entries, "All Due Tasks")
        save_state("due", [e.id for e in entries], config)
        return

    overdue = [e for e in entries if e.due < today]

    if scope == "overdue":
        overdue.sort(key=lambda e: (e.due, not e.important))
        if not overdue:
            console.print("  [dim]Nothing overdue.[/dim]")
            return
        display_entry_list(overdue, "Overdue")
        save_state("due", [e.id for e in overdue], config)
        return
    due_today = [e for e in entries if e.due == today]
    due_week = [e for e in entries if today < e.due <= end_of_week]

    # Important entries first within each due group
    for group in (overdue, due_today, due_week):
        group.sort(key=lambda e: not e.important)

    filtered = overdue + due_today + due_week
    if not filtered:
        if json_mode():
            emit_json("Due Tasks", [])
        else:
            console.print("  [dim]Nothing due this week.[/dim]")
        return

    if json_mode():
        ordered = overdue + due_today + due_week
        labels = (["Overdue"] * len(overdue)) + (["Today"] * len(due_today)) + (["Next 7 Days"] * len(due_week))
        emit_json("Due Tasks", ordered, [{"group": g} for g in labels])
        save_state("due", [e.id for e in ordered], config)
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
        ("Next 7 Days", due_week, ""),
    ]

    for label, group, style in groups:
        if not group:
            continue
        for idx, entry in enumerate(group):
            all_entries.append(entry)
            num = len(all_entries)
            _, icon, body, meta = _build_entry_row(num, entry)
            group_label = f"[{style}]{label}[/{style}]" if style and idx == 0 else (label if idx == 0 else "")
            row_style = _ZEBRA_STYLE if num % 2 == 0 else ""
            table.add_row(group_label, str(num), icon, body, meta, style=row_style)
        table.add_section()

    console.print()
    console.print(table)
    save_state("due", [e.id for e in all_entries], config)
