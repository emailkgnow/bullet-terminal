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
