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
    """Mark a task as done. For recurring tasks, record completion for today."""
    _require_task(entry, "done")
    if entry.is_recurring():
        from datetime import date
        today_iso = date.today().isoformat()
        if today_iso in entry.completions:
            return  # already done today
        record_undo(entry.id, "done", {"completion_removed": today_iso}, config)
        entry.completions.append(today_iso)
        update_entry(entry, config)
    else:
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
    """Permanently delete an entry from disk, vector DB, and index."""
    path = entry_path_from_id(entry.id, config)
    # Save file content for undo before deleting
    file_content = None
    if path and path.exists():
        file_content = path.read_text()
        path.unlink()
    from bute.ai.vectors import is_available, delete as vec_delete
    if is_available():
        vec_delete(entry.id, config)
    try:
        from bute.db import delete_entry
        delete_entry(entry.id, config)
    except Exception:
        pass
    if file_content is not None:
        record_undo(entry.id, "delete", {"file_content": file_content}, config)


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
    # Re-index after manual edits so DB and embeddings stay in sync
    updated = load_entry(path)
    try:
        from bute.db import upsert_entry
        upsert_entry(updated, config)
    except Exception:
        pass
    from bute.ai import embed_entry
    embed_entry(updated.id, updated.body, config)


def handle_add_tag(entry: Entry, tag: str, config) -> None:
    """Add a tag to an entry (no duplicates)."""
    if tag not in entry.tags:
        record_undo(entry.id, "@tag", {"tag": tag}, config)
        entry.tags.append(tag)
    update_entry(entry, config)


def handle_title(entry: Entry, args: list[str], config) -> None:
    """Generate an AI topic sentence and prepend it to the entry body."""
    from bute.ai import is_llm_available, llm_send
    from bute.ai.prompts import title_prompt

    if not is_llm_available(config):
        raise DwnError("AI not configured. Run bt init.")

    title = llm_send(title_prompt(), entry.body, config).strip().strip('"')
    record_undo(entry.id, "title", {"body": entry.body}, config)
    entry.body = f"{title}\n\n{entry.body}"
    update_entry(entry, config)
    console.print(f"  [bold]{title}[/bold]")


def handle_later(entry: Entry, args: list[str], config) -> None:
    """Remove @today tag — defer task to Task log."""
    _require_task(entry, "later")
    if "today" in entry.tags:
        record_undo(entry.id, "later", {"tag": "today"}, config)
        entry.tags.remove("today")
        update_entry(entry, config)
    else:
        Console().print(f"  [dim]Not in today's log[/dim]")


def handle_backlog(entry: Entry, args: list[str], config) -> None:
    """Remove @today and @thisweek — send task to Backlog."""
    _require_task(entry, "backlog")
    removed = []
    if "today" in entry.tags:
        entry.tags.remove("today")
        removed.append("today")
    if "thisweek" in entry.tags:
        entry.tags.remove("thisweek")
        removed.append("thisweek")
    if removed:
        record_undo(entry.id, "backlog", {"tags": removed}, config)
        update_entry(entry, config)
    else:
        Console().print(f"  [dim]Already in backlog[/dim]")


# Metadata keys that map to entry fields
META_KEYS = {"due", "d", "date", "t", "time"}


def _is_meta_token(token: str) -> bool:
    """Check if a token is a key:value metadata token."""
    if ":" not in token:
        return False
    key = token.split(":", 1)[0].lower()
    return key in META_KEYS


def _parse_meta_tokens(tokens: list[str]) -> dict[str, str]:
    """Extract metadata key:value pairs from tokens."""
    meta = {}
    for token in tokens:
        key, value = token.split(":", 1)
        meta[key.lower()] = value
    return meta


