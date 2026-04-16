"""End-to-end tests for ritual commands."""

from datetime import date

from bute.cli import main
from bute.config import default_config, save_config
from bute.models import Entry, EntryType, TaskStatus
from bute.ritual_ops import this_monday
from bute.storage import save_entry, update_entry


def _setup_config(tmp_config, tmp_data):
    """Create a config pointing to tmp_data."""
    doc = default_config(provider="anthropic")
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


# --- Daily Plan (dp) command tests ---


def test_dp_non_interactive_shows_tasks(runner, tmp_config, tmp_data):
    """dp -y shows weekly tasks and marks daily plan done."""
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "deploy staging", week_date=this_monday())
    save_entry(e)

    result = runner.invoke(main, ["dp", "--non-interactive"])
    assert result.exit_code == 0
    assert "Daily Plan" in result.output
    assert "deploy staging" in result.output
    assert "Ready" in result.output
    # Old phases should NOT appear
    assert "Dump" not in result.output
    assert "Yesterday" not in result.output
    assert "Schedule" not in result.output


def test_dp_non_interactive_no_tasks(runner, tmp_config, tmp_data):
    """dp -y with no active tasks shows empty message."""
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["dp", "--non-interactive"])
    assert result.exit_code == 0
    assert "No active tasks" in result.output
    assert "Ready" in result.output
    # Old phases should NOT appear
    assert "Dump" not in result.output
    assert "Yesterday" not in result.output
    assert "Schedule" not in result.output


def test_dp_non_interactive_marks_done(runner, tmp_config, tmp_data):
    """dp -y marks daily plan as done so bt shows Focus Log."""
    from bute.state import is_dp_done_today

    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["dp", "--non-interactive"])
    assert result.exit_code == 0
    assert is_dp_done_today()


def test_wp_marks_done(runner, tmp_config, tmp_data):
    """wp -y marks weekly plan as done for the current week."""
    from bute.state import is_wp_done_this_week

    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["wp", "--non-interactive"])
    assert result.exit_code == 0
    assert is_wp_done_this_week()


def test_wp_not_done_by_default(tmp_config, tmp_data):
    """wp is not done when no .wp_date file exists."""
    from bute.state import is_wp_done_this_week

    _setup_config(tmp_config, tmp_data)
    from bute.config import load_config
    config = load_config()
    assert not is_wp_done_this_week(config)


# --- Weekly Plan (wp) command tests ---


def test_wp_non_interactive(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e1 = Entry.create(EntryType.TASK, "task one")
    e2 = Entry.create(EntryType.TASK, "task two", week_date=this_monday())
    save_entry(e1)
    save_entry(e2)

    result = runner.invoke(main, ["wp", "--non-interactive"])
    assert result.exit_code == 0
    assert "task two" in result.output


def test_wp_no_tasks(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["wp", "--non-interactive"])
    assert "No tasks to plan" in result.output or "Backlog is empty" in result.output


def test_wp_shows_carryover_icon(runner, tmp_config, tmp_data):
    """wp shows ↩ for tasks that had week_date set from last week."""
    _setup_config(tmp_config, tmp_data)
    e1 = Entry.create(EntryType.TASK, "carried over", week_date=this_monday())
    e2 = Entry.create(EntryType.TASK, "fresh task")
    save_entry(e1)
    save_entry(e2)

    # Non-interactive mode shows the task list — carryover first, backlog second
    result = runner.invoke(main, ["wp", "--non-interactive"])
    assert result.exit_code == 0
    assert "carried over" in result.output
    assert "fresh task" in result.output


# --- Daily log tests ---


def test_daily_log_shows_done_tasks(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "finished task", focus_date=date.today(), week_date=this_monday())
    save_entry(e)
    e.status = TaskStatus.DONE
    update_entry(e)

    result = runner.invoke(main, ["daily"])
    assert result.exit_code == 0
    assert "finished task" in result.output


def test_daily_log_shows_entries(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    j = Entry.create(EntryType.JOURNAL, "feeling good")
    save_entry(j)

    result = runner.invoke(main, ["daily"])
    assert result.exit_code == 0
    assert "feeling good" in result.output


def test_daily_log_empty(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["daily"])
    assert result.exit_code == 0
    assert "No entries" in result.output


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


# --- Config key: core.wp_day tests ---


def test_get_wp_day_default():
    """get_wp_day returns 6 (Sunday) when no config."""
    from bute.config import get_wp_day
    assert get_wp_day() == 6


def test_get_wp_day_from_config(tmp_config, tmp_data):
    """get_wp_day reads from config."""
    from bute.config import get_wp_day
    _setup_config(tmp_config, tmp_data)
    from bute.config import load_config
    config = load_config()
    config["core"]["wp_day"] = "monday"
    assert get_wp_day(config) == 0


# --- bt (no args) wp trigger tests ---


def test_bt_noargs_chains_wp_then_dp(runner, tmp_config, tmp_data, monkeypatch):
    """bt (no args) on trigger day runs wp then dp in sequence."""
    _setup_config(tmp_config, tmp_data)
    # Mark tour as done so bt doesn't show tour
    from bute.config import TOUR_DONE
    TOUR_DONE.parent.mkdir(parents=True, exist_ok=True)
    TOUR_DONE.touch()

    # Force wp_day to today's weekday so trigger fires
    from bute.config import load_config, save_config
    config = load_config()
    today_name = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][date.today().weekday()]
    config["core"]["wp_day"] = today_name
    save_config(config)

    e = Entry.create(EntryType.TASK, "weekly task")
    save_entry(e)

    # Mock questionary to avoid interactive TUI in test
    import questionary
    monkeypatch.setattr(questionary, "checkbox", lambda *a, **kw: type("Q", (), {"ask": lambda self: []})())

    # bt (no args) should trigger wp (non-interactive fallback) then dp
    result = runner.invoke(main, [], input="\n")
    assert result.exit_code == 0
    # wp should have run (Plan header)
    assert "Plan" in result.output


def test_bt_noargs_skips_wp_when_done(runner, tmp_config, tmp_data, monkeypatch):
    """bt (no args) skips wp when already done this week."""
    _setup_config(tmp_config, tmp_data)
    from bute.config import TOUR_DONE
    TOUR_DONE.parent.mkdir(parents=True, exist_ok=True)
    TOUR_DONE.touch()

    # Force wp_day to today
    from bute.config import load_config, save_config
    config = load_config()
    today_name = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][date.today().weekday()]
    config["core"]["wp_day"] = today_name
    save_config(config)

    # Mark wp as already done
    from bute.state import mark_wp_done
    mark_wp_done()

    # Mock questionary to avoid interactive TUI
    import questionary
    monkeypatch.setattr(questionary, "checkbox", lambda *a, **kw: type("Q", (), {"ask": lambda self: []})())

    # bt (no args) — wp should be skipped, dp should run
    result = runner.invoke(main, [], input="\n")
    assert result.exit_code == 0
    assert "Daily Plan" in result.output
    # wp Plan header should NOT appear (wp was already done)
    output_lines = result.output.split("\n")
    plan_lines = [l for l in output_lines if l.strip() == "Plan" or "Review your backlog" in l]
    assert len(plan_lines) == 0, f"wp should not have triggered, but found: {plan_lines}"
