"""Action command — handles number-based actions (done, drop, etc.)."""

import os
import shutil
import subprocess
from datetime import date

import click
from rich.console import Console

from bute.display import display_action_confirmation, display_entry_full
from bute.errors import DwnError, InvalidActionError
from bute.models import Entry, EntryType, TaskStatus
from bute.state import pop_undo, record_undo, resolve_numbers
from bute.storage import entry_path_from_id, load_entry, update_entry

console = Console()


_MAX_RANGE_SIZE = 100


def _expand_number_token(tok: str) -> list[int]:
    """Expand a digit token or `start-end` range into a list of ints.

    Returns None if the token is not a number/range.
    Raises InvalidActionError for invalid ranges.
    """
    if tok.isdigit():
        return [int(tok)]
    if "-" in tok:
        parts = tok.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            start, end = int(parts[0]), int(parts[1])
            if start < 1:
                raise InvalidActionError(
                    f"Range '{tok}' starts below 1; entry numbers are 1-indexed."
                )
            if end < start:
                raise InvalidActionError(
                    f"Range '{tok}' is descending. Use {end}-{start} instead."
                )
            if end - start + 1 > _MAX_RANGE_SIZE:
                raise InvalidActionError(
                    f"Range '{tok}' exceeds {_MAX_RANGE_SIZE} entries."
                )
            return list(range(start, end + 1))
    return None


def parse_action_tokens(
    tokens: tuple[str, ...],
) -> tuple[list[int], str, list[str]]:
    """Parse action tokens into (numbers, action, args).

    Examples:
        ("1", "3", "done") → ([1, 3], "done", [])
        ("1-4", "12", "done") → ([1, 2, 3, 4, 12], "done", [])
    """
    numbers = []
    rest = list(tokens)

    # Consume leading digit tokens and ranges
    while rest:
        expanded = _expand_number_token(rest[0])
        if expanded is None:
            break
        numbers.extend(expanded)
        rest.pop(0)

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
        today_iso = date.today().isoformat()
        if today_iso in entry.completions:
            return  # already done today
        record_undo(entry.id, "done", {"completion_removed": today_iso}, config)
        entry.completions.append(today_iso)
        update_entry(entry, config)
    else:
        record_undo(
            entry.id, "done",
            {
                "status": entry.status.value,
                "completed_date": entry.completed_date.isoformat() if entry.completed_date else None,
                "focus_date": entry.focus_date.isoformat() if entry.focus_date else None,
                "week_date": entry.week_date.isoformat() if entry.week_date else None,
            },
            config,
        )
        entry.status = TaskStatus.DONE
        entry.completed_date = date.today()
        # Resolved tasks drop their focus state — they won't show in any view
        # anyway, so keeping it is dead metadata.
        entry.focus_date = None
        entry.week_date = None
        update_entry(entry, config)


def handle_drop(entry: Entry, args: list[str], config) -> None:
    """Mark a task as dropped."""
    _require_task(entry, "drop")
    record_undo(
        entry.id, "drop",
        {
            "status": entry.status.value,
            "completed_date": entry.completed_date.isoformat() if entry.completed_date else None,
            "focus_date": entry.focus_date.isoformat() if entry.focus_date else None,
            "week_date": entry.week_date.isoformat() if entry.week_date else None,
        },
        config,
    )
    entry.status = TaskStatus.DROPPED
    entry.completed_date = date.today()
    entry.focus_date = None
    entry.week_date = None
    update_entry(entry, config)


def handle_delete(entry: Entry, args: list[str], config) -> None:
    """Move an entry to .trash/ (recoverable via bt trash → bt <n> restore, or bt undo)."""
    from bute.storage import trash_entry

    trashed = trash_entry(entry.id, config)
    if trashed is not None:
        record_undo(entry.id, "delete", {"trashed": True}, config)


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
    _invalidate_vector(entry.id, config)


