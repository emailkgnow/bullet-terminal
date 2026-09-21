"""Tests for view commands."""

import json

from bute.cli import main
from bute.config import default_config, save_config
from bute.state import state_path


def _setup_config(tmp_config, tmp_data):
    doc = default_config()
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


def test_tasks_view_empty(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["tasks"])
    assert result.exit_code == 0


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
    runner.invoke(main, ["t", "-b"])
    path = state_path()
    assert path.exists()
    state = json.loads(path.read_text())
    assert state["view"] == "backlog"
    assert len(state["entries"]) > 0


def test_tasks_view_excludes_recurring(tmp_config, tmp_data, runner):
    """bt t / bt b exclude recurring tasks regardless of @habit tag."""
    from bute.cli import main
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    regular = Entry.create(entry_type=EntryType.TASK, body="call dentist")
    save_entry(regular)

    recurring = Entry.create(entry_type=EntryType.TASK, body="meditate", repeat="daily")
    save_entry(recurring)

    result = runner.invoke(main, ["t", "-b"])
    assert "call dentist" in result.output
    assert "meditate" not in result.output


def test_list_view_shows_extra_meta(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"project": "alpha"}))
    result = runner.invoke(main, ["t", "-b"])
    assert result.exit_code == 0, result.output
    assert "project:alpha" in result.output


def test_list_view_safe_with_unmatched_rich_tag_in_extra_meta(runner, tmp_config, tmp_data):
    """Verify list view (table) doesn't crash when extra_meta contains unmatched Rich markup."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    # Unmatched closing tag [/] would crash Rich table without escaping
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"key": "[/]"}))
    result = runner.invoke(main, ["t", "-b"])
    assert result.exit_code == 0, result.output
    # Literal value should appear in output
    assert "key:[/]" in result.output


def test_list_view_renders_literal_text_with_styling_markup_in_extra_meta(runner, tmp_config, tmp_data):
    """Verify that styling markup like [bold] is rendered literally, not consumed as styling."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    # [bold]x should render as literal text, not as bold x
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"key": "[bold]x"}))
    result = runner.invoke(main, ["t", "-b"])
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


# --- bt t scopes: bare = today, -w = this week, -b = backlog ---


def _planned_week(*bodies_and_tags):
    """Save active tasks selected for the current week. Returns nothing."""
    from bute.models import Entry, EntryType
    from bute.ritual_ops import week_anchor
    from bute.storage import save_entry

    for body, tags in bodies_and_tags:
        save_entry(
            Entry.create(EntryType.TASK, body, tags=list(tags), week_date=week_anchor())
        )


def test_week_view_tag_filter(runner, tmp_config, tmp_data):
    _planned_week(("fix bug", ["backend"]), ("call dentist", []))
    result = runner.invoke(main, ["t", "-w", "@backend"])
    assert result.exit_code == 0, result.output
    assert "fix bug" in result.output
    assert "call dentist" not in result.output


def test_week_writes_state(runner, tmp_config, tmp_data):
    _planned_week(("call dentist", []))
    runner.invoke(main, ["t", "-w"])
    state = json.loads(state_path().read_text())
    assert state["view"] == "week"
    assert len(state["entries"]) == 1


def test_week_view_does_not_fall_back_to_backlog(runner, tmp_config, tmp_data):
    """An empty week is empty — bt t -w must not silently become bt t -b."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["t", "-w"])
    assert result.exit_code == 0, result.output
    assert "someday maybe" not in result.output


def test_week_view_ignores_recurring_when_deciding_emptiness(runner, tmp_config, tmp_data):
    """Recurring tasks carry week_date but are filtered out — they must not mask an empty week."""
    from bute.models import Entry, EntryType
    from bute.ritual_ops import week_anchor
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "exercise", repeat="daily", week_date=week_anchor()))
    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["t", "-w"])
    assert result.exit_code == 0, result.output
    assert "someday maybe" not in result.output
    assert "exercise" not in result.output


def test_week_view_empty_points_at_wp(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["t", "-w"])
    assert "bt wp" in result.output


def test_week_view_empty_still_emits_json(runner, tmp_config, tmp_data):
    import json as _json
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["t", "-w", "--json"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output.strip().splitlines()[-1])
    assert data["entries"] == []


def test_tasks_view_shows_today(runner, tmp_config, tmp_data):
    from datetime import date
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "on today", focus_date=date.today()))
    save_entry(Entry.create(EntryType.TASK, "someday maybe"))

    result = runner.invoke(main, ["t"])
    assert result.exit_code == 0, result.output
    assert "on today" in result.output
    assert "someday maybe" not in result.output
    assert "Tasks — Today" in result.output


def test_tasks_week_scope(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.ritual_ops import week_anchor
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "planned this week", week_date=week_anchor()))
    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["t", "-w"])
    assert result.exit_code == 0, result.output
    assert "planned this week" in result.output
    assert "someday maybe" not in result.output


def test_tasks_backlog_scope(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType, TaskStatus
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "someday maybe"))
    done = Entry.create(EntryType.TASK, "already finished")
    done.status = TaskStatus.DONE
    save_entry(done)

    result = runner.invoke(main, ["t", "-b"])
    assert result.exit_code == 0, result.output
    assert "someday maybe" in result.output
    assert "already finished" not in result.output


def test_tasks_backlog_all_is_every_task(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType, TaskStatus
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "still open"))
    done = Entry.create(EntryType.TASK, "already finished")
    done.status = TaskStatus.DONE
    save_entry(done)

    result = runner.invoke(main, ["t", "-b", "-a"])
    assert result.exit_code == 0, result.output
    assert "still open" in result.output
    assert "already finished" in result.output
    assert "Tasks — All" in result.output


def test_task_scope_grouping_pins_date_column(runner, tmp_config, tmp_data):
    """Only `bt t -b -a` groups by date; bt t / bt t -w / bt t -b stay flat lists."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "ordinary task"))

    result = runner.invoke(main, ["t", "-b", "-a"])
    assert result.exit_code == 0, result.output
    assert "Date" in result.output

    for args in (["t"], ["t", "-w"], ["t", "-b"]):
        result = runner.invoke(main, args)
        assert result.exit_code == 0, result.output
        assert "Date" not in result.output


