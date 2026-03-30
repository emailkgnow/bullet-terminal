"""Action command — handles number-based actions (done, drop, etc.)."""

import os
import subprocess

import click
from rich.console import Console

from bute.display import display_action_confirmation
from bute.errors import DwnError, InvalidActionError
from bute.models import Entry, EntryType, TaskStatus
from bute.state import pop_undo, record_undo, resolve_numbers
from bute.storage import entry_path_from_id, load_entry, update_entry

console = Console()


def parse_action_tokens(
    tokens: tuple[str, ...],
) -> tuple[list[int], str, list[str]]:
    """Parse action tokens into (numbers, action, args).

    Example: ("1", "3", "migrate", "tomorrow") → ([1, 3], "migrate", ["tomorrow"])
    """
    numbers = []
    rest = list(tokens)

    # Consume leading digits
    while rest and rest[0].isdigit():
        numbers.append(int(rest.pop(0)))

    if not numbers:
        raise InvalidActionError("No entry numbers provided.")

    if not rest:
        raise InvalidActionError("No action specified.")

    action = rest.pop(0)
    return numbers, action, rest


def _require_task(entry: Entry, action: str) -> None:
    """Raise if entry is not a task."""
    if entry.type != EntryType.TASK:
        raise DwnError(
            f"Entry is a {entry.type.value}. Only tasks can be marked '{action}'."
        )


def handle_done(entry: Entry, args: list[str], config) -> None:
    """Mark a task as done."""
    _require_task(entry, "done")
    record_undo(entry.id, "done", {"status": entry.status.value}, config)
    entry.status = TaskStatus.DONE
    update_entry(entry, config)


def handle_drop(entry: Entry, args: list[str], config) -> None:
    """Mark a task as dropped."""
    _require_task(entry, "drop")
    record_undo(entry.id, "drop", {"status": entry.status.value}, config)
    entry.status = TaskStatus.DROPPED
    update_entry(entry, config)


def handle_delete(entry: Entry, args: list[str], config) -> None:
    """Permanently delete an entry from disk and vector DB."""
    path = entry_path_from_id(entry.id, config)
    if path and path.exists():
        path.unlink()
    from bute.ai.vectors import is_available, delete as vec_delete
    if is_available():
        vec_delete(entry.id, config)


def handle_toggle_important(entry: Entry, args: list[str], config) -> None:
    """Toggle the important flag."""
    record_undo(entry.id, "!", {"important": entry.important}, config)
    entry.important = not entry.important
    update_entry(entry, config)


def handle_mod(entry: Entry, args: list[str], config) -> None:
    """Modify the body text of an entry."""
    if not args:
        raise InvalidActionError("mod requires new text. Usage: bt 1 mod new text here")
    entry.body = " ".join(args)
    update_entry(entry, config)


def handle_edit(entry: Entry, args: list[str], config) -> None:
    """Open entry in $EDITOR for full editing."""
    path = entry_path_from_id(entry.id, config)
    if path is None:
        raise DwnError("Entry file not found.")
    editor = os.environ.get("EDITOR", "nano")
    subprocess.call([editor, str(path)])


def handle_add_tag(entry: Entry, tag: str, config) -> None:
    """Add a tag to an entry (no duplicates)."""
    if tag not in entry.tags:
        record_undo(entry.id, "@tag", {"tag": tag}, config)
        entry.tags.append(tag)
    update_entry(entry, config)


def handle_later(entry: Entry, args: list[str], config) -> None:
    """Remove @today tag — defer task to backlog."""
    _require_task(entry, "later")
    if "today" in entry.tags:
        record_undo(entry.id, "later", {"tag": "today"}, config)
        entry.tags.remove("today")
        update_entry(entry, config)
    else:
        Console().print(f"  [dim]Not in today's log[/dim]")