def _reindex_entry(path, config):
    """Re-index an entry after edits. Drops its vector so `bt like` re-embeds it."""
    updated = load_entry(path)
    try:
        from bute.db import upsert_entry
        upsert_entry(updated, config)
    except Exception:
        pass
    _invalidate_vector(updated.id, config)


def _invalidate_vector(entry_id: str, config) -> None:
    """Delete an entry's stale vector. Cheap — no model load. Re-embedded lazily."""
    try:
        from bute.ai.vectors import is_available, delete as vec_delete
        if is_available():
            vec_delete(entry_id, config)
    except Exception:
        pass


def handle_edit(entry: Entry, args: list[str], config) -> None:
    """Open entry in $EDITOR for full editing."""
    path = entry_path_from_id(entry.id, config)
    if path is None:
        raise DwnError("Entry file not found.")
    editor = os.environ.get("EDITOR", "nano")
    subprocess.call([editor, str(path)])
    _reindex_entry(path, config)


def handle_show(entry: Entry, args: list[str], config) -> None:
    """Render the entry as markdown — via glow when installed, Rich otherwise.

    glow strips the YAML frontmatter itself, so it gets the file path directly.
    Always opens glow's pager (-p) so reading is a real glow session — scroll,
    search with /, quit with q — rather than a dump into scrollback.
    """
    path = entry_path_from_id(entry.id, config)
    if path is not None and shutil.which("glow"):
        subprocess.call(["glow", "-p", str(path)])
        return
    display_entry_full(entry)


def handle_add_tag(entry: Entry, tag: str, config) -> None:
    """Add a tag to an entry (no duplicates)."""
    if tag not in entry.tags:
        record_undo(entry.id, "@tag", {"tag": tag}, config)
        entry.tags.append(tag)
    update_entry(entry, config)



def handle_later(entry: Entry, args: list[str], config) -> None:
    """Clear focus_date — defer task to Task log."""
    _require_task(entry, "later")
    if entry.focus_date is not None:
        record_undo(
            entry.id, "later",
            {"focus_date": entry.focus_date.isoformat()},
            config,
        )
        entry.focus_date = None
        update_entry(entry, config)
    else:
        Console().print(f"  [dim]Not in today's log[/dim]")


def handle_focus(entry: Entry, args: list[str], config) -> None:
    """Set focus_date and week_date — pull task into Focus Log."""
    from bute.ritual_ops import week_anchor
    _require_task(entry, "focus")
    today = date.today()
    anchor = week_anchor(today, config)
    if entry.focus_date == today and entry.week_date == anchor:
        Console().print(f"  [dim]Already in Focus Log[/dim]")
        return
    prev = {
        "focus_date": entry.focus_date.isoformat() if entry.focus_date else None,
        "week_date": entry.week_date.isoformat() if entry.week_date else None,
    }
    record_undo(entry.id, "focus", prev, config)
    entry.focus_date = today
    entry.week_date = anchor
    update_entry(entry, config)


def handle_backlog(entry: Entry, args: list[str], config) -> None:
    """Clear focus_date and week_date — send task to Backlog."""
    _require_task(entry, "backlog")
    if entry.focus_date is None and entry.week_date is None:
        Console().print(f"  [dim]Already in backlog[/dim]")
        return
    prev = {
        "focus_date": entry.focus_date.isoformat() if entry.focus_date else None,
        "week_date": entry.week_date.isoformat() if entry.week_date else None,
    }
    record_undo(entry.id, "backlog", prev, config)
    entry.focus_date = None
    entry.week_date = None
    update_entry(entry, config)


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
        record_undo(entry.id, "clear", {"tag": tag}, config)
        entry.tags.remove(tag)
        update_entry(entry, config)
    else:
        Console().print(f"  [dim]@{tag} not on this entry[/dim]")


# Clearable fields and their entry attribute names
CLEAR_FIELDS = {"due", "d", "t", "time", "date", "repeat", "!"}


