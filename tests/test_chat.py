"""Tests for the chat command module."""


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
