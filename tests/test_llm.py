"""Tests for the LLM client module."""

from unittest.mock import MagicMock, patch

import pytest

openai = pytest.importorskip("openai", reason="openai not installed")

from bute.ai.llm import is_available, reset, send_message


@pytest.fixture(autouse=True)
def _reset_llm():
    """Reset LLM client state between tests."""
    reset()
    yield
    reset()


def test_is_available_with_key():
    config = {"ai": {"provider": "anthropic", "api_key": "sk-test", "base_url": "", "model": ""}}
    assert is_available(config) is True


def test_is_available_no_key():
    config = {"ai": {"provider": "anthropic", "api_key": "", "base_url": "", "model": ""}}
    assert is_available(config) is False


def test_is_available_ollama_no_key():
    config = {"ai": {"provider": "ollama", "api_key": "", "base_url": "", "model": ""}}
    assert is_available(config) is True


def test_send_message_returns_text():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test response"

    with patch("bute.ai.llm._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        result = send_message("system", "user")
        assert result == "Test response"


def test_send_message_error_returns_fallback():
    with patch("bute.ai.llm._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        mock_client_fn.return_value = mock_client

        result = send_message("system", "user")
        assert result == "[AI unavailable]"


def test_send_with_entries_formats_context():
    from bute.ai.llm import send_with_entries
    from bute.models import Entry, EntryType

    entries = [
        Entry.create(EntryType.TASK, "call dentist", tags=["health"]),
        Entry.create(EntryType.JOURNAL, "feeling good"),
    ]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Synthesis"

    with patch("bute.ai.llm._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        result = send_with_entries("system", entries, "question")
        assert result == "Synthesis"

        # Verify entries were in the user message
        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "call dentist" in user_msg
        assert "feeling good" in user_msg


def test_stream_chat_yields_chunks():
    from bute.ai.llm import stream_chat

    chunk1 = MagicMock()
    chunk1.choices = [MagicMock()]
    chunk1.choices[0].delta.content = "Hello"

    chunk2 = MagicMock()
    chunk2.choices = [MagicMock()]
    chunk2.choices[0].delta.content = " world"

    with patch("bute.ai.llm._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([chunk1, chunk2])
        mock_client_fn.return_value = mock_client

        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "hello"},
        ]
        chunks = list(stream_chat(messages))
        assert chunks == ["Hello", " world"]

        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["stream"] is True
        assert call_args[1]["messages"] == messages


def test_stream_chat_error_yields_fallback():
    from bute.ai.llm import stream_chat

    with patch("bute.ai.llm._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        mock_client_fn.return_value = mock_client

        chunks = list(stream_chat([{"role": "user", "content": "hi"}]))
        assert chunks == ["[AI unavailable]"]
