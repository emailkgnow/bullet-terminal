"""Tests for the nudges command."""

from unittest.mock import MagicMock, patch

from bute.cli import main
from bute.config import default_config, save_config
from bute.models import Entry, EntryType
from bute.storage import save_entry


def _setup(tmp_config, tmp_data):
    doc = default_config(provider="anthropic")
    doc["ai"]["api_key"] = "sk-test"
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


def _mock_llm(response="- You have stale tasks\n- Journal shows a pattern"):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = response
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    return patch("dwn.ai.llm._get_client", return_value=mock_client)


def test_nudges_no_ai(runner, tmp_config, tmp_data):
    doc = default_config(provider="anthropic")
    doc["ai"]["api_key"] = ""
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)

    result = runner.invoke(main, ["nudges"])
    assert result.exit_code == 0
    assert "AI" in result.output


def test_nudges_with_entries(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "stale task")
    save_entry(e)

    with _mock_llm():
        result = runner.invoke(main, ["nudges"])
    assert result.exit_code == 0
    assert "stale" in result.output.lower()


def test_nudges_no_entries(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    with _mock_llm():
        result = runner.invoke(main, ["nudges"])
    assert "No entries" in result.output
