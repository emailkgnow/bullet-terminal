"""Tests for habit/recurring task storage and selection."""


def test_get_habit_entries_selects_by_repeat_not_tag(tmp_data):
    """All recurring tasks qualify as habits, @habit tag is not required."""
    from bute.commands.habits import _get_habit_entries
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    # Recurring task WITHOUT @habit tag — should now qualify
    recurring_no_tag = Entry.create(
        entry_type=EntryType.TASK,
        body="daily meditation",
        repeat="daily",
    )
    save_entry(recurring_no_tag)

    # Non-recurring task WITH @habit tag — should NOT qualify
    tagged_no_repeat = Entry.create(
        entry_type=EntryType.TASK,
        body="misleading legacy tag",
        tags=["habit"],
    )
    save_entry(tagged_no_repeat)

    # Recurring weekly task — should qualify (formerly excluded)
    weekly = Entry.create(
        entry_type=EntryType.TASK,
        body="friday status update",
        repeat="weekly",
    )
    save_entry(weekly)

    bodies = {e.body for e in _get_habit_entries(None)}
    assert "daily meditation" in bodies
    assert "friday status update" in bodies
    assert "misleading legacy tag" not in bodies


def test_done_on_recurring_appends_completion(tmp_data):
    """bt <n> done on a recurring task appends today to completions, not status=DONE."""
    from datetime import date
    from bute.commands.action import handle_done
    from bute.models import Entry, EntryType, TaskStatus
    from bute.storage import load_entry, entry_path_from_id, save_entry

    entry = Entry.create(
        entry_type=EntryType.TASK,
        body="meditate",
        repeat="daily",
    )
    save_entry(entry)

    handle_done(entry, [], None)

    reloaded = load_entry(entry_path_from_id(entry.id))
    assert reloaded.status == TaskStatus.ACTIVE  # never transitions to DONE
    assert date.today().isoformat() in reloaded.completions


def test_compact_date_runs_empty():
    from bute.models import compact_date_runs
    assert compact_date_runs([]) == []


def test_compact_date_runs_single_date():
    from bute.models import compact_date_runs
    assert compact_date_runs(["2026-01-05"]) == ["2026-01-05"]


def test_compact_date_runs_consecutive_streak():
    from bute.models import compact_date_runs
    dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    assert compact_date_runs(dates) == ["2026-01-01..2026-01-04"]


def test_compact_date_runs_gap_splits_runs():
    from bute.models import compact_date_runs
    dates = [
        "2026-01-01", "2026-01-02", "2026-01-03",  # run
        "2026-01-05", "2026-01-06",                # run after gap
        "2026-01-10",                              # isolated
    ]
    assert compact_date_runs(dates) == [
        "2026-01-01..2026-01-03",
        "2026-01-05..2026-01-06",
        "2026-01-10",
    ]


def test_compact_date_runs_unsorted_and_deduped():
    from bute.models import compact_date_runs
    dates = ["2026-01-03", "2026-01-01", "2026-01-02", "2026-01-02"]
    assert compact_date_runs(dates) == ["2026-01-01..2026-01-03"]


def test_expand_date_runs_accepts_legacy_flat_list():
    """Plain ISO-date entries (pre-RLE format) still load correctly."""
    from bute.models import expand_date_runs
    assert expand_date_runs(["2026-01-01", "2026-01-02"]) == ["2026-01-01", "2026-01-02"]


def test_expand_date_runs_range_form():
    from bute.models import expand_date_runs
    assert expand_date_runs(["2026-01-01..2026-01-03"]) == [
        "2026-01-01", "2026-01-02", "2026-01-03",
    ]


def test_expand_date_runs_mixed_form():
    from bute.models import expand_date_runs
    assert expand_date_runs(["2026-01-01..2026-01-02", "2026-01-10"]) == [
        "2026-01-01", "2026-01-02", "2026-01-10",
    ]


def test_rle_roundtrip_preserves_completions(tmp_data):
    """Save a streaky habit, reload, verify completions match."""
    from bute.models import Entry, EntryType
    from bute.storage import load_entry, entry_path_from_id, save_entry

    entry = Entry.create(entry_type=EntryType.TASK, body="meditate", repeat="daily")
    entry.completions = [
        "2026-01-01", "2026-01-02", "2026-01-03",  # run
        "2026-01-05",                              # isolated
        "2026-02-10", "2026-02-11",                # run
    ]
    save_entry(entry)

    reloaded = load_entry(entry_path_from_id(entry.id))
    assert reloaded.completions == [
        "2026-01-01", "2026-01-02", "2026-01-03",
        "2026-01-05",
        "2026-02-10", "2026-02-11",
    ]


def test_rle_saves_compact_form_on_disk(tmp_data):
    """Verify the on-disk YAML uses range form, not one-line-per-date."""
    import frontmatter
    from bute.models import Entry, EntryType
    from bute.storage import entry_path_from_id, save_entry

    entry = Entry.create(entry_type=EntryType.TASK, body="meditate", repeat="daily")
    entry.completions = [f"2026-01-{day:02d}" for day in range(1, 11)]  # 10 consecutive days
    save_entry(entry)

    raw = frontmatter.load(str(entry_path_from_id(entry.id)))
    assert raw.metadata["completions"] == ["2026-01-01..2026-01-10"]
