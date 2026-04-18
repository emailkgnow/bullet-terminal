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
