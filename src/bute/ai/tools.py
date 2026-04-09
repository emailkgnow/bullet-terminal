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
