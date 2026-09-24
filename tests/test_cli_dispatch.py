"""Dispatch tests for the task scope flags and the signifier words."""

import pytest

from bute.cli import main


def test_bt_b_is_gone(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["b"])
    assert result.exit_code != 0


def test_bt_w_is_gone(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["w"])
    assert result.exit_code != 0


def test_bt_backlog_long_form_is_gone(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["backlog"])
    assert result.exit_code != 0


def test_scope_flag_alone_is_a_view(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "in the backlog"))
    result = runner.invoke(main, ["t", "-b"])
    assert result.exit_code == 0, result.output
    assert "Tasks — Backlog" in result.output


def test_scope_flag_with_text_is_a_capture(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    result = runner.invoke(main, ["t", "-b", "buy", "milk"])
    assert result.exit_code == 0, result.output
    entries = query_and_load(type="task")
    assert [e.body for e in entries] == ["buy milk"]


def test_scope_flags_do_not_break_literal_json_in_capture_text(runner, tmp_config, tmp_data):
    """The --json-in-body contract (test_json_output.py:211) survives the new flags."""
    from bute.storage import query_and_load

    result = runner.invoke(main, ["n", "add", "--json", "flag", "to", "api"])
    assert result.exit_code == 0, result.output
    bodies = [e.body for e in query_and_load(None, type="note")]
    assert bodies == ["add --json flag to api"]


# --- cal / jrnl replace calendar / journal as the typed words ---

def test_cal_captures_calendar_entry(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    result = runner.invoke(main, ["cal", "dentist", "time:14:30"])
    assert result.exit_code == 0, result.output
    assert [e.body for e in query_and_load(None, type="calendar")] == ["dentist"]


def test_jrnl_captures_journal_entry(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    result = runner.invoke(main, ["jrnl!", "rough", "morning"])
    assert result.exit_code == 0, result.output
    entries = query_and_load(None, type="journal")
    assert [e.body for e in entries] == ["rough morning"]
    assert entries[0].important


def test_cal_and_jrnl_alone_are_views(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.CALENDAR, "standup"))
    save_entry(Entry.create(EntryType.JOURNAL, "quiet day"))
    assert "standup" in runner.invoke(main, ["cal"]).output
    assert "quiet day" in runner.invoke(main, ["jrnl"]).output


@pytest.mark.parametrize("args,hint", [
    (["calendar", "meet", "mom"], "bt cal"),
    (["calendar"], "bt cal"),
    (["calendar!"], "bt cal!"),
    (["journal", "rough", "day"], "bt jrnl"),
    (["journal"], "bt jrnl"),
])
def test_old_words_point_to_new(runner, tmp_config, tmp_data, args, hint):
    result = runner.invoke(main, args)
    assert result.exit_code != 0
    assert hint in result.output
    assert list(tmp_data.rglob("entries/**/*.md")) == [], "nothing should be written"
