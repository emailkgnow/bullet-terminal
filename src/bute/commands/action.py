"""Action command — handles number-based actions (done, drop, etc.)."""

import click
from rich.console import Console

from bute.display import display_action_confirmation
from bute.errors import DwnError, InvalidActionError
from bute.models import Entry, EntryType, TaskStatus
from bute.state import resolve_numbers
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
    entry.status = TaskStatus.DONE
    update_entry(entry, config)


def handle_drop(entry: Entry, args: list[str], config) -> None:
    """Mark a task as dropped."""
    _require_task(entry, "drop")
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
    entry.important = not entry.important
    update_entry(entry, config)


def handle_add_tag(entry: Entry, tag: str, config) -> None:
    """Add a tag to an entry (no duplicates)."""
    if tag not in entry.tags:
        entry.tags.append(tag)
    update_entry(entry, config)


# Action dispatch table
ACTION_HANDLERS = {
    "done": handle_done,
    "drop": handle_drop,
    "delete": handle_delete,
    "!": handle_toggle_important,
}


@click.command("action", hidden=True)
@click.argument("tokens", nargs=-1, required=True)
@click.pass_context
def action_cmd(ctx, tokens):
    """Perform actions on numbered entries."""
    config = ctx.obj.get("config")
    numbers, action, args = parse_action_tokens(tokens)
    entry_ids = resolve_numbers(numbers, config)

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
