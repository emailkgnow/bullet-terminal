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