def handle_set_meta(entry: Entry, meta: dict[str, str], config) -> None:
    """Update due date, scheduled date, or time on an entry."""
    from bute.parser import resolve_date, resolve_time

    prev = {}
    labels = []

    # due: or due:<date> (empty clears)
    if "due" in meta:
        prev["due"] = entry.due.isoformat() if entry.due else None
        if not meta["due"] or meta["due"].lower() == "none":
            entry.due = None
            labels.append("due:cleared")
        else:
            entry.due = resolve_date(meta["due"])
            labels.append(f"due:{entry.due}")

    # d: or date: (empty clears)
    raw_date = meta.get("d", meta.get("date"))
    if raw_date is not None:
        prev["scheduled_date"] = entry.scheduled_date.isoformat() if entry.scheduled_date else None
        if not raw_date or raw_date.lower() == "none":
            entry.scheduled_date = None
            labels.append("d:cleared")
        else:
            entry.scheduled_date = resolve_date(raw_date)
            labels.append(f"d:{entry.scheduled_date}")

    # t: or time: (empty clears)
    raw_time = meta.get("t", meta.get("time"))
    if raw_time is not None:
        prev["scheduled_time"] = entry.scheduled_time
        if not raw_time or raw_time.lower() == "none":
            entry.scheduled_time = None
            labels.append("t:cleared")
        else:
            entry.scheduled_time = resolve_time(raw_time)
            labels.append(f"t:{entry.scheduled_time}")

    record_undo(entry.id, "meta", prev, config)
    update_entry(entry, config)
    return " ".join(labels)


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

    # Delete undo: recreate the file from saved content
    if action == "delete":
        file_content = prev.get("file_content")
        if not file_content:
            raise DwnError(f"Entry {entry_id[:8]} — no saved content to restore.")
        from bute.storage import save_entry, load_entry as _load
        from bute.config import get_data_dir
        data_dir = get_data_dir(config)
        # Reconstruct the file path from entry metadata
        import frontmatter
        post = frontmatter.loads(file_content)
        created = post.metadata.get("created", "")
        if isinstance(created, str):
            from datetime import datetime
            created = datetime.fromisoformat(created)
        month_dir = data_dir / "entries" / created.strftime("%Y-%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        restored_path = month_dir / f"{entry_id}.md"
        restored_path.write_text(file_content)
        entry = _load(restored_path)
        # Re-index
        from bute.ai import embed_entry
        embed_entry(entry.id, entry.body, config)
        try:
            from bute.db import upsert_entry
            upsert_entry(entry, config)
        except Exception:
            pass
        display_action_confirmation(entry, "undo delete")
        return

    path = entry_path_from_id(entry_id, config)
    if path is None:
        raise DwnError(f"Entry {entry_id[:8]} not found — cannot undo.")
    entry = load_entry(path)

    if action in ("done", "drop"):
        if "completion_removed" in prev:
            # Undo a recurring done — remove the date from completions
            date_to_remove = prev["completion_removed"]
            if date_to_remove in entry.completions:
                entry.completions.remove(date_to_remove)
            update_entry(entry, config)
        else:
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
    elif action == "backlog":
        for tag in prev["tags"]:
            if tag not in entry.tags:
                entry.tags.append(tag)
        update_entry(entry, config)
    elif action == "title":
        entry.body = prev["body"]
        update_entry(entry, config)
    elif action == "meta":
        from datetime import date as date_type
        if "due" in prev:
            entry.due = date_type.fromisoformat(prev["due"]) if prev["due"] else None
        if "scheduled_date" in prev:
            entry.scheduled_date = date_type.fromisoformat(prev["scheduled_date"]) if prev["scheduled_date"] else None
        if "scheduled_time" in prev:
            entry.scheduled_time = prev["scheduled_time"]
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
    "open": handle_edit,
    "edit": handle_edit,
    "later": handle_later,
    "backlog": handle_backlog,
    "title": handle_title,
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
        return

    # Handle map: bt <n> map (single @ai-analysis note)
    if action == "map":
        if len(entry_ids) > 1:
            raise InvalidActionError(
                "map works on a single entry. Usage: bt 1 map"
            )
        entry_id = entry_ids[0]
        path = entry_path_from_id(entry_id, config)
        if path is None:
            console.print(f"  [red]Entry {entry_id[:8]} not found.[/red]")
            return
        entry = load_entry(path)
        if "ai-analysis" not in entry.tags:
            raise InvalidActionError("map only works on @ai-analysis notes.")
        from bute.display import display_analyze_map
        display_analyze_map(entry.tags[0] if entry.tags[0] != "ai-analysis" else "analysis", entry.body)
        return

    # Handle chat: bt <n> chat or bt <n> <m> chat (multi-entry)
    if action == "chat":
        entries = []
        for entry_id in entry_ids:
            path = entry_path_from_id(entry_id, config)
            if path is None:
                console.print(f"  [red]Entry {entry_id[:8]} not found.[/red]")
                return
            entries.append(load_entry(path))
        from bute.commands.chat import start_chat_session

        start_chat_session(entries, config)
        return

    # Handle metadata updates: bt 3 due:friday, bt 3 d:tomorrow t:14.30
    if _is_meta_token(action):
        all_meta_tokens = [action] + [a for a in args if _is_meta_token(a)]
        meta = _parse_meta_tokens(all_meta_tokens)
        for entry_id in entry_ids:
            path = entry_path_from_id(entry_id, config)
            if path is None:
                console.print(f"  [red]Entry {entry_id[:8]} not found.[/red]")
                continue
            entry = load_entry(path)
            try:
                label = handle_set_meta(entry, meta, config)
                display_action_confirmation(entry, label)
            except (ValueError, KeyError) as e:
                console.print(f"  [red]Invalid value: {e}[/red]")
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
            if action not in ("edit", "open"):
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
