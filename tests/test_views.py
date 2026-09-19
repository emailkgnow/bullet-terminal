"""Tests for view commands."""

import json

from bute.cli import main
from bute.config import default_config, save_config
from bute.state import state_path


def _setup_config(tmp_config, tmp_data):
    doc = default_config()
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


def test_tasks_view(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["tasks"])
    assert result.exit_code == 0
    assert "call dentist" in result.output


def test_tasks_view_empty(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["tasks"])
    assert result.exit_code == 0


def test_backlog_view(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["backlog"])
    assert result.exit_code == 0
    assert "call dentist" in result.output
    assert "fix bug" in result.output


def test_notes_view(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["notes"])
    assert result.exit_code == 0
    assert "OAuth2 tokens" in result.output


def test_tag_filter(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["@backend"])
    assert result.exit_code == 0
    assert "fix bug" in result.output
    assert "call dentist" not in result.output


def test_tag_filter_empty(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["@nonexistent"])
    assert result.exit_code == 0
    assert "No entries found" in result.output


def test_tasks_writes_state(runner, tmp_config, populated_data):
    runner.invoke(main, ["tasks"])
    path = state_path()
    assert path.exists()
    state = json.loads(path.read_text())
    assert state["view"] == "tasks"
    assert len(state["entries"]) > 0


def test_backlog_writes_state(runner, tmp_config, populated_data):
    runner.invoke(main, ["backlog"])
    path = state_path()
    state = json.loads(path.read_text())
    assert state["view"] == "backlog"
    assert len(state["entries"]) == 2  # both active tasks


def test_tasks_view_excludes_recurring(tmp_config, tmp_data, runner):
    """bt t / bt b exclude recurring tasks regardless of @habit tag."""
    from bute.cli import main
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    regular = Entry.create(entry_type=EntryType.TASK, body="call dentist")
    save_entry(regular)

    recurring = Entry.create(entry_type=EntryType.TASK, body="meditate", repeat="daily")
    save_entry(recurring)

    result = runner.invoke(main, ["b"])
    assert "call dentist" in result.output
    assert "meditate" not in result.output


def test_list_view_shows_extra_meta(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"project": "alpha"}))
    result = runner.invoke(main, ["b"])
    assert result.exit_code == 0, result.output
    assert "project:alpha" in result.output


def test_list_view_safe_with_unmatched_rich_tag_in_extra_meta(runner, tmp_config, tmp_data):
    """Verify list view (table) doesn't crash when extra_meta contains unmatched Rich markup."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    # Unmatched closing tag [/] would crash Rich table without escaping
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"key": "[/]"}))
    result = runner.invoke(main, ["b"])
    assert result.exit_code == 0, result.output
    # Literal value should appear in output
    assert "key:[/]" in result.output


def test_list_view_renders_literal_text_with_styling_markup_in_extra_meta(runner, tmp_config, tmp_data):
    """Verify that styling markup like [bold] is rendered literally, not consumed as styling."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    # [bold]x should render as literal text, not as bold x
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"key": "[bold]x"}))
    result = runner.invoke(main, ["b"])
    assert result.exit_code == 0, result.output
    # Literal value should appear (without being consumed as markup)
    assert "key:[bold]x" in result.output


def test_show_entry_safe_with_rich_markup_in_extra_meta(runner, tmp_config, tmp_data, monkeypatch):
    """Verify bt <n> show (display_entry_full) doesn't crash with markup in extra_meta."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    from bute.state import save_state
    from bute.cli import main

    # Mock shutil.which to disable leaf, forcing Rich fallback
    import shutil
    real_which = shutil.which
    monkeypatch.setattr(
        shutil, "which",
        lambda cmd, *a, **kw: None if cmd == "leaf" else real_which(cmd, *a, **kw),
    )

    # Create entry and save it
    entry = Entry.create(EntryType.TASK, "call bank", extra_meta={"key": "[/]"})
    save_entry(entry)
    # Set up state so entry is in the display list
    save_state("tasks", [entry.id])
    # Show the entry
    result = runner.invoke(main, ["1", "show"])
    assert result.exit_code == 0, result.output
    # Literal value should appear in the output
    assert "key:[/]" in result.output


def test_list_view_hides_underscore_prefixed_extra_meta(runner, tmp_config, tmp_data):
    """Underscore-prefixed keys are private to the external writer — never displayed."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    save_entry(Entry.create(
        EntryType.CALENDAR, "visit mom",
        scheduled_time="14:30",
        extra_meta={"_gcal_id": "A5E6A2D6-6AEE-405A-BE38-4E661B92A068:2026-09-29"},
    ))
    result = runner.invoke(main, ["c"])
    assert result.exit_code == 0, result.output
    assert "visit mom" in result.output
    assert "gcal_id" not in result.output
    assert "2:30 PM" in result.output


def test_show_entry_hides_underscore_prefixed_extra_meta(runner, tmp_config, tmp_data):
    """bt <n> show also omits private keys."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    from bute.state import save_state
    entry = Entry.create(
        EntryType.CALENDAR, "visit mom",
        extra_meta={"_gcal_id": "abc123", "project": "alpha"},
    )
    save_entry(entry)
    save_state("calendar", [entry.id])
    result = runner.invoke(main, ["1", "show"])
    assert "_gcal_id" not in result.output
    assert "abc123" not in result.output


def test_underscore_extra_meta_survives_save_round_trip(runner, tmp_config, tmp_data):
    """Hidden does not mean dropped — gcal-sync must still find its dedup key."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry, load_entry
    entry = Entry.create(EntryType.CALENDAR, "visit mom", extra_meta={"_gcal_id": "abc123"})
    path = save_entry(entry)
    assert load_entry(path).extra_meta["_gcal_id"] == "abc123"


