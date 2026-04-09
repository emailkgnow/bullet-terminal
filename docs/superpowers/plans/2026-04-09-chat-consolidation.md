# AI Chat Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate all AI features into `bt chat` as a single agentic interface with tool calling — the AI can read and write bt data, every write confirms.

**Architecture:** Rewrite `commands/chat.py` around OpenAI tool calling. Define tools in a new `ai/tools.py` module. Remove standalone AI commands (`recap`, `nudges`, `topic`, `analyze`, `autotag`, `map`). Update `ai/llm.py` to handle tool calls in streaming. Update CLI registrations and help text.

**Tech Stack:** Python, Click, OpenAI SDK (tool calling), Rich (display), SQLite (queries)

---

### Task 1: Create `ai/tools.py` — Tool Schema Definitions

**Files:**
- Create: `src/bute/ai/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write tests for tool schema structure**

```python
# tests/test_tools.py
"""Tests for AI tool definitions."""

from bute.ai.tools import TOOL_SCHEMAS, get_tool_schemas


def test_tool_schemas_is_list():
    assert isinstance(TOOL_SCHEMAS, list)


def test_all_schemas_have_required_fields():
    for schema in TOOL_SCHEMAS:
        assert schema["type"] == "function"
        fn = schema["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn


def test_read_tools_present():
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert "query_entries" in names
    assert "search_text" in names


def test_write_tools_present():
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert "create_entry" in names
    assert "add_tag" in names
    assert "remove_tag" in names
    assert "mark_done" in names
    assert "mark_dropped" in names
    assert "toggle_important" in names
    assert "update_due" in names


def test_display_tools_present():
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert "display_map" in names


def test_get_tool_schemas_excludes_search_similar_when_unavailable():
    schemas = get_tool_schemas(embeddings_available=False)
    names = {s["function"]["name"] for s in schemas}
    assert "search_similar" not in names


def test_get_tool_schemas_includes_search_similar_when_available():
    schemas = get_tool_schemas(embeddings_available=True)
    names = {s["function"]["name"] for s in schemas}
    assert "search_similar" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bute.ai.tools'`

- [ ] **Step 3: Implement tool schemas**

```python
# src/bute/ai/tools.py
"""AI tool definitions for bt chat — schemas and execution."""

from __future__ import annotations

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "query_entries",
            "description": (
                "Query bt entries by type, date range, tags, status, etc. "
                "All parameters are optional — combine as needed. "
                "Returns formatted entry list."
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
                        "description": "ISO date (YYYY-MM-DD). Return entries created on or after this date.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD). Return entries created on or before this date.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Include entries with ALL of these tags (AND logic).",
                    },
                    "exclude_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exclude entries with any of these tags.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["active", "done", "dropped"],
                        "description": "Filter tasks by status. Only applies to tasks.",
                    },
                    "important": {
                        "type": "boolean",
                        "description": "If true, only important entries.",
                    },
                    "has_due": {
                        "type": "boolean",
                        "description": "If true, only entries with a due date.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries to return. Default 50.",
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_text",
            "description": "Full-text search across entry bodies. Use for keyword lookups.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (keywords).",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["task", "note", "journal", "calendar"],
                        "description": "Optional type filter.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results. Default 20.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_similar",
            "description": "Semantic similarity search. Finds entries conceptually related to the query, even without keyword matches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query to find similar entries.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results. Default 10.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_entry",
            "description": "Create a new bt entry (task, note, journal, or calendar event).",
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
                        "description": "Tags without @ prefix.",
                    },
                    "due": {
                        "type": "string",
                        "description": "Due date (YYYY-MM-DD).",
                    },
                    "date": {
                        "type": "string",
                        "description": "Scheduled date (YYYY-MM-DD).",
                    },
                    "time": {
                        "type": "string",
                        "description": "Scheduled time (HH:MM, 24h).",
                    },
                    "important": {
                        "type": "boolean",
                        "description": "Mark as important.",
                    },
                },
                "required": ["signifier", "body"],
                "additionalProperties": False,
            },
        },
    },
    {
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
                        "description": "Entry ULIDs to tag.",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Tag name without @ prefix.",
                    },
                },
                "required": ["entry_ids", "tag"],
                "additionalProperties": False,
            },
        },
    },
    {
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
                        "description": "Entry ULIDs.",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Tag name without @ prefix.",
                    },
                },
                "required": ["entry_ids", "tag"],
                "additionalProperties": False,
            },
        },
    },
    {
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
                        "description": "Task ULIDs to mark done.",
                    },
                },
                "required": ["entry_ids"],
                "additionalProperties": False,
            },
        },
    },
    {
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
                        "description": "Task ULIDs to drop.",
                    },
                },
                "required": ["entry_ids"],
                "additionalProperties": False,
            },
        },
    },
    {
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
                        "description": "Entry ULIDs.",
                    },
                },
                "required": ["entry_ids"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_due",
            "description": "Set or update the due date on one or more entries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entry_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entry ULIDs.",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "New due date (YYYY-MM-DD).",
                    },
                },
                "required": ["entry_ids", "due_date"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "display_map",
            "description": "Render a mind map visualization of entries or a tag. Use when the user asks to 'map' something.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Tag to map. Will use cached analysis or run analysis on entries with this tag.",
                    },
                },
                "required": ["tag"],
                "additionalProperties": False,
            },
        },
    },
]

# search_similar is conditional — only include when embeddings are available
_CONDITIONAL_TOOL_NAMES = {"search_similar"}


def get_tool_schemas(embeddings_available: bool = False) -> list[dict]:
    """Return tool schemas, excluding conditional tools when unavailable."""
    if embeddings_available:
        return list(TOOL_SCHEMAS)
    return [s for s in TOOL_SCHEMAS if s["function"]["name"] not in _CONDITIONAL_TOOL_NAMES]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/ai/tools.py tests/test_tools.py
git commit -m "feat: add AI tool schema definitions for chat consolidation"
```

---

### Task 2: Add Tool Execution Layer to `ai/tools.py`

**Files:**
- Modify: `src/bute/ai/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write tests for tool execution — read tools**

Add to `tests/test_tools.py`:

```python
from unittest.mock import patch
from bute.models import Entry, EntryType
from bute.storage import save_entry


def test_execute_query_entries(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "fix bug", tags=["backend"])
    e2 = Entry.create(EntryType.NOTE, "meeting notes")
    save_entry(e1)
    save_entry(e2)

    result = execute_tool("query_entries", {"type": "task"}, config=None)
    assert "fix bug" in result
    assert "meeting notes" not in result


def test_execute_query_entries_with_tags(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "tagged task", tags=["work"])
    e2 = Entry.create(EntryType.TASK, "untagged task")
    save_entry(e1)
    save_entry(e2)

    result = execute_tool("query_entries", {"tags": ["work"]}, config=None)
    assert "tagged task" in result
    assert "untagged task" not in result


def test_execute_query_entries_with_date_range(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "today task")
    save_entry(e1)

    from datetime import date
    today = date.today().isoformat()
    result = execute_tool("query_entries", {"date_from": today, "date_to": today}, config=None)
    assert "today task" in result


def test_execute_search_text(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "fix authentication bug")
    e2 = Entry.create(EntryType.NOTE, "grocery list")
    save_entry(e1)
    save_entry(e2)

    result = execute_tool("search_text", {"query": "authentication"}, config=None)
    assert "authentication" in result


def test_execute_unknown_tool():
    from bute.ai.tools import execute_tool

    result = execute_tool("nonexistent_tool", {}, config=None)
    assert "Unknown tool" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py::test_execute_query_entries -v`
Expected: FAIL — `ImportError: cannot import name 'execute_tool'`

- [ ] **Step 3: Implement read tool execution**

Add to `src/bute/ai/tools.py`:

```python
def execute_tool(name: str, arguments: dict, config=None) -> str:
    """Execute a tool call and return the result as a string for the LLM."""
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return f"Unknown tool: {name}"
    return handler(arguments, config)


def _handle_query_entries(args: dict, config) -> str:
    from bute.ai.prompts import format_entries
    from bute.storage import query_and_load

    kwargs = {}
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

    # Handle tags — first tag goes to tag=, rest filtered in Python
    tags = args.get("tags", [])
    exclude_tags = args.get("exclude_tags", [])
    if tags:
        kwargs["tag"] = tags[0]

    limit = args.get("limit", 50)
    entries = query_and_load(config, **kwargs)

    # Apply remaining tag filters
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


_TOOL_HANDLERS = {
    "query_entries": _handle_query_entries,
    "search_text": _handle_search_text,
    "search_similar": _handle_search_similar,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/ai/tools.py tests/test_tools.py
git commit -m "feat: add read tool execution (query, search, similar)"
```

---

### Task 3: Add Write Tool Execution & Confirmation UX to `ai/tools.py`

**Files:**
- Modify: `src/bute/ai/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write tests for write tool execution**

Add to `tests/test_tools.py`:

```python
def test_execute_create_entry(tmp_data):
    from bute.ai.tools import execute_tool

    with patch("click.confirm", return_value=True):
        result = execute_tool(
            "create_entry",
            {"signifier": ".", "body": "new task from AI", "tags": ["work"]},
            config=None,
        )
    assert "Created" in result

    from bute.storage import query_and_load
    tasks = query_and_load(None, type="task")
    assert any(e.body == "new task from AI" for e in tasks)


def test_execute_create_entry_denied(tmp_data):
    from bute.ai.tools import execute_tool

    with patch("click.confirm", return_value=False):
        result = execute_tool(
            "create_entry",
            {"signifier": ".", "body": "denied task"},
            config=None,
        )
    assert "denied" in result.lower() or "cancelled" in result.lower()


def test_execute_add_tag(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "taggable task")
    save_entry(e1)

    with patch("click.confirm", return_value=True):
        result = execute_tool("add_tag", {"entry_ids": [e1.id], "tag": "backend"}, config=None)
    assert "Applied" in result or "added" in result.lower()

    from bute.storage import entry_path_from_id, load_entry
    loaded = load_entry(entry_path_from_id(e1.id))
    assert "backend" in loaded.tags


def test_execute_mark_done(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "task to complete")
    save_entry(e1)

    with patch("click.confirm", return_value=True):
        result = execute_tool("mark_done", {"entry_ids": [e1.id]}, config=None)
    assert "Applied" in result or "done" in result.lower()

    from bute.storage import entry_path_from_id, load_entry
    loaded = load_entry(entry_path_from_id(e1.id))
    assert loaded.status.value == "done"


def test_execute_toggle_important(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "normal task")
    save_entry(e1)

    with patch("click.confirm", return_value=True):
        result = execute_tool("toggle_important", {"entry_ids": [e1.id]}, config=None)

    from bute.storage import entry_path_from_id, load_entry
    loaded = load_entry(entry_path_from_id(e1.id))
    assert loaded.important is True


def test_execute_update_due(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "task needs due date")
    save_entry(e1)

    with patch("click.confirm", return_value=True):
        result = execute_tool("update_due", {"entry_ids": [e1.id], "due_date": "2026-04-15"}, config=None)

    from bute.storage import entry_path_from_id, load_entry
    loaded = load_entry(entry_path_from_id(e1.id))
    assert str(loaded.due) == "2026-04-15"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py::test_execute_create_entry -v`
Expected: FAIL — `create_entry` not in `_TOOL_HANDLERS`

- [ ] **Step 3: Implement write tool handlers with confirmation**

Add to `src/bute/ai/tools.py`:

```python
import click
from rich.console import Console

_console = Console()


def _confirm_action(description: str) -> bool:
    """Show confirmation prompt for AI-initiated write action."""
    _console.print(f"\n  [bold]AI wants to:[/bold] {description}")
    return click.confirm("  Apply?", default=True)


def _confirm_batch(description: str, entry_summaries: list[str]) -> list[int] | None:
    """Show confirmation for batch action. Returns selected indices or None if denied.

    Returns list of 0-based indices if approved (all or picked), None if denied.
    """
    _console.print(f"\n  [bold]AI wants to:[/bold] {description}")
    for i, summary in enumerate(entry_summaries, 1):
        _console.print(f"    {i}. {summary}")

    if len(entry_summaries) == 1:
        if click.confirm("  Apply?", default=True):
            return [0]
        return None

    choice = click.prompt(
        "  Apply?",
        type=click.Choice(["y", "n", "p"], case_sensitive=False),
        prompt_suffix=" [y]es [n]o [p]ick > ",
        default="y",
        show_choices=False,
    )
    if choice == "n":
        return None
    if choice == "y":
        return list(range(len(entry_summaries)))

    # Pick mode — ask for numbers
    picks = click.prompt("  Numbers to apply (space-separated)", default="").strip()
    if not picks:
        return None
    indices = []
    for tok in picks.split():
        if tok.isdigit():
            idx = int(tok) - 1
            if 0 <= idx < len(entry_summaries):
                indices.append(idx)
    return indices if indices else None


def _load_entries_by_ids(entry_ids: list[str], config) -> list:
    """Load Entry objects from ULIDs."""
    from bute.storage import entry_path_from_id, load_entry

    entries = []
    for eid in entry_ids:
        path = entry_path_from_id(eid, config)
        if path:
            entries.append(load_entry(path))
    return entries


def _entry_summary(entry) -> str:
    """One-line summary of an entry for confirmation display."""
    type_icons = {"task": ".", "note": "-", "journal": "=", "calendar": "o"}
    icon = type_icons.get(entry.type.value, "?")
    bang = "!" if entry.important else ""
    return f"{bang}{icon} {entry.body}"


def _handle_create_entry(args: dict, config) -> str:
    from bute.ai import embed_entry
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    sig_map = {".": EntryType.TASK, "-": EntryType.NOTE, "=": EntryType.JOURNAL, "o": EntryType.CALENDAR}
    entry_type = sig_map.get(args["signifier"])
    if entry_type is None:
        return f"Invalid signifier: {args['signifier']}"

    body = args["body"]
    tags = args.get("tags", [])
    summary_parts = [f"{args['signifier']} {body}"]
    if tags:
        summary_parts.append(" ".join(f"@{t}" for t in tags))
    if args.get("due"):
        summary_parts.append(f"due:{args['due']}")

    description = " ".join(summary_parts)
    _console.print(f"\n  [bold]AI wants to create:[/bold]")
    _console.print(f"    {description}")
    if not click.confirm("  Create?", default=True):
        return "User cancelled creation."

    kwargs = {"entry_type": entry_type, "body": body, "tags": list(tags)}
    if args.get("important"):
        kwargs["important"] = True
    if args.get("due"):
        from datetime import date as dt_date
        try:
            kwargs["due"] = dt_date.fromisoformat(args["due"])
        except ValueError:
            pass
    if args.get("date"):
        from datetime import date as dt_date
        try:
            kwargs["scheduled_date"] = dt_date.fromisoformat(args["date"])
        except ValueError:
            pass
    if args.get("time"):
        kwargs["scheduled_time"] = args["time"]

    entry = Entry.create(**kwargs)
    save_entry(entry, config)
    embed_entry(entry.id, entry.body, config)
    return f"Created: {args['signifier']} {body}"


def _handle_add_tag(args: dict, config) -> str:
    from bute.commands.action import handle_add_tag
    entries = _load_entries_by_ids(args["entry_ids"], config)
    if not entries:
        return "No entries found for the given IDs."

    tag = args["tag"]
    summaries = [_entry_summary(e) for e in entries]
    selected = _confirm_batch(f"add @{tag} to {len(entries)} {'entry' if len(entries) == 1 else 'entries'}", summaries)
    if selected is None:
        return "User cancelled."

    count = 0
    for i in selected:
        handle_add_tag(entries[i], tag, config)
        count += 1
    return f"Applied: added @{tag} to {count} {'entry' if count == 1 else 'entries'}."


def _handle_remove_tag(args: dict, config) -> str:
    from bute.commands.action import handle_remove_tag
    entries = _load_entries_by_ids(args["entry_ids"], config)
    if not entries:
        return "No entries found for the given IDs."

    tag = args["tag"]
    summaries = [_entry_summary(e) for e in entries]
    selected = _confirm_batch(f"remove @{tag} from {len(entries)} {'entry' if len(entries) == 1 else 'entries'}", summaries)
    if selected is None:
        return "User cancelled."

    count = 0
    for i in selected:
        handle_remove_tag(entries[i], tag, config)
        count += 1
    return f"Applied: removed @{tag} from {count} {'entry' if count == 1 else 'entries'}."


def _handle_mark_done(args: dict, config) -> str:
    from bute.commands.action import ACTION_HANDLERS
    entries = _load_entries_by_ids(args["entry_ids"], config)
    if not entries:
        return "No entries found for the given IDs."

    summaries = [_entry_summary(e) for e in entries]
    selected = _confirm_batch(f"mark {len(entries)} {'entry' if len(entries) == 1 else 'entries'} done", summaries)
    if selected is None:
        return "User cancelled."

    handler = ACTION_HANDLERS["done"]
    count = 0
    for i in selected:
        handler(entries[i], [], config)
        count += 1
    return f"Applied: marked {count} {'entry' if count == 1 else 'entries'} done."


def _handle_mark_dropped(args: dict, config) -> str:
    from bute.commands.action import ACTION_HANDLERS
    entries = _load_entries_by_ids(args["entry_ids"], config)
    if not entries:
        return "No entries found for the given IDs."

    summaries = [_entry_summary(e) for e in entries]
    selected = _confirm_batch(f"drop {len(entries)} {'entry' if len(entries) == 1 else 'entries'}", summaries)
    if selected is None:
        return "User cancelled."

    handler = ACTION_HANDLERS["drop"]
    count = 0
    for i in selected:
        handler(entries[i], [], config)
        count += 1
    return f"Applied: dropped {count} {'entry' if count == 1 else 'entries'}."


def _handle_toggle_important(args: dict, config) -> str:
    from bute.commands.action import ACTION_HANDLERS
    entries = _load_entries_by_ids(args["entry_ids"], config)
    if not entries:
        return "No entries found for the given IDs."

    summaries = [_entry_summary(e) for e in entries]
    selected = _confirm_batch(f"toggle important on {len(entries)} {'entry' if len(entries) == 1 else 'entries'}", summaries)
    if selected is None:
        return "User cancelled."

    handler = ACTION_HANDLERS["!"]
    count = 0
    for i in selected:
        handler(entries[i], [], config)
        count += 1
    return f"Applied: toggled important on {count} {'entry' if count == 1 else 'entries'}."


def _handle_update_due(args: dict, config) -> str:
    from datetime import date as dt_date
    from bute.storage import update_entry
    entries = _load_entries_by_ids(args["entry_ids"], config)
    if not entries:
        return "No entries found for the given IDs."

    due_date = args["due_date"]
    try:
        parsed_due = dt_date.fromisoformat(due_date)
    except ValueError:
        return f"Invalid date format: {due_date}. Use YYYY-MM-DD."

    summaries = [_entry_summary(e) for e in entries]
    selected = _confirm_batch(f"set due date to {due_date} on {len(entries)} {'entry' if len(entries) == 1 else 'entries'}", summaries)
    if selected is None:
        return "User cancelled."

    count = 0
    for i in selected:
        entries[i].due = parsed_due
        update_entry(entries[i], config)
        count += 1
    return f"Applied: set due {due_date} on {count} {'entry' if count == 1 else 'entries'}."


def _handle_display_map(args: dict, config) -> str:
    from bute.ai import is_llm_available, llm_send
    from bute.ai.prompts import analyze_prompt, format_entries
    from bute.db import get_tag_stage
    from bute.display import display_analyze_map
    from bute.storage import query_and_load

    tag = args["tag"]

    # Check for existing analysis
    stage_row = get_tag_stage(tag, config=config)
    analysis = stage_row["analysis"] if stage_row else None

    if analysis:
        display_analyze_map(tag, analysis)
        return f"Displayed mind map for @{tag}."

    # No cached analysis — run one
    entries = query_and_load(config, tag=tag)
    if not entries:
        return f"No entries found with @{tag}."

    if not is_llm_available(config):
        return "LLM not available to generate analysis."

    formatted = format_entries(entries)
    response = llm_send(analyze_prompt(), f'Tag: "@{tag}"\n\nEntries:\n{formatted}', config)
    display_analyze_map(tag, response)
    return f"Displayed mind map for @{tag} ({len(entries)} entries analyzed)."
```

Update `_TOOL_HANDLERS` to include all handlers:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/ai/tools.py tests/test_tools.py
git commit -m "feat: add write tool execution with confirmation UX"
```

---

### Task 4: Update `ai/llm.py` — Tool Calling Support in Streaming

**Files:**
- Modify: `src/bute/ai/llm.py:127-147`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write test for stream_chat_with_tools**

Add to `tests/test_tools.py`:

```python
def test_stream_chat_with_tools_yields_content(tmp_data):
    """Test that stream_chat_with_tools yields content and tool calls."""
    from bute.ai.llm import stream_chat_with_tools

    # We can't easily test real streaming, but verify the function exists
    # and handles the tools parameter
    assert callable(stream_chat_with_tools)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py::test_stream_chat_with_tools_yields_content -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Add `stream_chat_with_tools` to `ai/llm.py`**

Add after the existing `stream_chat` function at line 147 in `src/bute/ai/llm.py`:

```python
def stream_chat_with_tools(messages: list[dict], tools: list[dict], config=None):
    """Stream a multi-turn chat completion with tool calling support.

    Yields dicts with either:
      {"type": "content", "content": "text chunk"}
      {"type": "tool_call", "id": "call_xxx", "name": "func", "arguments": "json_str"}
      {"type": "done"}

    On error, yields a single content chunk with the error message.
    """
    try:
        client = _get_client(config)
        model = _get_model(config)
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools if tools else None,
            stream=True,
        )

        # Accumulate tool call data across chunks
        tool_calls: dict[int, dict] = {}  # index -> {id, name, arguments}

        for chunk in stream:
            delta = chunk.choices[0].delta

            # Content chunks
            if delta.content:
                yield {"type": "content", "content": delta.content}

            # Tool call chunks — accumulate across deltas
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tool_calls[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        tool_calls[idx]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_calls[idx]["arguments"] += tc.function.arguments

            # Check for finish reason
            if chunk.choices[0].finish_reason == "tool_calls":
                for idx in sorted(tool_calls.keys()):
                    tc = tool_calls[idx]
                    yield {"type": "tool_call", "id": tc["id"], "name": tc["name"], "arguments": tc["arguments"]}
                tool_calls.clear()

        yield {"type": "done"}

    except Exception as e:
        logger.debug("LLM stream failed: %s", e, exc_info=True)
        yield {"type": "content", "content": "[AI unavailable]"}
        yield {"type": "done"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/ai/llm.py tests/test_tools.py
git commit -m "feat: add stream_chat_with_tools for tool calling in streaming"
```

---

### Task 5: Write New System Prompt

**Files:**
- Modify: `src/bute/ai/prompts.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write test for new system prompt**

Add to `tests/test_tools.py`:

```python
def test_chat_system_prompt_contains_key_elements():
    from bute.ai.prompts import chat_system_prompt

    prompt = chat_system_prompt()
    assert "thinking partner" in prompt.lower() or "life management" in prompt.lower()
    assert "task" in prompt and "note" in prompt and "journal" in prompt
    assert "confirmation" in prompt.lower() or "approval" in prompt.lower()
    assert "2026" in prompt  # should include today's date context
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py::test_chat_system_prompt_contains_key_elements -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Add `chat_system_prompt` to `ai/prompts.py`**

Add to `src/bute/ai/prompts.py` (keep existing `SYSTEM_BASE`, `format_entries`, `autotag_prompt`, `title_prompt` — these are reused):

```python
def chat_system_prompt() -> str:
    from datetime import date
    today = date.today()
    week_number = today.isocalendar()[1]

    return f"""{SYSTEM_BASE}

You are in an interactive chat session with full access to the user's bt entries through tool calls.

Today is {today.isoformat()} (week {week_number}).

Entry types and signifiers:
  . = task (action or intention) — statuses: active, done, dropped
  - = note (knowledge, idea, reference)
  = = journal (reflection, feeling)
  o = calendar (event, commitment)
  ! prefix = important

Tags: @tag syntax. System tags: @today, @thisweek, @goal, @habit.

You have tools to read entries (query_entries, search_text, search_similar) and write (create_entry, add_tag, remove_tag, mark_done, mark_dropped, toggle_important, update_due, display_map). Every write action requires user confirmation — you do not need to ask permission in your message, the system handles it.

Guidelines:
- When the user asks a question that needs entry data, call the appropriate tool first — don't guess
- Explain why before proposing write actions
- Don't over-fetch — pull the minimum context needed
- If the user scopes explicitly ("based on these entries only"), respect the boundary
- When asked to map something, use the display_map tool
- Be direct, concise, and insightful — focus on patterns, connections, and gaps the user might not see
- No markdown formatting (no bold, no headers). Use plain section titles and - bullet points"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/ai/prompts.py tests/test_tools.py
git commit -m "feat: add chat_system_prompt with tool calling context"
```

---

### Task 6: Rewrite `commands/chat.py` — New Chat Session

**Files:**
- Modify: `src/bute/commands/chat.py`
- Test: `tests/test_chat.py`

- [ ] **Step 1: Write tests for the new ChatSession**

Replace the entire `tests/test_chat.py` with:

```python
"""Tests for the new chat command module."""

import pytest
from unittest.mock import patch
from bute.models import Entry, EntryType
from bute.storage import save_entry


def test_chat_system_prompt_returns_string():
    from bute.ai.prompts import chat_system_prompt

    result = chat_system_prompt()
    assert isinstance(result, str)
    assert "task" in result


def test_chat_session_start_blank(tmp_data):
    from bute.commands.chat import ChatSession

    session = ChatSession.start(config={})

    assert session.context_entries == []
    assert len(session.messages) == 1  # system prompt only
    assert session.messages[0]["role"] == "system"
    assert session.last_bt_results == []


def test_chat_session_add_to_context(tmp_data):
    from bute.commands.chat import ChatSession

    session = ChatSession.start(config={})

    e1 = Entry.create(EntryType.NOTE, "note one")
    e2 = Entry.create(EntryType.NOTE, "note two")
    session.add_to_context([e1, e2])

    assert len(session.context_entries) == 2


def test_chat_session_add_to_context_no_duplicates(tmp_data):
    from bute.commands.chat import ChatSession

    session = ChatSession.start(config={})

    e1 = Entry.create(EntryType.TASK, "main task")
    session.add_to_context([e1])
    session.add_to_context([e1])

    assert len(session.context_entries) == 1


def test_chat_session_message_management(tmp_data):
    from bute.commands.chat import ChatSession

    session = ChatSession.start(config={})

    session.add_user_message("what should I do?")
    assert session.messages[-1] == {"role": "user", "content": "what should I do?"}

    session.add_assistant_message("Here's what I think...")
    assert session.messages[-1] == {"role": "assistant", "content": "Here's what I think..."}


def test_execute_bt_view_tasks(tmp_data):
    from bute.commands.chat import execute_bt_view

    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.NOTE, "note one")
    save_entry(e1)
    save_entry(e2)

    results = execute_bt_view(["t"], config=None)
    assert len(results) == 1
    assert results[0].body == "task one"


def test_execute_bt_view_tag_filter(tmp_data):
    from bute.commands.chat import execute_bt_view

    e1 = Entry.create(EntryType.TASK, "tagged", tags=["work"])
    e2 = Entry.create(EntryType.TASK, "untagged")
    save_entry(e1)
    save_entry(e2)

    results = execute_bt_view(["@work"], config=None)
    assert len(results) == 1
    assert results[0].body == "tagged"


def test_execute_bt_view_important(tmp_data):
    from bute.commands.chat import execute_bt_view

    e1 = Entry.create(EntryType.TASK, "normal task")
    e2 = Entry.create(EntryType.TASK, "urgent task", important=True)
    save_entry(e1)
    save_entry(e2)

    results = execute_bt_view(["!"], config=None)
    assert len(results) == 1
    assert results[0].important is True


def test_handle_slash_command_done(tmp_data):
    from bute.commands.chat import ChatSession, _handle_slash_command

    session = ChatSession.start(config={})
    assert _handle_slash_command(session, "/done") == "exit"


def test_handle_slash_command_bt(tmp_data):
    from bute.commands.chat import ChatSession, _handle_slash_command

    e1 = Entry.create(EntryType.TASK, "task one")
    save_entry(e1)

    session = ChatSession.start(config=None)
    _handle_slash_command(session, "/bt t")
    assert len(session.last_bt_results) >= 1


def test_handle_number_action_in_chat(tmp_data):
    from bute.commands.chat import ChatSession, _handle_number_action

    e1 = Entry.create(EntryType.TASK, "task to complete")
    save_entry(e1)

    session = ChatSession.start(config=None)
    session.last_bt_results = [e1]

    _handle_number_action(session, ["1", "done"])

    from bute.storage import entry_path_from_id, load_entry
    loaded = load_entry(entry_path_from_id(e1.id))
    assert loaded.status.value == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_chat.py -v`
Expected: FAIL — `ChatSession.start()` still requires entries parameter

- [ ] **Step 3: Rewrite `commands/chat.py`**

Replace the entire file `src/bute/commands/chat.py`:

```python
"""Interactive AI chat sessions with tool calling."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from bute.display import TYPE_STYLE

if TYPE_CHECKING:
    from bute.models import Entry

console = Console()


@dataclass
class ChatSession:
    """Holds state for an interactive chat session."""

    config: dict
    context_entries: list[Entry] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    last_bt_results: list[Entry] = field(default_factory=list)

    @classmethod
    def start(cls, config: dict) -> ChatSession:
        """Create a new blank chat session."""
        from bute.ai.prompts import chat_system_prompt

        session = cls(
            config=config,
            messages=[{"role": "system", "content": chat_system_prompt()}],
        )
        return session

    def add_to_context(self, entries: list[Entry]) -> None:
        """Add entries to the chat context (skips duplicates)."""
        from bute.ai.prompts import format_entries

        existing_ids = {e.id for e in self.context_entries}
        new_entries = [e for e in entries if e.id not in existing_ids]
        if not new_entries:
            return
        self.context_entries.extend(new_entries)
        self.messages.append({
            "role": "user",
            "content": f"[Added to context]\n{format_entries(new_entries)}",
        })

    def add_user_message(self, text: str) -> None:
        """Add a user message to the history."""
        self.messages.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str) -> None:
        """Add an assistant response to the history."""
        self.messages.append({"role": "assistant", "content": text})


def execute_bt_view(args: list[str], config) -> list:
    """Execute a bt view command within chat and return matching entries."""
    from bute.storage import query_and_load

    if not args:
        return []

    first = args[0]

    sig_to_query = {
        "t": {"type": "task", "status": "active"},
        "n": {"type": "note"},
        "j": {"type": "journal"},
        "c": {"type": "calendar"},
    }

    # Signifier views: t, n, j, c (with optional @tag)
    if first in sig_to_query:
        kwargs = dict(sig_to_query[first])
        for arg in args[1:]:
            if arg.startswith("@") and len(arg) > 1:
                kwargs["tag"] = arg[1:]
        return query_and_load(config, **kwargs)

    # Important + type: t!, n!, etc.
    stripped = first.rstrip("!")
    if first.endswith("!") and stripped in sig_to_query:
        kwargs = dict(sig_to_query[stripped])
        kwargs["important"] = True
        return query_and_load(config, **kwargs)

    # Tag filter: @tagname
    if first.startswith("@") and len(first) > 1:
        return query_and_load(config, tag=first[1:])

    # Important filter: !
    if first == "!":
        return query_and_load(config, important=True)

    return []


def display_bt_results(entries: list, context_ids: set[str]) -> None:
    """Display bt query results with in-context markers."""
    if not entries:
        console.print("  [dim]No entries found.[/dim]")
        return

    table = Table(
        show_header=False, box=None, pad_edge=False,
        padding=(0, 1), expand=True,
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("", width=2)
    table.add_column("", ratio=1, overflow="fold")
    table.add_column("", style="dim")

    for i, entry in enumerate(entries, 1):
        style = TYPE_STYLE[entry.type]
        icon = Text()
        if entry.important:
            icon.append("!", style="bold red")
        else:
            icon.append(" ")
        icon.append(style["icon"], style=style["color"])

        body = Text(entry.body.split("\n", 1)[0].strip())

        meta_parts = []
        if entry.id in context_ids:
            meta_parts.append("← in ctx")
        if entry.due:
            meta_parts.append(f"due:{entry.due}")
        if entry.tags:
            meta_parts.extend(f"@{t}" for t in entry.tags)

        table.add_row(str(i), icon, body, " ".join(meta_parts))

    console.print()
    console.print(table)


def start_chat_session(config) -> None:
    """Start an interactive AI chat session."""
    from bute.ai import _LLM_INSTALL_MSG, is_embedding_available, is_llm_available

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    session = ChatSession.start(config)
    embeddings = is_embedding_available()

    console.print("\n  [bold]bt chat[/bold] — AI session with tool access")
    console.print("  [dim]/bt <args> to pull entries, /done to exit[/dim]\n")

    # REPL loop
    _run_repl(session, embeddings)


def _run_repl(session: ChatSession, embeddings_available: bool) -> None:
    """Run the chat REPL with tool calling."""
    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            result = _handle_slash_command(session, user_input)
            if result == "exit":
                return
            continue

        # Number-action
        tokens = user_input.split()
        if tokens[0].isdigit():
            _handle_number_action(session, tokens)
            continue

        # Regular message → send to AI with tools
        session.add_user_message(user_input)
        _stream_with_tools(session, embeddings_available)


def _stream_with_tools(session: ChatSession, embeddings_available: bool) -> None:
    """Stream AI response, handling tool calls in a loop."""
    from rich.live import Live

    from bute.ai.llm import stream_chat_with_tools
    from bute.ai.tools import execute_tool, get_tool_schemas
    from bute.display import display_ai_response

    tools = get_tool_schemas(embeddings_available=embeddings_available)

    while True:
        content_parts = []
        tool_calls = []

        with Live(Text(""), refresh_per_second=10, console=console, transient=True) as live:
            for event in stream_chat_with_tools(session.messages, tools, session.config):
                if event["type"] == "content":
                    content_parts.append(event["content"])
                    live.update(Text("".join(content_parts)))
                elif event["type"] == "tool_call":
                    tool_calls.append(event)
                elif event["type"] == "done":
                    break

        content = "".join(content_parts)

        # If there are no tool calls, we're done — show the response
        if not tool_calls:
            if content.strip():
                session.add_assistant_message(content)
                display_ai_response(content)
            return

        # Record the assistant message with tool calls
        assistant_msg = {"role": "assistant"}
        if content:
            assistant_msg["content"] = content
        assistant_msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            }
            for tc in tool_calls
        ]
        session.messages.append(assistant_msg)

        # Show any content before tool calls
        if content.strip():
            display_ai_response(content)

        # Execute each tool call and add results
        for tc in tool_calls:
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(tc["name"], args, config=session.config)
            session.messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        # Loop back — the AI will process tool results and respond


def _handle_slash_command(session: ChatSession, command: str) -> str | None:
    """Handle a slash command. Returns 'exit' or None to continue."""
    parts = command.split(None, 1)
    cmd = parts[0].lower()
    args_str = parts[1] if len(parts) > 1 else ""

    if cmd == "/done":
        return "exit"

    if cmd == "/bt":
        bt_args = args_str.split() if args_str else []
        if not bt_args:
            console.print("  [dim]Usage: /bt t, /bt n, /bt @tag, /bt ![/dim]")
            return None
        entries = execute_bt_view(bt_args, session.config)
        if entries:
            session.last_bt_results = entries
            context_ids = {e.id for e in session.context_entries}
            display_bt_results(entries, context_ids)
            # Inject results into message history so the AI can see them
            from bute.ai.prompts import format_entries
            session.messages.append({
                "role": "user",
                "content": f"[/bt {args_str} — {len(entries)} entries]\n{format_entries(entries)}",
            })
        else:
            console.print("  [dim]No entries found.[/dim]")
        return None

    console.print(f"  [dim]Unknown command: {cmd}[/dim]")
    console.print("  [dim]Available: /bt <args>, /done[/dim]")
    return None


def _handle_number_action(session: ChatSession, tokens: list[str]) -> None:
    """Handle number-action commands in chat (e.g., '1 done', '2 3 @tag')."""
    numbers = []
    rest = list(tokens)
    while rest and rest[0].isdigit():
        numbers.append(int(rest.pop(0)))

    if not rest:
        console.print("  [dim]No action specified. Usage: 1 done, 2 3 @tag[/dim]")
        return

    action = rest[0]
    action_args = rest[1:]

    if not session.last_bt_results:
        console.print("  [dim]No entries to reference. Run /bt first.[/dim]")
        return

    # Resolve numbers to entries
    resolved = []
    for n in numbers:
        if n < 1 or n > len(session.last_bt_results):
            console.print(
                f"  [red]#{n} out of range (1-{len(session.last_bt_results)})[/red]"
            )
            return
        resolved.append(session.last_bt_results[n - 1])

    # Standard bt actions (done, drop, !, @tag, untag, later)
    from bute.commands.action import ACTION_HANDLERS, handle_add_tag, handle_remove_tag
    from bute.display import display_action_confirmation
    from bute.errors import DwnError

    # Handle @tag action
    if action.startswith("@") and len(action) > 1:
        tag = action[1:]
        for entry in resolved:
            handle_add_tag(entry, tag, session.config)
            display_action_confirmation(entry, f"@{tag}")
        return

    # Handle untag
    if action == "untag":
        if not action_args:
            console.print("  [dim]Usage: 1 untag @backend[/dim]")
            return
        tag = action_args[0].lstrip("@")
        for entry in resolved:
            handle_remove_tag(entry, tag, session.config)
            display_action_confirmation(entry, f"untag @{tag}")
        return

    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        console.print(f"  [dim]Unknown action: {action}[/dim]")
        return

    for entry in resolved:
        try:
            handler(entry, action_args, session.config)
            display_action_confirmation(entry, action)
        except DwnError as e:
            console.print(f"  [red]{e.format_message()}[/red]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_chat.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/chat.py tests/test_chat.py
git commit -m "feat: rewrite chat with tool calling, blank start, no exit flow"
```

---

### Task 7: Update CLI — Remove Commands and Update Help

**Files:**
- Modify: `src/bute/cli.py:537-589` (imports and registrations)
- Modify: `src/bute/cli.py:350-376` (help text)
- Delete: `src/bute/commands/nudges.py`
- Delete: `src/bute/commands/topic.py`

- [ ] **Step 1: Write test for CLI command availability**

Add to `tests/test_tools.py`:

```python
def test_removed_commands_not_registered():
    """Verify removed commands are no longer in the CLI."""
    from click.testing import CliRunner
    from bute.cli import main

    runner = CliRunner()

    # These should not be available
    for cmd in ["recap", "nudges", "topic", "analyze", "tag-notes", "map"]:
        result = runner.invoke(main, [cmd, "--help"])
        assert result.exit_code != 0 or "No such command" in result.output or "Error" in result.output, f"{cmd} should be removed"


def test_chat_command_still_registered():
    """Verify chat is still available."""
    from click.testing import CliRunner
    from bute.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--help"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py::test_removed_commands_not_registered -v`
Expected: FAIL — commands are still registered

- [ ] **Step 3: Update CLI imports and registrations**

In `src/bute/cli.py`, remove these import lines (around lines 537-551):

Remove from the rituals import:
```python
# Change this line:
from bute.commands.rituals import dp_cmd, dump_cmd, monthly_cmd, recap_cmd, wp_cmd
# To this:
from bute.commands.rituals import dp_cmd, dump_cmd, monthly_cmd, wp_cmd
```

Remove these import lines entirely:
```python
from bute.commands.topic import topic_cmd  # noqa: E402
from bute.commands.nudges import nudges_cmd  # noqa: E402
from bute.commands.tags import analyze_tag_cmd, autotag_cmd, map_tag_cmd  # noqa: E402
```

Remove these `add_command` lines:
```python
main.add_command(recap_cmd)
main.add_command(topic_cmd)
main.add_command(nudges_cmd)
main.add_command(analyze_tag_cmd)
main.add_command(autotag_cmd)
main.add_command(map_tag_cmd)
```

- [ ] **Step 4: Update help text in `_print_help()`**

Replace the AI section (lines 350-376) in `src/bute/cli.py`:

```python
    # --- AI ---
    t = Table(title="AI — LLM features (bt init to configure)", title_style="bold cyan",
              box=None, pad_edge=False, padding=(0, 2), show_header=True, header_style="bold dim", expand=True)
    t.add_column("Command", style="bold", no_wrap=True)
    t.add_column("What it does")
    t.add_column("Example", style="dim")
    t.add_section()
    t.add_row("bt chat", "AI session — read & act on your entries", "bt chat")
    t.add_row("bt <n> title", "AI-generate a title for an entry", "bt 3 title")
    t.add_section()
    t.add_row("[dim]search (local, no API key)[/dim]", "", "")
    t.add_row("bt like <input>", "Find similar entries", "bt like 3, bt like productivity")
    console.print()
    console.print(t)
    console.print()
    console.print("    [dim]Chat commands:[/dim] /bt <view>  /done")
    console.print("    [dim]Chat can read, create, tag, and act on entries with your approval[/dim]")
    console.print()
```

- [ ] **Step 5: Update the chat command registration**

Find the existing chat command Click definition. It currently takes entry numbers as arguments for `bt <n> chat`. Update it to take no arguments — `bt chat` only. Find where the chat Click command is defined (likely in `cli.py` within the resolve_command method or as a standalone command) and update it.

In `src/bute/cli.py`, find the chat handling in `resolve_command()` and the chat Click command. The chat command registration needs to call `start_chat_session(config)` without entries.

Search for where `start_chat_session` is called and update the call to pass only `config`:

```python
# In the chat command handler, change:
start_chat_session(entries, config)
# To:
start_chat_session(config)
```

Also remove the `bt <n> chat` routing from `resolve_command()` if it's handled there.

- [ ] **Step 6: Delete removed command files**

```bash
rm src/bute/commands/nudges.py src/bute/commands/topic.py
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py::test_removed_commands_not_registered tests/test_tools.py::test_chat_command_still_registered -v`
Expected: All PASS

- [ ] **Step 8: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All PASS (or only unrelated failures)

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: remove standalone AI commands, update CLI help for chat-only AI"
```

---

### Task 8: Clean Up Removed Code — Prompts, Rituals, Tags

**Files:**
- Modify: `src/bute/ai/prompts.py` — remove `topic_prompt`, `nudges_prompt`, `analyze_prompt`, `chat_prompt`, `chat_summary_prompt`
- Modify: `src/bute/commands/rituals.py` — remove `recap_cmd`, `_recap_daily`, `_recap_period`
- Modify: `src/bute/commands/tags.py` — remove `analyze_tag_cmd`, `map_tag_cmd`, `autotag_cmd`

- [ ] **Step 1: Remove unused prompt functions**

In `src/bute/ai/prompts.py`, delete these functions:
- `topic_prompt()` (lines 22-51)
- `nudges_prompt()` (lines 54-73)
- `chat_prompt()` (lines 122-150)
- `chat_summary_prompt()` (lines 153-161)

Keep:
- `SYSTEM_BASE`
- `chat_system_prompt()` (added in Task 5)
- `analyze_prompt()` — still used by `_handle_display_map` in `ai/tools.py`
- `title_prompt()`
- `autotag_prompt()`
- `format_entries()`
- `_BT_FENCE`

- [ ] **Step 2: Remove recap from rituals.py**

In `src/bute/commands/rituals.py`, delete:
- `recap_cmd` (lines 385-391)
- `_recap_daily` (lines 394-423)
- `_recap_period` (lines 426-445)

- [ ] **Step 3: Remove analyze, map, autotag commands from tags.py**

In `src/bute/commands/tags.py`, delete:
- `analyze_tag_cmd` (lines 110-130)
- `map_tag_cmd` (lines 132-186)
- `autotag_cmd` (lines 188-280)

Keep:
- `_parse_tag_tokens()` — may be used elsewhere
- `_format_analysis_for_note()` — used by `_run_analyze()` which is used by `display_map` tool
- `_load_tagged_entries()`
- `_load_filtered_entries()`
- `_run_analyze()` — used by `display_map` tool handler

- [ ] **Step 4: Remove stale test references**

Check `tests/test_chat.py` for any references to removed functions (`chat_prompt`, `chat_summary_prompt`, `parse_proposals`, `create_proposals`, `_generate_summary`). These were already replaced in Task 6.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: remove unused prompt templates, recap, analyze/map/autotag commands"
```

---

### Task 9: Reinstall and Smoke Test

**Files:**
- No file changes — manual verification

- [ ] **Step 1: Reinstall bt globally**

```bash
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall
```

- [ ] **Step 2: Verify removed commands are gone**

```bash
bt recap week      # should error: "No such command"
bt nudges          # should error: "No such command"
bt topic test      # should error: "No such command"
bt analyze @test   # should error: "No such command"
bt tag-notes       # should error: "No such command"
bt map @test       # should error: "No such command"
```

- [ ] **Step 3: Verify chat starts blank**

```bash
bt chat            # should start a blank session
# Type: what tasks do I have?
# AI should call query_entries tool
# Type: /done to exit
```

- [ ] **Step 4: Verify /bt works in chat**

```bash
bt chat
# Type: /bt t
# Should show tasks
# Type: 1 done (if tasks exist)
# Should mark done
# Type: /done
```

- [ ] **Step 5: Verify help text is updated**

```bash
bt --help          # AI section should show only chat + title + like
```

- [ ] **Step 6: Run full test suite one final time**

```bash
uv run pytest -v
```

- [ ] **Step 7: Commit any fixes**

```bash
git add -A
git commit -m "fix: address smoke test issues"
```

---

### Task 10: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLI Grammar section**

In `CLAUDE.md`, replace the AI-related command examples. Remove references to `recap`, `nudges`, `topic`, `analyze`, `autotag`, `map` as standalone commands. Update the Chat section:

Replace:
```
**Chat sessions** — `bt <n> chat` starts an AI conversation anchored to an entry.
```

With:
```
**Chat sessions** — `bt chat` starts an AI conversation. The AI has tool access to query, create, tag, and act on entries — every write action requires confirmation. Use `/bt <args>` to explicitly pull entries, `/done` to exit.
```

Remove from Tag Processing section:
```
bute analyze @home-reno
bute analyze @bt @ai -@done
bute map @backend
```

Remove from Rituals:
```
bute recap week
```

- [ ] **Step 2: Update Key Modules table**

Remove `ai/prompts.py` entry mentioning topic/nudges/analyze prompts. Update to mention `ai/tools.py`:

Add row:
```
| `ai/tools.py` | Tool schemas + execution for chat (query, create, tag, action, map) |
```

- [ ] **Step 3: Update Design Decisions**

Add or update the AI design decision:
```
- **AI is chat-only** — all AI features consolidated into `bt chat`. No standalone AI commands. Chat has tool calling: AI can query entries, create, tag, and modify with user confirmation. Standalone commands (`recap`, `nudges`, `topic`, `analyze`, `autotag`, `map`) removed — their capabilities are subsumed by natural conversation.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for AI chat consolidation"
```
