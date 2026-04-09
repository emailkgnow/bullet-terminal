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