def handle_clear(entry: Entry, field: str, config) -> str:
    """Clear a metadata field. Returns label for confirmation."""
    if field == "!" or field == "important":
        if not entry.important:
            Console().print("  [dim]Not marked important[/dim]")
            return ""
        record_undo(entry.id, "clear", {"important": True}, config)
        entry.important = False
        update_entry(entry, config)
        return "clear !"
    elif field == "due":
        if entry.due is None:
            Console().print("  [dim]No due date set[/dim]")
            return ""
        record_undo(entry.id, "clear", {"due": entry.due.isoformat()}, config)
        entry.due = None
        update_entry(entry, config)
        return "clear due"
    elif field in ("d", "date"):
        if entry.scheduled_date is None:
            Console().print("  [dim]No scheduled date set[/dim]")
            return ""
        record_undo(entry.id, "clear", {"scheduled_date": entry.scheduled_date.isoformat()}, config)
        entry.scheduled_date = None
        update_entry(entry, config)
        return "clear d"
    elif field in ("t", "time"):
        if entry.scheduled_time is None:
            Console().print("  [dim]No time set[/dim]")
            return ""
        record_undo(entry.id, "clear", {"scheduled_time": entry.scheduled_time}, config)
        entry.scheduled_time = None
        update_entry(entry, config)
        return "clear t"
    elif field == "repeat":
        if entry.repeat is None:
            Console().print("  [dim]No repeat set[/dim]")
            return ""
        record_undo(entry.id, "clear", {"repeat": entry.repeat}, config)
        entry.repeat = None
        update_entry(entry, config)
        return "clear repeat"
    else:
        raise InvalidActionError(f"Cannot clear '{field}'. Clearable: @tag, !, due, d, t, repeat")


