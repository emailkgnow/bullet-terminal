"""Tests for --json output on views."""

import json
from datetime import date

from bute.cli import main
from bute.models import Entry, EntryType
from bute.state import state_path
from bute.storage import save_entry


def _parse(output: str) -> dict:
    return json.loads(output)


def test_backlog_json_flag_after_command(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "alpha", tags=["x"], due=date(2026, 9, 20)))
    result = runner.invoke(main, ["b", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"] == "Task Backlog"
    assert len(data["entries"]) == 1
    e = data["entries"][0]
    assert e["n"] == 1
    assert e["body"] == "alpha"
    assert e["type"] == "task"
    assert e["status"] == "active"
    assert e["tags"] == ["x"]
    assert e["due"] == "2026-09-20"
    assert e["date"] is None


def test_json_flag_before_command(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "alpha"))
    result = runner.invoke(main, ["--json", "b"])
    assert result.exit_code == 0, result.output
    assert _parse(result.output)["entries"][0]["body"] == "alpha"


def test_signifier_view_with_json_is_a_view_not_capture(runner, tmp_config, tmp_data):
    """bt t --json must route to the Tasks view, not capture a task named '--json'."""
    result = runner.invoke(main, ["t", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"] == "Task Log"
    entries_dir = tmp_data / "entries"
    assert not entries_dir.exists() or list(entries_dir.rglob("*.md")) == []


def test_json_numbers_match_state(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "plain"))
    save_entry(Entry.create(EntryType.TASK, "urgent", important=True))
    result = runner.invoke(main, ["b", "--json"])
    data = _parse(result.output)
    state = json.loads(state_path().read_text())
    assert [e["id"] for e in data["entries"]] == state["entries"]
    assert data["entries"][0]["body"] == "urgent"  # important sorts first


def test_grouped_view_json(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.NOTE, "a note"))
    result = runner.invoke(main, ["n", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"] == "Notes"
    assert data["entries"][0]["body"] == "a note"


def test_empty_view_json(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["b", "--json"])
    assert result.exit_code == 0, result.output
    assert _parse(result.output) == {"view": "Task Backlog", "entries": []}


def test_focus_log_json_skips_habits_and_whisper(runner, tmp_config, tmp_data):
    from bute.config import TOUR_DONE
    TOUR_DONE.parent.mkdir(parents=True, exist_ok=True)
    TOUR_DONE.touch()
    from bute.state import mark_dp_done, mark_wp_done
    mark_dp_done()
    mark_wp_done()  # never fall into the interactive weekly plan on its trigger day
    save_entry(Entry.create(EntryType.TASK, "today task", focus_date=date.today()))
    save_entry(Entry.create(EntryType.TASK, "meditate", repeat="daily"))

    result = runner.invoke(main, ["--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"].startswith("Focus Log")
    bodies = [e["body"] for e in data["entries"]]
    assert "today task" in bodies
    # Output must be a single JSON document — no habit table or whisper appended
    assert result.output.strip().count("\n") == 0
    state = json.loads(state_path().read_text())
    assert [e["id"] for e in data["entries"]] == state["entries"]
    assert "extra_entries" not in state


def test_due_json(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "late", due=date(2020, 1, 1)))
    result = runner.invoke(main, ["due", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"] == "Due Tasks"
    assert data["entries"][0]["body"] == "late"
    assert data["entries"][0]["group"] == "Overdue"


def test_tags_json(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "a", tags=["x", "y"]))
    save_entry(Entry.create(EntryType.TASK, "b", tags=["x"]))
    result = runner.invoke(main, ["tags", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data == {"view": "Tags", "tags": [{"tag": "x", "count": 2}, {"tag": "y", "count": 1}]}


def test_find_json(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.NOTE, "OAuth tokens expire"))
    result = runner.invoke(main, ["find", "OAuth", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["entries"][0]["body"] == "OAuth tokens expire"
