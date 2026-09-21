"""Dispatch tests for the task scope flags."""

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
