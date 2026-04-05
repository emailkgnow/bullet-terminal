"""Tests for tag analyze command."""

from unittest.mock import MagicMock, patch

import pytest

openai = pytest.importorskip("openai", reason="openai not installed")

from bute.cli import main
from bute.config import default_config, save_config
from bute.db import get_tag_stage
from bute.models import Entry, EntryType
from bute.storage import save_entry


def _setup(tmp_config, tmp_data):
    doc = default_config(provider="anthropic")
    doc["ai"]["api_key"] = "sk-test"
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


@pytest.fixture(autouse=True)
def _reset_llm():
    from bute.ai.llm import reset as reset_llm
    reset_llm()
    yield
    reset_llm()


def _mock_llm(response):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = response
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    return patch("bute.ai.llm._get_client", return_value=mock_client)


def _create_tagged_entries(tag):
    """Create sample entries with the given tag."""
    entries = [
        Entry.create(EntryType.TASK, "fix faucet", tags=[tag]),
        Entry.create(EntryType.NOTE, "kitchen is 12x15", tags=[tag]),
        Entry.create(EntryType.JOURNAL, "excited about reno", tags=[tag]),
    ]
    for e in entries:
        save_entry(e)
    return entries


def test_analyze_tag(runner, tmp_config, tmp_data):
    """bt @home-reno analyze should analyze all tagged entries."""
    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")

    with _mock_llm("Theme A\n- fix faucet\n- kitchen dimensions"):
        result = runner.invoke(main, ["@home-reno", "analyze"], input="y\n")

    assert result.exit_code == 0
    stage = get_tag_stage("home-reno")
    assert stage is not None
    assert stage["stage"] == "analyzed"
    assert "Theme A" in stage["analysis"]


def test_analyze_tag_no_entries(runner, tmp_config, tmp_data):
    """Analyzing a tag with no entries should show a message."""
    _setup(tmp_config, tmp_data)
    result = runner.invoke(main, ["@empty-tag", "analyze"])
    assert "no entries" in result.output.lower()


def test_analyze_tag_rerun_overwrites(runner, tmp_config, tmp_data):
    """Re-running analyze should overwrite previous analysis."""
    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")

    with _mock_llm("First analysis"):
        runner.invoke(main, ["@home-reno", "analyze"], input="y\n")

    with _mock_llm("Second analysis"):
        runner.invoke(main, ["@home-reno", "analyze"], input="y\n")

    stage = get_tag_stage("home-reno")
    assert "Second analysis" in stage["analysis"]
    assert stage["stage"] == "analyzed"


def test_tags_list_shows_stage(runner, tmp_config, tmp_data):
    """bt tags should show stage column with colors."""
    from bute.db import upsert_tag_stage

    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")

    # Directly set stage in DB (avoids dependency on analyze command)
    upsert_tag_stage("home-reno", "analyzed", analysis="Theme A\n- items")

    result = runner.invoke(main, ["tags"])
    assert result.exit_code == 0
    assert "home-reno" in result.output
    assert "analyzed" in result.output


