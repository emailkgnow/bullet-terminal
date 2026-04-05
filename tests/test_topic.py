"""Tests for the topic command."""

from unittest.mock import MagicMock, patch

import pytest
openai = pytest.importorskip("openai", reason="openai not installed")

from bute.cli import main
from bute.config import default_config, save_config
from bute.models import Entry, EntryType
from bute.storage import save_entry


def _setup(tmp_config, tmp_data):
    doc = default_config(provider="anthropic")
    doc["ai"]["api_key"] = "sk-test"
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


def _mock_llm(response="Mocked synthesis"):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = response
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    return patch("bute.ai.llm._get_client", return_value=mock_client)


def test_topic_no_ai(runner, tmp_config, tmp_data):
    doc = default_config(provider="anthropic")
    doc["ai"]["api_key"] = ""
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)

    result = runner.invoke(main, ["topic", "test"])
    assert result.exit_code == 0
    assert "AI" in result.output or "openai" in result.output


def test_topic_with_entries(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    e = Entry.create(EntryType.NOTE, "API design notes", tags=["api"])
    save_entry(e)

    with _mock_llm("Here is the synthesis about api"):
        result = runner.invoke(main, ["topic", "api"])
    assert result.exit_code == 0
    assert "synthesis" in result.output.lower()


def test_topic_no_entries(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)

    with _mock_llm():
        result = runner.invoke(main, ["topic", "nonexistent"])
    assert result.exit_code == 0
    assert "No entries" in result.output