def apply_undo(record: dict, config) -> None:
    """Reverse a recorded action."""
    entry_id = record["entry_id"]
    action = record["action"]
    prev = record["prev"]

    # Delete undo: restore from trash, or (legacy records) from saved content
    if action == "delete":
        from bute.storage import restore_entry, trash_dir
        if (trash_dir(config) / f"{entry_id}.md").exists():
            entry = restore_entry(entry_id, config)
        else:
            # Legacy undo record from before the trash existed: recreate from saved text
            file_content = prev.get("file_content")
            if not file_content:
                raise DwnError(f"Entry {entry_id[:8]} — nothing in trash and no saved content to restore.")
            import frontmatter
            from datetime import datetime
            from bute.config import get_data_dir
            from bute.storage import load_entry as _load
            post = frontmatter.loads(file_content)
            created = post.metadata.get("created", "")
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            entry_type = post.metadata.get("type", "note")
            month_dir = get_data_dir(config) / "entries" / entry_type / created.strftime("%Y-%m")
            month_dir.mkdir(parents=True, exist_ok=True)
            restored_path = month_dir / f"{entry_id}.md"
            restored_path.write_text(file_content)
            entry = _load(restored_path)
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
            from datetime import date as date_type
            entry.status = TaskStatus(prev["status"])
            prev_completed = prev.get("completed_date")
            entry.completed_date = date_type.fromisoformat(prev_completed) if prev_completed else None
            if "focus_date" in prev:
                entry.focus_date = date_type.fromisoformat(prev["focus_date"]) if prev["focus_date"] else None
            if "week_date" in prev:
                entry.week_date = date_type.fromisoformat(prev["week_date"]) if prev["week_date"] else None
            update_entry(entry, config)
    elif action == "!":
        entry.important = prev["important"]
        update_entry(entry, config)
    elif action == "@tag":
        tag = prev["tag"]
        if tag in entry.tags:
            entry.tags.remove(tag)
        update_entry(entry, config)
    elif action == "clear":
        # Restore whichever field was cleared
        from datetime import date as date_type
        if "tag" in prev:
            tag = prev["tag"]
            if tag not in entry.tags:
                entry.tags.append(tag)
        if "important" in prev:
            entry.important = prev["important"]
        if "due" in prev:
            entry.due = date_type.fromisoformat(prev["due"]) if prev["due"] else None
        if "scheduled_date" in prev:
            entry.scheduled_date = date_type.fromisoformat(prev["scheduled_date"]) if prev["scheduled_date"] else None
        if "scheduled_time" in prev:
            entry.scheduled_time = prev["scheduled_time"]
        if "repeat" in prev:
            entry.repeat = prev["repeat"]
        update_entry(entry, config)
    elif action == "later":
        from datetime import date as date_type
        entry.focus_date = date_type.fromisoformat(prev["focus_date"]) if prev.get("focus_date") else None
        update_entry(entry, config)
    elif action == "backlog":
        from datetime import date as date_type
        entry.focus_date = date_type.fromisoformat(prev["focus_date"]) if prev.get("focus_date") else None
        entry.week_date = date_type.fromisoformat(prev["week_date"]) if prev.get("week_date") else None
        update_entry(entry, config)
    elif action == "focus":
        from datetime import date as date_type
        entry.focus_date = date_type.fromisoformat(prev["focus_date"]) if prev.get("focus_date") else None
        entry.week_date = date_type.fromisoformat(prev["week_date"]) if prev.get("week_date") else None
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
    "show": handle_show,
    "read": handle_show,
    "view": handle_show,
    "later": handle_later,
    "focus": handle_focus,
    "backlog": handle_backlog,
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

    # Handle restore: bt <n> restore — only meaningful from the bt trash view
    if action == "restore":
        from bute.state import load_state
        from bute.storage import restore_entry
        if load_state(config).get("view") != "trash":
            console.print("  [red]Those numbers are not in the trash. Run [bold]bt trash[/bold] first.[/red]")
            return
        for entry_id in entry_ids:
            try:
                entry = restore_entry(entry_id, config)
            except DwnError as e:
                console.print(f"  [red]{e.format_message()}[/red]")
                continue
            display_action_confirmation(entry, "restore")
        return

    # Handle @tag action — collect all @tags from action + args
    if action.startswith("@") and len(action) > 1:
        tags = [action[1:]] + [a[1:] for a in args if a.startswith("@") and len(a) > 1]
        label = "+" + " +".join(f"@{t}" for t in tags)
        for entry_id in entry_ids:
            path = entry_path_from_id(entry_id, config)
            if path is None:
                console.print(f"  [red]Entry {entry_id[:8]} not found.[/red]")
                continue
            entry = load_entry(path)
            for tag in tags:
                handle_add_tag(entry, tag, config)
            display_action_confirmation(entry, label)
        return

    # Handle clear action: bt 1 clear @backend, bt 1 clear !, bt 1 clear due, etc.
    if action == "clear":
        if not args:
            raise InvalidActionError(
                "clear requires a field. Usage: bt 1 clear @tag | ! | due | d | t | repeat"
            )
        field = args[0]
        # Tag removal: bt 1 clear @backend  or  bt 1 clear backend
        if field.startswith("@") or field not in CLEAR_FIELDS:
            tag = field.lstrip("@")
            for entry_id in entry_ids:
                path = entry_path_from_id(entry_id, config)
                if path is None:
                    console.print(f"  [red]Entry {entry_id[:8]} not found.[/red]")
                    continue
                entry = load_entry(path)
                handle_remove_tag(entry, tag, config)
                display_action_confirmation(entry, f"clear @{tag}")
            return
        # Metadata removal: bt 1 clear due, bt 1 clear !, etc.
        for entry_id in entry_ids:
            path = entry_path_from_id(entry_id, config)
            if path is None:
                console.print(f"  [red]Entry {entry_id[:8]} not found.[/red]")
                continue
            entry = load_entry(path)
            label = handle_clear(entry, field, config)
            if label:
                display_action_confirmation(entry, label)
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
            if action not in ("edit", "open", "show", "read", "view"):
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
