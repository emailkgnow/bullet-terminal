"""End-to-end tests for ritual commands."""

from datetime import date

from bute.cli import main
from bute.config import default_config, save_config
from bute.habit_storage import load_habits_for_date
from bute.models import Entry, EntryType, TaskStatus
from bute.storage import entry_path_from_id, load_entries_by_filter, load_entry, save_entry, update_entry


def _setup_config(tmp_config, tmp_data):
    """Create a config with habits, pointing to tmp_data."""
    doc = default_config(provider="ollama")
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


# --- Habit command tests ---


def test_habit_show_status(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["habit"])
    assert result.exit_code == 0
    assert "quran" in result.output
    assert "walking" in result.output


def test_habit_log_done(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["habit", "quran"])
    assert result.exit_code == 0
    assert "quran" in result.output

    habits = load_habits_for_date(date.today())
    assert habits["quran"] is True


def test_habit_log_not_done(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["habit", "walking", "--no"])
    assert result.exit_code == 0

    habits = load_habits_for_date(date.today())
    assert habits["walking"] is False


def test_habit_invalid_name(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["habit", "nonexistent"])
    assert result.exit_code == 1
    assert "not a configured habit" in result.output


# --- DYTS command tests ---


def test_dyts_non_interactive(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    # Create an active task so T phase has something
    e = Entry.create(EntryType.TASK, "test task")
    save_entry(e)

    result = runner.invoke(main, ["dyts", "--non-interactive"])
    assert result.exit_code == 0
    assert "Dump" in result.output
    assert "Yesterday" in result.output
    assert "Tasks" in result.output
    assert "Schedule" in result.output
    assert "Ready" in result.output


def test_dyts_shows_schedule(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.CALENDAR, "standup", scheduled_time="10am")
    save_entry(e)

    result = runner.invoke(main, ["dyts", "--non-interactive"])
    assert "standup" in result.output


# --- Migrate command tests ---


def test_migrate_non_interactive(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "unfinished task")
    save_entry(e)

    result = runner.invoke(main, ["migrate", "--non-interactive"])
    assert result.exit_code == 0
    assert "migrate tomorrow" in result.output
    assert "Migration complete" in result.output

    # Original should be migrated
    loaded = load_entry(entry_path_from_id(e.id))
    assert loaded.status == TaskStatus.MIGRATED


def test_migrate_empty(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["migrate", "--non-interactive"])
    assert "Nothing to migrate" in result.output


def test_migrate_creates_tomorrow_entry(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "carry this", tags=["backend"])
    save_entry(e)

    runner.invoke(main, ["migrate", "--non-interactive"])

    # Should have a new active entry
    new_entries = load_entries_by_filter(
        lambda x: x.body == "carry this" and x.status == TaskStatus.ACTIVE
    )
    assert len(new_entries) == 1
    assert "backend" in new_entries[0].tags


# --- Plan command tests ---


def test_plan_non_interactive(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.TASK, "task two", tags=["thisweek"])
    save_entry(e1)
    save_entry(e2)

    result = runner.invoke(main, ["plan", "--non-interactive"])
    assert result.exit_code == 0
    assert "task two" in result.output  # thisweek task shown


def test_plan_no_tasks(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["plan", "--non-interactive"])
    assert "No active tasks" in result.output


# --- Recap command tests ---


def test_recap_shows_done_tasks(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "finished task", tags=["today"])
    save_entry(e)
    e.status = TaskStatus.DONE
    update_entry(e)

    result = runner.invoke(main, ["recap"])
    assert result.exit_code == 0
    assert "finished task" in result.output
    assert "Done" in result.output


def test_recap_shows_open_tasks(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "still going", tags=["today"])
    save_entry(e)

    result = runner.invoke(main, ["recap"])
    assert result.exit_code == 0
    assert "still going" in result.output
    assert "Open" in result.output


def test_recap_shows_captured(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    j = Entry.create(EntryType.JOURNAL, "feeling good")
    save_entry(j)

    result = runner.invoke(main, ["recap"])
    assert result.exit_code == 0
    assert "feeling good" in result.output


def test_recap_empty_day(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["recap"])
    assert result.exit_code == 0
    assert "Nothing to recap" in result.output


def test_recap_marks_done(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    j = Entry.create(EntryType.JOURNAL, "a thought")
    save_entry(j)

    runner.invoke(main, ["recap"])

    from bute.state import is_recap_done_today
    assert is_recap_done_today()


def test_recap_period_no_ai(runner, tmp_config, tmp_data):
    """bt recap week without AI available shows install message."""
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["recap", "week"])
    assert result.exit_code == 0
    assert "AI" in result.output or "No entries" in result.output


def test_recap_invalid_period(runner, tmp_config, tmp_data):
    """bt recap with unknown period shows error."""
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["recap", "quarter"])
    assert result.exit_code == 0
    assert "Unknown period" in result.output


# --- Streak command tests ---


def test_streak_shows_habits(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)

    from datetime import date
    from bute.habit_storage import save_habit
    save_habit("quran", True, date(2026, 3, 29))
    save_habit("walking", False, date(2026, 3, 29))

    result = runner.invoke(main, ["streak"])
    assert result.exit_code == 0
    assert "quran" in result.output
    assert "walking" in result.output
    assert "streak" in result.output.lower()


def test_streak_no_habits_configured(runner, tmp_config, tmp_data):
    """Streak with no habits configured shows message."""
    from bute.config import default_config, save_config
    doc = default_config(provider="ollama")
    doc["core"]["data_dir"] = str(tmp_data)
    if "habits" in doc:
        del doc["habits"]
    save_config(doc)

    result = runner.invoke(main, ["streak"])
    assert result.exit_code == 0
    assert "No habits configured" in result.output
