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


# ---------------------------------------------------------------------------
# Tool execution tests (Task 2)
# ---------------------------------------------------------------------------


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

    # Use UTC date to match SQLite's date() which normalises to UTC
    from datetime import datetime, timezone
    utc_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = execute_tool("query_entries", {"date_from": utc_today, "date_to": utc_today}, config=None)
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


# ---------------------------------------------------------------------------
# Write tool execution tests (Task 3)
# ---------------------------------------------------------------------------


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


def test_execute_create_entry_with_metadata(tmp_data):
    from bute.ai.tools import execute_tool

    with patch("click.confirm", return_value=True):
        result = execute_tool(
            "create_entry",
            {
                "signifier": ".",
                "body": "task with due date",
                "due": "2026-04-15",
                "important": True,
            },
            config=None,
        )
    assert "Created" in result
    from bute.storage import query_and_load

    tasks = query_and_load(None, type="task")
    matched = [e for e in tasks if e.body == "task with due date"]
    assert len(matched) == 1
    assert str(matched[0].due) == "2026-04-15"
    assert matched[0].important is True


def test_execute_create_note(tmp_data):
    from bute.ai.tools import execute_tool

    with patch("click.confirm", return_value=True):
        result = execute_tool(
            "create_entry",
            {"signifier": "-", "body": "a new note"},
            config=None,
        )
    assert "Created" in result
    from bute.storage import query_and_load

    notes = query_and_load(None, type="note")
    assert any(e.body == "a new note" for e in notes)


def test_execute_add_tag(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "taggable task")
    save_entry(e1)
    with patch("click.confirm", return_value=True):
        result = execute_tool(
            "add_tag", {"entry_ids": [e1.id], "tag": "backend"}, config=None
        )
    assert "Applied" in result or "added" in result.lower()
    from bute.storage import entry_path_from_id, load_entry

    loaded = load_entry(entry_path_from_id(e1.id))
    assert "backend" in loaded.tags


def test_execute_add_tag_denied(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "taggable task")
    save_entry(e1)
    with patch("click.confirm", return_value=False):
        result = execute_tool(
            "add_tag", {"entry_ids": [e1.id], "tag": "backend"}, config=None
        )
    assert "cancelled" in result.lower() or "denied" in result.lower()
    from bute.storage import entry_path_from_id, load_entry

    loaded = load_entry(entry_path_from_id(e1.id))
    assert "backend" not in loaded.tags


def test_execute_remove_tag(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "tagged task", tags=["backend"])
    save_entry(e1)
    with patch("click.confirm", return_value=True):
        result = execute_tool(
            "remove_tag", {"entry_ids": [e1.id], "tag": "backend"}, config=None
        )
    assert "Applied" in result or "removed" in result.lower()
    from bute.storage import entry_path_from_id, load_entry

    loaded = load_entry(entry_path_from_id(e1.id))
    assert "backend" not in loaded.tags


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


def test_execute_mark_dropped(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "task to drop")
    save_entry(e1)
    with patch("click.confirm", return_value=True):
        result = execute_tool("mark_dropped", {"entry_ids": [e1.id]}, config=None)
    assert "Applied" in result or "dropped" in result.lower()
    from bute.storage import entry_path_from_id, load_entry

    loaded = load_entry(entry_path_from_id(e1.id))
    assert loaded.status.value == "dropped"


def test_execute_toggle_important(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "normal task")
    save_entry(e1)
    with patch("click.confirm", return_value=True):
        result = execute_tool(
            "toggle_important", {"entry_ids": [e1.id]}, config=None
        )
    from bute.storage import entry_path_from_id, load_entry

    loaded = load_entry(entry_path_from_id(e1.id))
    assert loaded.important is True


def test_execute_update_due(tmp_data):
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "task needs due date")
    save_entry(e1)
    with patch("click.confirm", return_value=True):
        result = execute_tool(
            "update_due",
            {"entry_ids": [e1.id], "due_date": "2026-04-15"},
            config=None,
        )
    from bute.storage import entry_path_from_id, load_entry

    loaded = load_entry(entry_path_from_id(e1.id))
    assert str(loaded.due) == "2026-04-15"


def test_execute_mark_done_multiple(tmp_data):
    """Batch action on multiple entries."""
    from bute.ai.tools import execute_tool

    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.TASK, "task two")
    save_entry(e1)
    save_entry(e2)
    with patch("click.prompt", return_value="y"):
        result = execute_tool(
            "mark_done", {"entry_ids": [e1.id, e2.id]}, config=None
        )
    from bute.storage import entry_path_from_id, load_entry

    assert load_entry(entry_path_from_id(e1.id)).status.value == "done"
    assert load_entry(entry_path_from_id(e2.id)).status.value == "done"


def test_execute_entry_not_found(tmp_data):
    """Action on a nonexistent entry returns error."""
    from bute.ai.tools import execute_tool

    with patch("click.confirm", return_value=True):
        result = execute_tool(
            "mark_done", {"entry_ids": ["00000000000000000000000000"]}, config=None
        )
    assert "not found" in result.lower() or "error" in result.lower()


def test_handler_dict_completeness():
    """All tool schemas have a registered handler."""
    from bute.ai.tools import TOOL_SCHEMAS, _TOOL_HANDLERS

    schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    handler_names = set(_TOOL_HANDLERS.keys())
    assert schema_names == handler_names, (
        f"Missing handlers: {schema_names - handler_names}, "
        f"Extra handlers: {handler_names - schema_names}"
    )
