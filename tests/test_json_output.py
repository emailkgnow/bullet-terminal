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
    assert data["view"] == "Tasks — Backlog"
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
    assert data["view"] == "Tasks — All"
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
    assert _parse(result.output) == {"view": "Tasks — Backlog", "entries": []}


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


def test_find_json_empty(runner, tmp_config, tmp_data):
    """The no-results early return in find_cmd must also emit JSON, not Rich text."""
    result = runner.invoke(main, ["find", "nonexistent", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data == {"view": 'Find: "nonexistent"', "entries": []}


def test_extra_meta_is_raw_not_escaped_in_json(runner, tmp_config, tmp_data):
    """Task 6 wraps extra_meta in rich.markup.escape() for terminal rendering;
    JSON must carry the literal value an agent would need to round-trip."""
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"key": "[bold]x"}))
    result = runner.invoke(main, ["b", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["entries"][0]["extra"]["key"] == "[bold]x"


def test_dash_at_tag_filter_then_json_flag(runner, tmp_config, tmp_data):
    """bt -@habit --json must still route as a tag-exclude filter, not choke
    on -@ as an unrecognized option once --json is hoisted in front of it."""
    save_entry(Entry.create(EntryType.TASK, "plain"))
    save_entry(Entry.create(EntryType.TASK, "habit task", tags=["habit"]))
    result = runner.invoke(main, ["-@habit", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    bodies = [e["body"] for e in data["entries"]]
    assert "plain" in bodies
    assert "habit task" not in bodies


def test_json_flag_then_dash_at_tag_filter(runner, tmp_config, tmp_data):
    """Same as above with the flag before the -@tag token."""
    save_entry(Entry.create(EntryType.TASK, "plain"))
    save_entry(Entry.create(EntryType.TASK, "habit task", tags=["habit"]))
    result = runner.invoke(main, ["--json", "-@habit"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    bodies = [e["body"] for e in data["entries"]]
    assert "plain" in bodies
    assert "habit task" not in bodies


def test_bare_json_skips_tour_wp_and_dp_rituals(runner, tmp_config, tmp_data):
    """bt --json on an ordinary morning (dp/wp not done, no tour marker) must
    return the Focus Log unconditionally — never fall into an interactive
    ritual, which would also write focus/week-date side effects."""
    from bute.state import is_dp_done_today, is_wp_done_this_week
    from bute.config import TOUR_DONE

    save_entry(Entry.create(EntryType.TASK, "today task", focus_date=date.today()))
    config = None
    from bute.config import load_config
    config = load_config()

    assert not is_dp_done_today(config)
    assert not is_wp_done_this_week(config)

    result = runner.invoke(main, ["--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"].startswith("Focus Log")
    assert any(e["body"] == "today task" for e in data["entries"])

    # No ritual side effects — dp/wp still undone, no tour marker written.
    assert not is_dp_done_today(config)
    assert not is_wp_done_this_week(config)
    assert not TOUR_DONE.exists()


def test_like_json_without_embeddings(runner, tmp_config, tmp_data, monkeypatch):
    """When embeddings aren't installed, bt like --json must emit JSON
    (with an error field), not the Rich install-instructions message."""
    import bute.ai as ai_mod
    monkeypatch.setattr(ai_mod, "is_embedding_available", lambda: False)

    result = runner.invoke(main, ["like", "productivity", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"] == "Like"
    assert data["entries"] == []
    assert "error" in data


# --- --json must never be stripped out of captured text ---

def test_capture_keeps_literal_json_token_in_body(runner, tmp_config, tmp_data):
    """`bt n add --json flag to api` stores the word, it does not vanish."""
    result = runner.invoke(main, ["n", "add", "--json", "flag", "to", "api"])
    assert result.exit_code == 0, result.output
    from bute.storage import query_and_load
    notes = query_and_load(None, type="note")
    assert [e.body for e in notes] == ["add --json flag to api"]


def test_capture_word_signifier_keeps_literal_json_token(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["note", "add", "--json", "flag"])
    assert result.exit_code == 0, result.output
    from bute.storage import query_and_load
    notes = query_and_load(None, type="note")
    assert [e.body for e in notes] == ["add --json flag"]


def test_mod_keeps_literal_json_token_in_body(runner, tmp_config, tmp_data):
    from bute.state import save_state
    from bute.storage import entry_path_from_id, load_entry
    entry = Entry.create(EntryType.TASK, "old text")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "mod", "add", "--json", "flag"])
    assert result.exit_code == 0, result.output
    assert load_entry(entry_path_from_id(entry.id)).body == "add --json flag"


def test_action_json_flag_still_hoists(runner, tmp_config, tmp_data):
    """A non-capture action keeps working with a trailing --json."""
    from bute.state import save_state
    from bute.storage import entry_path_from_id, load_entry
    from bute.models import TaskStatus
    entry = Entry.create(EntryType.TASK, "finish me")
    save_entry(entry)
    save_state("ls", [entry.id])

    result = runner.invoke(main, ["1", "done", "--json"])
    assert result.exit_code == 0, result.output
    assert load_entry(entry_path_from_id(entry.id)).status == TaskStatus.DONE


def test_signifier_view_with_tag_and_json_still_routes_to_view(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "tagged", tags=["x"], week_date=None))
    result = runner.invoke(main, ["t", "@x", "--json"])
    assert result.exit_code == 0, result.output
    assert _parse(result.output)["view"].startswith("Task")
