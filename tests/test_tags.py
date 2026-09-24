"""Tests for tag commands."""

import re
from unittest.mock import MagicMock, patch

import pytest

from bute.cli import main
from bute.config import default_config, save_config
from bute.models import Entry, EntryType
from bute.storage import save_entry


def _setup(tmp_config, tmp_data):
    doc = default_config()
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


def _tag_lines(output):
    """Split `bt tags` output into (header line, {tag: row line})."""
    lines = output.splitlines()
    header = next(line for line in lines if line.lstrip().startswith("Tags"))
    rows = {}
    for line in lines:
        m = re.search(r"@(\S+)", line)
        if m:
            rows[m.group(1)] = line
    return header, rows


def test_tags_list_shows_type_breakdown(runner, tmp_config, tmp_data):
    """Each tag row shows its total, then a count per entry type."""
    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")
    save_entry(Entry.create(EntryType.TASK, "buy tiles", tags=["home-reno"]))

    result = runner.invoke(main, ["tags"])
    assert result.exit_code == 0, result.output
    _, rows = _tag_lines(result.output)
    # total 4 = 2 tasks, 1 note, 1 journal, 0 calendar (blank)
    assert re.search(r"@home-reno\s+4\s+2\s+1\s+1\s*$", rows["home-reno"])


def test_tags_list_drops_stage_column(runner, tmp_config, tmp_data):
    """The Stage column (remnant of the removed analyze feature) is gone."""
    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")

    result = runner.invoke(main, ["tags"])
    assert result.exit_code == 0, result.output
    assert "Stage" not in result.output
    assert "raw" not in result.output


def test_tags_list_counts_sit_under_their_symbols(runner, tmp_config, tmp_data):
    """Each count's last digit lines up with its type symbol in the header."""
    _setup(tmp_config, tmp_data)
    save_entry(Entry.create(EntryType.NOTE, "n", tags=["notesonly"]))
    save_entry(Entry.create(EntryType.CALENDAR, "c", tags=["calonly"]))
    for i in range(12):
        save_entry(Entry.create(EntryType.TASK, f"t{i}", tags=["a-much-longer-tag"]))

    result = runner.invoke(main, ["tags"])
    assert result.exit_code == 0, result.output
    header, rows = _tag_lines(result.output)
    note_col = header.index(" - ") + 1
    cal_col = header.rindex("o")
    task_col = header.index(" . ") + 1
    assert rows["notesonly"][note_col] == "1"
    assert rows["calonly"][cal_col] == "1"
    assert rows["a-much-longer-tag"][task_col - 1 : task_col + 1] == "12"


def test_tags_list_sorted_by_count_then_name(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    save_entry(Entry.create(EntryType.TASK, "a", tags=["zeta", "beta"]))
    save_entry(Entry.create(EntryType.TASK, "b", tags=["zeta"]))
    save_entry(Entry.create(EntryType.TASK, "c", tags=["alpha"]))

    result = runner.invoke(main, ["tags"])
    assert result.exit_code == 0, result.output
    order = re.findall(r"@(\S+)", result.output)
    assert order == ["zeta", "alpha", "beta"]


_KEY_ROW = re.compile(r"#\s+\.\s+-\s+=\s+o\s*$")


def test_tags_list_repeats_key_row_below_last_tag(runner, tmp_config, tmp_data):
    """A long list scrolls the header away, so the key row is repeated at the bottom, aligned."""
    _setup(tmp_config, tmp_data)
    for i in range(5):
        save_entry(Entry.create(EntryType.NOTE, f"n{i}", tags=[f"tag{i}"]))

    result = runner.invoke(main, ["tags"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    keys = [i for i, line in enumerate(lines) if _KEY_ROW.search(line)]
    last_tag = max(i for i, line in enumerate(lines) if "@" in line)
    assert len(keys) == 2
    assert keys[1] > last_tag
    header, footer = lines[keys[0]], lines[keys[1]]
    for symbol in "#.-=o":
        assert header.rindex(symbol) == footer.rindex(symbol)


def test_tags_list_ends_with_legend(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")

    result = runner.invoke(main, ["tags"])
    assert result.exit_code == 0, result.output
    legend = [line for line in result.output.splitlines() if line.strip()][-1]
    positions = [legend.index(s) for s in (
        "# total", ". tasks", "- notes", "= journals", "o calendar",
    )]
    assert positions == sorted(positions)


def test_tags_list_colors_counts_by_type(runner, tmp_config, tmp_data, monkeypatch):
    """Each per-type count wears its type's color, matching the symbols in the key rows."""
    from rich.console import Console

    import bute.commands.views as views

    monkeypatch.setattr(views, "console", Console(force_terminal=True, color_system="standard", width=80))
    _setup(tmp_config, tmp_data)
    for body, et in [("t", EntryType.TASK), ("t2", EntryType.TASK), ("n", EntryType.NOTE)]:
        save_entry(Entry.create(et, body, tags=["mix"]))
    save_entry(Entry.create(EntryType.JOURNAL, "j", tags=["mix"]))
    save_entry(Entry.create(EntryType.CALENDAR, "c", tags=["mix"]))

    result = runner.invoke(main, ["tags"])
    assert result.exit_code == 0, result.output
    row = next(line for line in result.output.splitlines() if "@mix" in line)
    assert re.search(r"\x1b\[36m\s*2\x1b\[0m", row)  # tasks: cyan
    assert re.search(r"\x1b\[33m\s*1\x1b\[0m", row)  # notes: yellow
    assert re.search(r"\x1b\[35m\s*1\x1b\[0m", row)  # journals: magenta
    assert re.search(r"\x1b\[32m\s*1\x1b\[0m", row)  # calendar: green


