"""Tests for tag commands."""

from unittest.mock import MagicMock, patch

import pytest

from bute.cli import main
from bute.config import default_config, save_config
from bute.models import Entry, EntryType
from bute.storage import save_entry


def _setup(tmp_config, tmp_data):
    doc = default_config(provider="anthropic")
    doc["ai"]["api_key"] = "sk-test"
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


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


