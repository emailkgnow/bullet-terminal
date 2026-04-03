"""Tests for the chat command module."""

import pytest
from bute.models import Entry, EntryType
from bute.storage import save_entry


def test_chat_prompt_returns_string():
    from bute.ai.prompts import chat_prompt

    result = chat_prompt()
    assert isinstance(result, str)
    assert "bt" in result.lower()
    assert "```bt" in result


def test_chat_summary_prompt_returns_string():
    from bute.ai.prompts import chat_summary_prompt

    result = chat_summary_prompt()
    assert isinstance(result, str)
    assert "summary" in result.lower() or "summarize" in result.lower()


def test_chat_session_start(tmp_data):
    from bute.commands.chat import ChatSession

    entry = Entry.create(EntryType.TASK, "renovate kitchen", tags=["home-reno"])
    session = ChatSession.start(entry, config={})

    assert session.anchor is entry
    assert len(session.context_entries) == 1
    assert session.context_entries[0] is entry
    assert len(session.messages) == 2  # system + initial user
    assert session.messages[0]["role"] == "system"
    assert session.messages[1]["role"] == "user"
    assert "renovate kitchen" in session.messages[1]["content"]
    assert session.proposals == []
    assert session.last_bt_results == []


def test_chat_session_add_to_context(tmp_data):
    from bute.commands.chat import ChatSession

    anchor = Entry.create(EntryType.TASK, "main task")
    session = ChatSession.start(anchor, config={})

    e1 = Entry.create(EntryType.NOTE, "note one")
    e2 = Entry.create(EntryType.NOTE, "note two")
    session.add_to_context([e1, e2])

    assert len(session.context_entries) == 3
    assert session.context_entries[1] is e1
    assert session.context_entries[2] is e2
    assert session.messages[-1]["role"] == "user"
    assert "Added to context" in session.messages[-1]["content"]
    assert "note one" in session.messages[-1]["content"]


def test_chat_session_add_to_context_no_duplicates(tmp_data):
    from bute.commands.chat import ChatSession

    anchor = Entry.create(EntryType.TASK, "main task")
    session = ChatSession.start(anchor, config={})

    before_count = len(session.messages)
    session.add_to_context([anchor])

    assert len(session.context_entries) == 1
    assert len(session.messages) == before_count


def test_chat_session_message_management(tmp_data):
    from bute.commands.chat import ChatSession

    anchor = Entry.create(EntryType.TASK, "test")
    session = ChatSession.start(anchor, config={})

    session.add_user_message("what should I do?")
    assert session.messages[-1] == {"role": "user", "content": "what should I do?"}

    session.add_assistant_message("Here's what I think...")
    assert session.messages[-1] == {"role": "assistant", "content": "Here's what I think..."}


def test_parse_proposals_extracts_bt_blocks():
    from bute.commands.chat import parse_proposals

    response = (
        "Here's what I'd suggest:\n\n"
        "```bt\n"
        ". finalize tile selection due:apr05 @home-reno\n"
        "- contractor notes for reference\n"
        "o tile samples arriving d:0404 t:1000\n"
        "```\n\n"
        "Let me know if that works."
    )
    proposals = parse_proposals(response)
    assert len(proposals) == 3

    assert proposals[0]["type"] == "task"
    assert proposals[0]["body"] == "finalize tile selection"
    assert proposals[0]["tags"] == ["home-reno"]
    assert proposals[0]["metadata"] == {"due": "apr05"}

    assert proposals[1]["type"] == "note"
    assert proposals[1]["body"] == "contractor notes for reference"

    assert proposals[2]["type"] == "calendar"
    assert proposals[2]["body"] == "tile samples arriving"
    assert proposals[2]["metadata"] == {"d": "0404", "t": "1000"}


def test_parse_proposals_handles_important():
    from bute.commands.chat import parse_proposals

    response = "```bt\n.! urgent fix @backend\n```"
    proposals = parse_proposals(response)
    assert len(proposals) == 1
    assert proposals[0]["important"] is True
    assert proposals[0]["body"] == "urgent fix"
    assert proposals[0]["tags"] == ["backend"]


def test_parse_proposals_multiple_blocks():
    from bute.commands.chat import parse_proposals

    response = (
        "First batch:\n```bt\n. task one\n```\n"
        "Second batch:\n```bt\n. task two\n- note three\n```"
    )
    proposals = parse_proposals(response)
    assert len(proposals) == 3


def test_parse_proposals_skips_invalid_lines():
    from bute.commands.chat import parse_proposals

    response = "```bt\n. valid task\nthis is not an entry\n\n. another task\n```"
    proposals = parse_proposals(response)
    assert len(proposals) == 2


def test_parse_proposals_empty_response():
    from bute.commands.chat import parse_proposals

    assert parse_proposals("No proposals here.") == []
    assert parse_proposals("") == []


def test_parse_proposals_journal_entry():
    from bute.commands.chat import parse_proposals

    response = "```bt\n= feeling good about progress @reflection\n```"
    proposals = parse_proposals(response)
    assert len(proposals) == 1
    assert proposals[0]["type"] == "journal"
    assert proposals[0]["body"] == "feeling good about progress"
    assert proposals[0]["tags"] == ["reflection"]


def test_execute_bt_view_tasks(tmp_data):
    from bute.commands.chat import execute_bt_view

    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.NOTE, "note one")
    save_entry(e1)
    save_entry(e2)

    results = execute_bt_view(["t"], config=None)
    assert len(results) == 1
    assert results[0].body == "task one"


def test_execute_bt_view_notes(tmp_data):
    from bute.commands.chat import execute_bt_view

    e1 = Entry.create(EntryType.NOTE, "note one")
    save_entry(e1)

    results = execute_bt_view(["n"], config=None)
    assert len(results) == 1
    assert results[0].body == "note one"


def test_execute_bt_view_tag_filter(tmp_data):
    from bute.commands.chat import execute_bt_view

    e1 = Entry.create(EntryType.TASK, "tagged", tags=["work"])
    e2 = Entry.create(EntryType.TASK, "untagged")
    save_entry(e1)
    save_entry(e2)

    results = execute_bt_view(["@work"], config=None)
    assert len(results) == 1
    assert results[0].body == "tagged"


def test_execute_bt_view_type_with_tag(tmp_data):
    from bute.commands.chat import execute_bt_view

    e1 = Entry.create(EntryType.TASK, "work task", tags=["work"])
    e2 = Entry.create(EntryType.NOTE, "work note", tags=["work"])
    save_entry(e1)
    save_entry(e2)

    results = execute_bt_view(["t", "@work"], config=None)
    assert len(results) == 1
    assert results[0].type == EntryType.TASK


def test_execute_bt_view_empty_args(tmp_data):
    from bute.commands.chat import execute_bt_view

    assert execute_bt_view([], config=None) == []


def test_execute_bt_view_important(tmp_data):
    from bute.commands.chat import execute_bt_view

    e1 = Entry.create(EntryType.TASK, "normal task")
    e2 = Entry.create(EntryType.TASK, "urgent task", important=True)
    save_entry(e1)
    save_entry(e2)

    results = execute_bt_view(["!"], config=None)
    assert len(results) == 1
    assert results[0].important is True
