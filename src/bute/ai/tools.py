"""AI tool schema definitions for OpenAI function calling.

Defines the tools available to the LLM during chat sessions.
Execution logic lives in separate modules (Tasks 2-3).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

_query_entries = {
    "type": "function",
    "function": {
        "name": "query_entries",
        "description": (
            "Query entries by type, date range, tags, status, importance, or due date. "
            "All parameters are optional — omit filters to get recent entries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["task", "note", "journal", "calendar"],
                    "description": "Filter by entry type.",
                },
                "date_from": {
                    "type": "string",
                    "description": "Start date (inclusive) in YYYY-MM-DD format.",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date (inclusive) in YYYY-MM-DD format.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Include entries that have ALL of these tags.",
                },
                "exclude_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exclude entries that have any of these tags.",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "done", "dropped"],
                    "description": "Filter tasks by status.",
                },
                "important": {
                    "type": "boolean",
                    "description": "If true, only return important entries.",
                },
                "has_due": {
                    "type": "boolean",
                    "description": "If true, only return entries with a due date.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of entries to return. Default 20.",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}

_search_text = {
    "type": "function",
    "function": {
        "name": "search_text",
        "description": "Full-text search across entry bodies and tags.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string.",
                },
                "type": {
                    "type": "string",
                    "enum": ["task", "note", "journal", "calendar"],
                    "description": "Filter results to a specific entry type.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results. Default 10.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

_search_similar = {
    "type": "function",
    "function": {
        "name": "search_similar",
        "description": "Semantic similarity search — find entries related to a query by meaning, not exact keywords.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The text to find similar entries for.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results. Default 10.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------

_create_entry = {
    "type": "function",
    "function": {
        "name": "create_entry",
        "description": (
            "Create a new entry (task, note, journal, or calendar event). "
            "The user will be asked to confirm before the entry is saved."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "signifier": {
                    "type": "string",
                    "enum": [".", "-", "=", "o"],
                    "description": ". = task, - = note, = = journal, o = calendar event.",
                },
                "body": {
                    "type": "string",
                    "description": "The entry text.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to attach (without @ prefix).",
                },
                "due": {
                    "type": "string",
                    "description": "Due date in YYYY-MM-DD format (tasks only).",
                },
                "date": {
                    "type": "string",
                    "description": "Scheduled date in YYYY-MM-DD format.",
                },
                "time": {
                    "type": "string",
                    "description": "Scheduled time in HH:MM 24-hour format.",
                },
                "important": {
                    "type": "boolean",
                    "description": "Mark the entry as important.",
                },
            },
            "required": ["signifier", "body"],
            "additionalProperties": False,
        },
    },
}

_add_tag = {
    "type": "function",
    "function": {
        "name": "add_tag",
        "description": "Add a tag to one or more entries.",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of entry ULIDs to tag.",
                },
                "tag": {
                    "type": "string",
                    "description": "Tag to add (without @ prefix).",
                },
            },
            "required": ["entry_ids", "tag"],
            "additionalProperties": False,
        },
    },
}

_remove_tag = {
    "type": "function",
    "function": {
        "name": "remove_tag",
        "description": "Remove a tag from one or more entries.",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of entry ULIDs to untag.",
                },
                "tag": {
                    "type": "string",
                    "description": "Tag to remove (without @ prefix).",
                },
            },
            "required": ["entry_ids", "tag"],
            "additionalProperties": False,
        },
    },
}

_mark_done = {
    "type": "function",
    "function": {
        "name": "mark_done",
        "description": "Mark one or more tasks as done.",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task ULIDs to mark done.",
                },
            },
            "required": ["entry_ids"],
            "additionalProperties": False,
        },
    },
}

_mark_dropped = {
    "type": "function",
    "function": {
        "name": "mark_dropped",
        "description": "Mark one or more tasks as dropped (consciously removed).",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task ULIDs to drop.",
                },
            },
            "required": ["entry_ids"],
            "additionalProperties": False,
        },
    },
}

_toggle_important = {
    "type": "function",
    "function": {
        "name": "toggle_important",
        "description": "Toggle the important flag on one or more entries.",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of entry ULIDs to toggle.",
                },
            },
            "required": ["entry_ids"],
            "additionalProperties": False,
        },
    },
}

_update_due = {
    "type": "function",
    "function": {
        "name": "update_due",
        "description": "Set or update the due date on one or more tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task ULIDs to update.",
                },
                "due_date": {
                    "type": "string",
                    "description": "New due date in YYYY-MM-DD format.",
                },
            },
            "required": ["entry_ids", "due_date"],
            "additionalProperties": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Display tools
# ---------------------------------------------------------------------------

_display_map = {
    "type": "function",
    "function": {
        "name": "display_map",
        "description": "Display a mind map visualization of a tag's analysis clusters.",
        "parameters": {
            "type": "object",
            "properties": {
                "tag": {
                    "type": "string",
                    "description": "Tag to visualize (without @ prefix).",
                },
            },
            "required": ["tag"],
            "additionalProperties": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# All tool schemas including search_similar (embeddings-dependent).
TOOL_SCHEMAS: list[dict] = [
    _query_entries,
    _search_text,
    _search_similar,
    _create_entry,
    _add_tag,
    _remove_tag,
    _mark_done,
    _mark_dropped,
    _toggle_important,
    _update_due,
    _display_map,
]


def get_tool_schemas(*, embeddings_available: bool = True) -> list[dict]:
    """Return tool schemas, conditionally excluding search_similar.

    Args:
        embeddings_available: When False, search_similar is excluded
            since it requires fastembed + sqlite-vec.
    """
    if embeddings_available:
        return list(TOOL_SCHEMAS)
    return [s for s in TOOL_SCHEMAS if s["function"]["name"] != "search_similar"]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


def execute_tool(name: str, arguments: dict, config=None) -> str:
    """Execute a tool call and return the result as a string for the LLM."""
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return f"Unknown tool: {name}"
    return handler(arguments, config)


def _handle_query_entries(args: dict, config) -> str:
    from bute.ai.prompts import format_entries
    from bute.storage import query_and_load

    kwargs: dict = {}
    if "type" in args:
        kwargs["type"] = args["type"]
    if "status" in args:
        kwargs["status"] = args["status"]
    if "important" in args and args["important"]:
        kwargs["important"] = True
    if "has_due" in args and args["has_due"]:
        kwargs["has_due"] = True
    if "date_from" in args:
        kwargs["created_since"] = args["date_from"]
    if "date_to" in args:
        kwargs["created_until"] = args["date_to"]

    tags = args.get("tags", [])
    exclude_tags = args.get("exclude_tags", [])
    if tags:
        kwargs["tag"] = tags[0]

    limit = args.get("limit", 50)
    entries = query_and_load(config, **kwargs)

    # Apply remaining tag filters in Python
    if len(tags) > 1:
        for t in tags[1:]:
            entries = [e for e in entries if t in e.tags]
    if exclude_tags:
        for t in exclude_tags:
            entries = [e for e in entries if t not in e.tags]

    entries = entries[:limit]

    if not entries:
        return "No entries found."
    return f"{len(entries)} entries:\n\n{format_entries(entries)}"


def _handle_search_text(args: dict, config) -> str:
    from bute.ai.prompts import format_entries
    from bute.db import search_text
    from bute.storage import entry_path_from_id, load_entry

    query = args["query"]
    entry_type = args.get("type")
    limit = args.get("limit", 20)

    results = search_text(query, type=entry_type, limit=limit, config=config)
    entries = []
    for entry_id, _ in results:
        path = entry_path_from_id(entry_id, config)
        if path:
            try:
                entries.append(load_entry(path))
            except Exception:
                continue

    if not entries:
        return "No entries found."
    return f"{len(entries)} entries:\n\n{format_entries(entries)}"


def _handle_search_similar(args: dict, config) -> str:
    from bute.ai import search_similar
    from bute.ai.prompts import format_entries
    from bute.storage import entry_path_from_id, load_entry

    query = args["query"]
    limit = args.get("limit", 10)

    results = search_similar(query, limit=limit, config=config)
    entries = []
    for entry_id, _distance in results:
        path = entry_path_from_id(entry_id, config)
        if path:
            try:
                entries.append(load_entry(path))
            except Exception:
                continue

    if not entries:
        return "No similar entries found."
    return f"{len(entries)} entries:\n\n{format_entries(entries)}"


# ---------------------------------------------------------------------------
# Helper functions for write tools
# ---------------------------------------------------------------------------

_SIGNIFIER_TO_TYPE = {
    ".": "task",
    "-": "note",
    "=": "journal",
    "o": "calendar",
}


def _load_entries_by_ids(
    entry_ids: list[str], config
) -> list["tuple[str, Entry | None]"]:
    """Load Entry objects from ULIDs.

    Returns list of (entry_id, Entry | None) tuples. None when not found.
    """
    from bute.storage import entry_path_from_id, load_entry

    results = []
    for eid in entry_ids:
        path = entry_path_from_id(eid, config)
        if path is None:
            results.append((eid, None))
        else:
            try:
                results.append((eid, load_entry(path)))
            except Exception:
                results.append((eid, None))
    return results


def _entry_summary(entry) -> str:
    """One-line summary of an entry for confirmation display."""
    from bute.models import EntryType

    icon_map = {
        EntryType.TASK: ".",
        EntryType.NOTE: "-",
        EntryType.JOURNAL: "=",
        EntryType.CALENDAR: "o",
    }
    icon = icon_map.get(entry.type, "?")
    important = "!" if entry.important else ""
    body = entry.body[:60] + ("..." if len(entry.body) > 60 else "")
    tags = " ".join(f"@{t}" for t in entry.tags) if entry.tags else ""
    parts = [f"{important}{icon} {body}"]
    if tags:
        parts.append(tags)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Confirmation functions
# ---------------------------------------------------------------------------


def _confirm_action(description: str) -> bool:
    """Single-entry confirmation prompt. Returns True if user confirms."""
    import click

    return click.confirm(f"  {description}", default=True)


def _confirm_batch(
    description: str, entry_summaries: list[str]
) -> list[int] | None:
    """Batch confirmation with y/n/p.

    For single entries: simple y/n (no pick option).
    For multiple entries: y/n/p (pick) where p lets user select indices.
    Returns list of 0-based indices to apply, or None if cancelled.
    """
    import click
    from rich.console import Console

    console = Console()
    console.print(f"\n  [bold]{description}[/bold]")
    for i, summary in enumerate(entry_summaries):
        console.print(f"    {i + 1}. {summary}")

    if len(entry_summaries) == 1:
        # Simple y/n for single entry
        if click.confirm("  Apply?", default=True):
            return [0]
        return None

    # Multi-entry: y/n/p
    choice = click.prompt(
        "  Apply to all? [y]es / [n]o / [p]ick",
        type=click.Choice(["y", "n", "p"], case_sensitive=False),
        default="y",
    )
    if choice == "y":
        return list(range(len(entry_summaries)))
    elif choice == "n":
        return None
    else:
        # Pick mode
        raw = click.prompt("  Enter numbers (e.g. 1 3)")
        try:
            indices = [int(x) - 1 for x in raw.split()]
            return [i for i in indices if 0 <= i < len(entry_summaries)]
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Write tool handlers
# ---------------------------------------------------------------------------


def _handle_create_entry(args: dict, config) -> str:
    """Create a new entry with confirmation."""
    from datetime import date

    import click

    from bute.ai import embed_entry
    from bute.display import confirm_capture
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    signifier = args["signifier"]
    body = args["body"]
    type_str = _SIGNIFIER_TO_TYPE.get(signifier)
    if type_str is None:
        return f"Invalid signifier: {signifier}"

    entry_type = EntryType(type_str)

    # Build kwargs for Entry.create
    create_kwargs: dict = {
        "entry_type": entry_type,
        "body": body,
    }
    if args.get("tags"):
        create_kwargs["tags"] = list(args["tags"])
    if args.get("important"):
        create_kwargs["important"] = True
    if args.get("due"):
        create_kwargs["due"] = date.fromisoformat(args["due"])
    if args.get("date"):
        create_kwargs["scheduled_date"] = date.fromisoformat(args["date"])
    if args.get("time"):
        create_kwargs["scheduled_time"] = args["time"]

    entry = Entry.create(**create_kwargs)

    # Confirmation
    summary = _entry_summary(entry)
    if not _confirm_action(f"Create: {summary}"):
        return "Cancelled — entry not created."

    save_entry(entry, config)
    embed_entry(entry.id, entry.body, config)
    return f"Created {entry_type.value}: {body}"


def _handle_add_tag(args: dict, config) -> str:
    """Add a tag to one or more entries."""
    from bute.commands.action import handle_add_tag

    entry_ids = args["entry_ids"]
    tag = args["tag"]
    loaded = _load_entries_by_ids(entry_ids, config)

    # Check for missing entries
    missing = [eid for eid, entry in loaded if entry is None]
    if len(missing) == len(loaded):
        return f"Error: no entries found ({', '.join(e[:8] for e in missing)})"

    found = [(eid, entry) for eid, entry in loaded if entry is not None]
    summaries = [_entry_summary(entry) for _, entry in found]
    indices = _confirm_batch(f"Add @{tag} to:", summaries)
    if indices is None:
        return "Cancelled — no changes made."

    applied = 0
    for idx in indices:
        _, entry = found[idx]
        handle_add_tag(entry, tag, config)
        applied += 1

    msg = f"Applied @{tag} to {applied} entry(ies)."
    if missing:
        msg += f" ({len(missing)} not found)"
    return msg


def _handle_remove_tag(args: dict, config) -> str:
    """Remove a tag from one or more entries."""
    from bute.commands.action import handle_remove_tag

    entry_ids = args["entry_ids"]
    tag = args["tag"]
    loaded = _load_entries_by_ids(entry_ids, config)

    missing = [eid for eid, entry in loaded if entry is None]
    if len(missing) == len(loaded):
        return f"Error: no entries found ({', '.join(e[:8] for e in missing)})"

    found = [(eid, entry) for eid, entry in loaded if entry is not None]
    summaries = [_entry_summary(entry) for _, entry in found]
    indices = _confirm_batch(f"Remove @{tag} from:", summaries)
    if indices is None:
        return "Cancelled — no changes made."

    applied = 0
    for idx in indices:
        _, entry = found[idx]
        handle_remove_tag(entry, tag, config)
        applied += 1

    msg = f"Applied: removed @{tag} from {applied} entry(ies)."
    if missing:
        msg += f" ({len(missing)} not found)"
    return msg


def _handle_mark_done(args: dict, config) -> str:
    """Mark one or more tasks as done."""
    from bute.commands.action import ACTION_HANDLERS

    entry_ids = args["entry_ids"]
    loaded = _load_entries_by_ids(entry_ids, config)

    missing = [eid for eid, entry in loaded if entry is None]
    if len(missing) == len(loaded):
        return f"Error: no entries found ({', '.join(e[:8] for e in missing)})"

    found = [(eid, entry) for eid, entry in loaded if entry is not None]
    summaries = [_entry_summary(entry) for _, entry in found]
    indices = _confirm_batch("Mark done:", summaries)
    if indices is None:
        return "Cancelled — no changes made."

    handler = ACTION_HANDLERS["done"]
    applied = 0
    errors = []
    for idx in indices:
        _, entry = found[idx]
        try:
            handler(entry, [], config)
            applied += 1
        except Exception as e:
            errors.append(f"{entry.body[:30]}: {e}")

    msg = f"Applied done to {applied} entry(ies)."
    if missing:
        msg += f" ({len(missing)} not found)"
    if errors:
        msg += f" Errors: {'; '.join(errors)}"
    return msg


def _handle_mark_dropped(args: dict, config) -> str:
    """Mark one or more tasks as dropped."""
    from bute.commands.action import ACTION_HANDLERS

    entry_ids = args["entry_ids"]
    loaded = _load_entries_by_ids(entry_ids, config)

    missing = [eid for eid, entry in loaded if entry is None]
    if len(missing) == len(loaded):
        return f"Error: no entries found ({', '.join(e[:8] for e in missing)})"

    found = [(eid, entry) for eid, entry in loaded if entry is not None]
    summaries = [_entry_summary(entry) for _, entry in found]
    indices = _confirm_batch("Mark dropped:", summaries)
    if indices is None:
        return "Cancelled — no changes made."

    handler = ACTION_HANDLERS["drop"]
    applied = 0
    errors = []
    for idx in indices:
        _, entry = found[idx]
        try:
            handler(entry, [], config)
            applied += 1
        except Exception as e:
            errors.append(f"{entry.body[:30]}: {e}")

    msg = f"Applied dropped to {applied} entry(ies)."
    if missing:
        msg += f" ({len(missing)} not found)"
    if errors:
        msg += f" Errors: {'; '.join(errors)}"
    return msg


def _handle_toggle_important(args: dict, config) -> str:
    """Toggle the important flag on one or more entries."""
    from bute.commands.action import ACTION_HANDLERS

    entry_ids = args["entry_ids"]
    loaded = _load_entries_by_ids(entry_ids, config)

    missing = [eid for eid, entry in loaded if entry is None]
    if len(missing) == len(loaded):
        return f"Error: no entries found ({', '.join(e[:8] for e in missing)})"

    found = [(eid, entry) for eid, entry in loaded if entry is not None]
    summaries = [_entry_summary(entry) for _, entry in found]
    indices = _confirm_batch("Toggle important:", summaries)
    if indices is None:
        return "Cancelled — no changes made."

    handler = ACTION_HANDLERS["!"]
    applied = 0
    for idx in indices:
        _, entry = found[idx]
        handler(entry, [], config)
        applied += 1

    msg = f"Applied toggle important to {applied} entry(ies)."
    if missing:
        msg += f" ({len(missing)} not found)"
    return msg


def _handle_update_due(args: dict, config) -> str:
    """Set or update the due date on one or more tasks."""
    from datetime import date

    from bute.storage import update_entry

    entry_ids = args["entry_ids"]
    due_str = args["due_date"]
    try:
        due_date = date.fromisoformat(due_str)
    except ValueError:
        return f"Invalid date format: {due_str} (expected YYYY-MM-DD)"

    loaded = _load_entries_by_ids(entry_ids, config)

    missing = [eid for eid, entry in loaded if entry is None]
    if len(missing) == len(loaded):
        return f"Error: no entries found ({', '.join(e[:8] for e in missing)})"

    found = [(eid, entry) for eid, entry in loaded if entry is not None]
    summaries = [_entry_summary(entry) for _, entry in found]
    indices = _confirm_batch(f"Set due date to {due_date}:", summaries)
    if indices is None:
        return "Cancelled — no changes made."

    applied = 0
    for idx in indices:
        _, entry = found[idx]
        entry.due = due_date
        update_entry(entry, config)
        applied += 1

    msg = f"Applied due:{due_date} to {applied} entry(ies)."
    if missing:
        msg += f" ({len(missing)} not found)"
    return msg


def _handle_display_map(args: dict, config) -> str:
    """Display a mind map for a tag's analysis."""
    from bute.db import get_tag_stage
    from bute.display import display_analyze_map

    tag = args["tag"]

    # Check for cached analysis
    stage = get_tag_stage(tag, config)
    if stage and stage.get("analysis"):
        display_analyze_map(tag, stage["analysis"])
        return f"Displayed mind map for @{tag}."

    # No cached analysis — need to run one
    try:
        from bute.ai import is_llm_available, llm_send
        from bute.ai.prompts import analyze_prompt
        from bute.storage import query_and_load

        if not is_llm_available(config):
            return f"No analysis cached for @{tag} and AI is not configured."

        entries = query_and_load(config, tag=tag)
        if not entries:
            return f"No entries found with @{tag}."

        from bute.ai.prompts import format_entries

        prompt = analyze_prompt()
        context = format_entries(entries)
        response = llm_send(prompt, context, config)

        # Cache the result
        from bute.db import set_tag_stage

        set_tag_stage(tag, "analyzed", analysis=response, config=config)

        display_analyze_map(tag, response)
        return f"Displayed mind map for @{tag}."
    except Exception as e:
        return f"Could not display map for @{tag}: {e}"


_TOOL_HANDLERS = {
    "query_entries": _handle_query_entries,
    "search_text": _handle_search_text,
    "search_similar": _handle_search_similar,
    "create_entry": _handle_create_entry,
    "add_tag": _handle_add_tag,
    "remove_tag": _handle_remove_tag,
    "mark_done": _handle_mark_done,
    "mark_dropped": _handle_mark_dropped,
    "toggle_important": _handle_toggle_important,
    "update_due": _handle_update_due,
    "display_map": _handle_display_map,
}
