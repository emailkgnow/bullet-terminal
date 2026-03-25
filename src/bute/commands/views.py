"""View commands for bute (ls, tasks, notes, journals, calendar, active, tag filter)."""

from datetime import date

import click

from bute.display import display_entry_list, display_entry_list_grouped
from bute.models import EntryType, TaskStatus
from bute.ritual_ops import get_daily_log
from bute.state import save_state
from bute.storage import load_entries_by_filter


@click.command("ls")
@click.pass_context
def ls_cmd(ctx):
    """Today's daily log — focus tasks, events, journals, notes."""
    config = ctx.obj.get("config")
    entries = get_daily_log(config)
    title = f"Today — {date.today().strftime('%a %b %d')}"
    display_entry_list(entries, title)
    save_state("ls", [e.id for e in entries], config)


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
    """Show active tasks (weekly selection in future phases)."""
    config = ctx.obj.get("config")

    entries = load_entries_by_filter(
        lambda e: e.type == EntryType.TASK and e.status == TaskStatus.ACTIVE,
        config,
    )
    display_entry_list(entries, "Active Tasks")
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