def handle_remove_tag(entry: Entry, tag: str, config) -> None:
    """Remove a tag from an entry."""
    if tag in entry.tags:
        record_undo(entry.id, "untag", {"tag": tag}, config)
        entry.tags.remove(tag)
        update_entry(entry, config)
    else:
        Console().print(f"  [dim]@{tag} not on this entry[/dim]")


def apply_undo(record: dict, config) -> None:
    """Reverse a recorded action."""
    entry_id = record["entry_id"]
    action = record["action"]
    prev = record["prev"]

    path = entry_path_from_id(entry_id, config)
    if path is None:
        raise DwnError(f"Entry {entry_id[:8]} not found — cannot undo.")
    entry = load_entry(path)

    if action in ("done", "drop"):
        entry.status = TaskStatus(prev["status"])
        update_entry(entry, config)
    elif action == "!":
        entry.important = prev["important"]
        update_entry(entry, config)
    elif action == "@tag":
        tag = prev["tag"]
        if tag in entry.tags:
            entry.tags.remove(tag)
        update_entry(entry, config)
    elif action in ("untag", "later"):
        tag = prev["tag"]
        if tag not in entry.tags:
            entry.tags.append(tag)
        update_entry(entry, config)
    else:
        raise DwnError(f"Cannot undo '{action}'.")

    display_action_confirmation(entry, f"undo {action}")


# Action dispatch table
ACTION_HANDLERS = {
    "done": handle_done,
    "drop": handle_drop,
    "delete": handle_delete,
    "!": handle_toggle_important,
    "mod": handle_mod,
    "modify": handle_mod,
    "edit": handle_edit,
    "later": handle_later,
}


@click.command("action", hidden=True)
@click.argument("tokens", nargs=-1, required=True)
@click.pass_context
def action_cmd(ctx, tokens):
    """Perform actions on numbered entries."""
    config = ctx.obj.get("config")
    numbers, action, args = parse_action_tokens(tokens)
    entry_ids = resolve_numbers(numbers, config)

    # Handle undo: bt <n> undo
    if action == "undo":
        for entry_id in entry_ids:
            record = pop_undo(entry_id, config)
            if record is None:
                console.print(f"  [dim]Nothing to undo for {entry_id[:8]}[/dim]")
                continue
            apply_undo(record, config)
        return

    # Handle @tag action
    if action.startswith("@") and len(action) > 1:
        tag = action[1:]
        for entry_id in entry_ids:
            path = entry_path_from_id(entry_id, config)
            if path is None:
                console.print(f"  [red]Entry {entry_id[:8]} not found.[/red]")
                continue
            entry = load_entry(path)
            handle_add_tag(entry, tag, config)
            display_action_confirmation(entry, f"@{tag}")
        return

    # Handle untag action: bt 1 untag @backend  or  bt 1 untag backend
    if action == "untag":
        if not args:
            raise InvalidActionError("untag requires a tag. Usage: bt 1 untag @backend")
        tag = args[0].lstrip("@")
        for entry_id in entry_ids:
            path = entry_path_from_id(entry_id, config)
            if path is None:
                console.print(f"  [red]Entry {entry_id[:8]} not found.[/red]")
                continue
            entry = load_entry(path)
            handle_remove_tag(entry, tag, config)
            display_action_confirmation(entry, f"untag @{tag}")
        return

    # Standard actions
    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        raise InvalidActionError(f"Unknown action: '{action}'")

    for entry_id in entry_ids:
        path = entry_path_from_id(entry_id, config)
        if path is None:
            console.print(f"  [red]Entry {entry_id[:8]} not found.[/red]")
            continue
        entry = load_entry(path)
        try:
            handler(entry, args, config)
            display_action_confirmation(entry, action)
        except DwnError as e:
            console.print(f"  [red]{e.format_message()}[/red]")


@click.command("undo")
@click.pass_context
def undo_cmd(ctx):
    """Undo the last action."""
    config = ctx.obj.get("config")
    record = pop_undo(config=config)
    if record is None:
        console.print("  [dim]Nothing to undo.[/dim]")
        return
    apply_undo(record, config)