def test_tasks_scopes_are_exclusive(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["t", "-w", "-b"])
    assert result.exit_code != 0
    assert "one scope" in result.output.lower()


def test_tasks_scope_excludes_recurring(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "meditate", repeat="daily"))
    save_entry(Entry.create(EntryType.TASK, "ordinary task"))

    result = runner.invoke(main, ["t", "-b"])
    assert "meditate" not in result.output
    assert "ordinary task" in result.output


def test_tasks_scope_tag_filter(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "tagged one", tags=["backend"]))
    save_entry(Entry.create(EntryType.TASK, "untagged one"))

    result = runner.invoke(main, ["t", "-b", "@backend"])
    assert result.exit_code == 0, result.output
    assert "tagged one" in result.output
    assert "untagged one" not in result.output


def test_tasks_scopes_write_distinct_state(runner, tmp_config, tmp_data):
    import json as _json
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "alpha"))

    for args, view in (
        (["t"], "tasks"),
        (["t", "-w"], "week"),
        (["t", "-b"], "backlog"),
    ):
        runner.invoke(main, args)
        state = _json.loads(state_path().read_text())
        assert state["view"] == view, args


def test_dp_pool_still_falls_back_to_backlog(tmp_config, tmp_data):
    """bt dp offers the backlog when the week is unplanned — that fallback must survive."""
    from bute.models import Entry, EntryType
    from bute.ritual_ops import get_weekly_active_tasks
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    assert {e.body for e in get_weekly_active_tasks(None)} == {"someday maybe"}


def test_important_task_scope_defaults_to_today(runner, tmp_config, tmp_data):
    from datetime import date
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "urgent today", important=True, focus_date=date.today()))
    save_entry(Entry.create(EntryType.TASK, "urgent someday", important=True))

    result = runner.invoke(main, ["t!"])
    assert result.exit_code == 0, result.output
    assert "urgent today" in result.output
    assert "urgent someday" not in result.output


def test_important_task_backlog_scope(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "urgent someday", important=True))
    save_entry(Entry.create(EntryType.TASK, "ordinary someday"))

    result = runner.invoke(main, ["t!", "-b"])
    assert result.exit_code == 0, result.output
    assert "urgent someday" in result.output
    assert "ordinary someday" not in result.output


def test_important_non_task_types_ignore_scope(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.NOTE, "big idea", important=True))

    result = runner.invoke(main, ["n!"])
    assert result.exit_code == 0, result.output
    assert "big idea" in result.output


def test_important_task_scopes_are_exclusive(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["t!", "-w", "-b"])
    assert result.exit_code != 0
    assert "one scope" in result.output.lower()


def test_important_task_backlog_scope_tag_filter(runner, tmp_config, tmp_data):
    """bt t! -b @backend composes the important filter, the backlog scope, and the tag filter."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "urgent tagged", important=True, tags=["backend"]))
    save_entry(Entry.create(EntryType.TASK, "urgent untagged", important=True))

    result = runner.invoke(main, ["t!", "-b", "@backend"])
    assert result.exit_code == 0, result.output
    assert "urgent tagged" in result.output
    assert "urgent untagged" not in result.output


def test_important_non_task_tag_filter(runner, tmp_config, tmp_data):
    """bt n! @idea filters important notes by tag too."""
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.NOTE, "big idea", important=True, tags=["idea"]))
    save_entry(Entry.create(EntryType.NOTE, "other thought", important=True))

    result = runner.invoke(main, ["n!", "@idea"])
    assert result.exit_code == 0, result.output
    assert "big idea" in result.output
    assert "other thought" not in result.output
