"""Tests for the chat command module."""

import pytest
from bute.models import Entry, EntryType


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
