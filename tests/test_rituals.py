"""End-to-end tests for ritual commands."""

from datetime import date

from bute.cli import main
from bute.config import default_config, save_config
from bute.models import Entry, EntryType, TaskStatus
from bute.storage import entry_path_from_id, load_entry, save_entry, update_entry


def _setup_config(tmp_config, tmp_data):
    """Create a config pointing to tmp_data."""
    doc = default_config(provider="ollama")
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


# --- Daily Plan (dp) command tests ---


def test_dp_non_interactive(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "test task", tags=["thisweek"])
    save_entry(e)

    result = runner.invoke(main, ["dp", "--non-interactive"])
    assert result.exit_code == 0
    assert "Dump" in result.output
    assert "Yesterday" in result.output
    assert "Tasks" in result.output
    assert "Schedule" in result.output
    assert "Ready" in result.output


def test_dp_shows_schedule(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.CALENDAR, "standup", scheduled_time="10:00")
    save_entry(e)

    result = runner.invoke(main, ["dp", "--non-interactive"])
    assert "standup" in result.output


# --- Weekly Plan (wp) command tests ---


def test_wp_non_interactive(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.TASK, "task two", tags=["thisweek"])
    save_entry(e1)
    save_entry(e2)

    result = runner.invoke(main, ["wp", "--non-interactive"])
    assert result.exit_code == 0
    assert "task two" in result.output


def test_wp_no_tasks(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["wp", "--non-interactive"])
    assert "No tasks to plan" in result.output or "Backlog is empty" in result.output


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
    # Create habit entries
    h1 = Entry.create(EntryType.TASK, "quran", tags=["habit"], repeat="daily")
    h2 = Entry.create(EntryType.TASK, "walking", tags=["habit"], repeat="daily")
    save_entry(h1)
    save_entry(h2)

    result = runner.invoke(main, ["streak"])
    assert result.exit_code == 0
    assert "quran" in result.output
    assert "walking" in result.output


def test_streak_no_habits(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["streak"])
    assert result.exit_code == 0
    assert "No habits" in result.output or "no habits" in result.output.lower()