def test_capture_confirmation_hides_underscore_prefixed_extra_meta(runner, tmp_config, tmp_data):
    from bute.display import confirm_capture
    from bute.models import Entry, EntryType
    entry = Entry.create(EntryType.CALENDAR, "visit mom", extra_meta={"_gcal_id": "abc123"})
    confirm_capture(entry)


# --- bt t = every task, grouped by date; bt w = this week's active tasks ---


def test_tasks_view_includes_done_and_dropped(runner, tmp_config, tmp_data):
    """bt t applies no status filter — the true parallel to bt n/j/c."""
    from bute.models import Entry, EntryType, TaskStatus
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "still open"))

    done = Entry.create(EntryType.TASK, "finished")
    done.status = TaskStatus.DONE
    save_entry(done)

    dropped = Entry.create(EntryType.TASK, "abandoned")
    dropped.status = TaskStatus.DROPPED
    save_entry(dropped)

    result = runner.invoke(main, ["t"])
    assert result.exit_code == 0, result.output
    assert "still open" in result.output
    assert "finished" in result.output
    assert "abandoned" in result.output


def test_tasks_view_is_grouped_by_date(runner, tmp_config, populated_data):
    """Grouped rendering gives bt t the Date column that bt n/j/c have."""
    result = runner.invoke(main, ["t"])
    assert result.exit_code == 0, result.output
    assert "Date" in result.output


def test_tasks_view_excludes_recurring_tasks(runner, tmp_config, tmp_data):
    """Recurring tasks keep their own view (bt streak), even now that bt t is unfiltered."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "call dentist"))
    save_entry(Entry.create(EntryType.TASK, "meditate", repeat="daily"))

    result = runner.invoke(main, ["t"])
    assert result.exit_code == 0, result.output
    assert "call dentist" in result.output
    assert "meditate" not in result.output


def test_tasks_view_json_title(runner, tmp_config, tmp_data):
    import json as _json
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "alpha"))
    result = runner.invoke(main, ["t", "--json"])
    assert result.exit_code == 0, result.output
    assert _json.loads(result.output.strip().splitlines()[-1])["view"] == "Tasks — All"


def test_week_view_shows_this_weeks_active_tasks(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.ritual_ops import week_anchor
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "planned this week", week_date=week_anchor()))
    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["w"])
    assert result.exit_code == 0, result.output
    assert "planned this week" in result.output
    assert "someday maybe" not in result.output


def test_week_view_excludes_done(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType, TaskStatus
    from bute.ritual_ops import week_anchor
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "still open", week_date=week_anchor()))

    done = Entry.create(EntryType.TASK, "finished", week_date=week_anchor())
    done.status = TaskStatus.DONE
    save_entry(done)

    result = runner.invoke(main, ["w"])
    assert result.exit_code == 0, result.output
    assert "still open" in result.output
    assert "finished" not in result.output


def _planned_week(*bodies_and_tags):
    """Save active tasks selected for the current week. Returns nothing."""
    from bute.models import Entry, EntryType
    from bute.ritual_ops import week_anchor
    from bute.storage import save_entry

    for body, tags in bodies_and_tags:
        save_entry(
            Entry.create(EntryType.TASK, body, tags=list(tags), week_date=week_anchor())
        )


def test_week_view_full_word(runner, tmp_config, tmp_data):
    _planned_week(("call dentist", []))
    result = runner.invoke(main, ["week"])
    assert result.exit_code == 0, result.output
    assert "call dentist" in result.output


def test_week_view_tag_filter(runner, tmp_config, tmp_data):
    _planned_week(("fix bug", ["backend"]), ("call dentist", []))
    result = runner.invoke(main, ["w", "@backend"])
    assert result.exit_code == 0, result.output
    assert "fix bug" in result.output
    assert "call dentist" not in result.output


def test_week_writes_state(runner, tmp_config, tmp_data):
    _planned_week(("call dentist", []))
    runner.invoke(main, ["w"])
    state = json.loads(state_path().read_text())
    assert state["view"] == "week"
    assert len(state["entries"]) == 1


def test_week_capture_is_not_hijacked(runner, tmp_config, tmp_data):
    """'w' is a view letter only — bt w with text must not silently capture."""
    result = runner.invoke(main, ["w", "buy", "milk"])
    entries_dir = tmp_data / "entries"
    assert not entries_dir.exists() or list(entries_dir.rglob("*.md")) == []


def test_week_view_does_not_fall_back_to_backlog(runner, tmp_config, tmp_data):
    """An empty week is empty — bt w must not silently become bt b."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["w"])
    assert result.exit_code == 0, result.output
    assert "someday maybe" not in result.output


def test_week_view_ignores_recurring_when_deciding_emptiness(runner, tmp_config, tmp_data):
    """Recurring tasks carry week_date but are filtered out — they must not mask an empty week."""
    from bute.models import Entry, EntryType
    from bute.ritual_ops import week_anchor
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "exercise", repeat="daily", week_date=week_anchor()))
    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["w"])
    assert result.exit_code == 0, result.output
    assert "someday maybe" not in result.output
    assert "exercise" not in result.output


def test_week_view_empty_points_at_wp(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["w"])
    assert "bt wp" in result.output


def test_week_view_empty_still_emits_json(runner, tmp_config, tmp_data):
    import json as _json
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["w", "--json"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output.strip().splitlines()[-1])
    assert data["entries"] == []


def test_dp_pool_still_falls_back_to_backlog(tmp_config, tmp_data):
    """bt dp offers the backlog when the week is unplanned — that fallback must survive."""
    from bute.models import Entry, EntryType
    from bute.ritual_ops import get_weekly_active_tasks
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    assert {e.body for e in get_weekly_active_tasks(None)} == {"someday maybe"}
