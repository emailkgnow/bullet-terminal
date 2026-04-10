"""Tests for bt stats — momentum dashboard."""

from datetime import date, timedelta

import pytest


def test_mark_dp_done_appends_history(tmp_data):
    """mark_dp_done should append today's date to .dp_history."""
    from bute.state import mark_dp_done, get_dp_history

    mark_dp_done()
    history = get_dp_history()
    assert date.today() in history


def test_dp_history_no_duplicates(tmp_data):
    """Calling mark_dp_done twice on same day should not duplicate."""
    from bute.state import mark_dp_done, get_dp_history

    mark_dp_done()
    mark_dp_done()
    history_path = tmp_data / ".dp_history"
    lines = history_path.read_text().strip().splitlines()
    assert len(lines) == 1


from bute.models import Entry, EntryType, TaskStatus
from bute.storage import save_entry


def _index(entry):
    from bute.db import upsert_entry
    upsert_entry(entry)


def test_get_done_per_day(tmp_data, tmp_config):
    """Count tasks done per day using file mtime."""
    e1 = Entry.create(EntryType.TASK, "task one")
    e1.status = TaskStatus.DONE
    save_entry(e1)
    _index(e1)

    e2 = Entry.create(EntryType.TASK, "task two")
    e2.status = TaskStatus.DONE
    save_entry(e2)
    _index(e2)

    from bute.commands.stats import get_done_per_day

    today = date.today()
    result = get_done_per_day(None, today - timedelta(days=7), today)
    assert result[today] == 2


def test_task_streak_consecutive(tmp_data):
    """Streak of 3 consecutive days."""
    from bute.commands.stats import calc_task_streak

    today = date.today()
    done_per_day = {
        today: 1,
        today - timedelta(days=1): 2,
        today - timedelta(days=2): 1,
    }
    assert calc_task_streak(done_per_day, today) == 3


def test_task_streak_gap_breaks(tmp_data):
    """A gap in days breaks the streak."""
    from bute.commands.stats import calc_task_streak

    today = date.today()
    done_per_day = {
        today: 1,
        # gap at today - 1
        today - timedelta(days=2): 1,
    }
    assert calc_task_streak(done_per_day, today) == 1


def test_task_streak_zero_today(tmp_data):
    """No tasks done today means streak is 0."""
    from bute.commands.stats import calc_task_streak

    today = date.today()
    done_per_day = {
        today - timedelta(days=1): 1,
    }
    assert calc_task_streak(done_per_day, today) == 0


def test_dp_streak_consecutive(tmp_data):
    """DP streak counts consecutive days from history."""
    from bute.commands.stats import calc_dp_streak
    from bute.config import get_data_dir

    today = date.today()
    history_path = get_data_dir() / ".dp_history"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        (today - timedelta(days=2)).isoformat(),
        (today - timedelta(days=1)).isoformat(),
        today.isoformat(),
    ]
    history_path.write_text("\n".join(lines) + "\n")

    assert calc_dp_streak(None, today) == 3


def test_dp_streak_zero_today(tmp_data):
    """No dp done today means dp streak is 0."""
    from bute.commands.stats import calc_dp_streak
    from bute.config import get_data_dir

    today = date.today()
    history_path = get_data_dir() / ".dp_history"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text((today - timedelta(days=1)).isoformat() + "\n")

    assert calc_dp_streak(None, today) == 0


def test_build_closure_chart_basic():
    """Chart should produce day labels and bar characters."""
    from bute.commands.stats import build_closure_chart

    today = date(2026, 4, 10)  # Thursday
    days = [today - timedelta(days=6 - i) for i in range(7)]
    done_per_day = {
        days[0]: 2,
        days[2]: 4,
        days[4]: 1,
    }
    labels, counts_row, bars = build_closure_chart(done_per_day, days)
    assert len(labels) == 7
    assert len(bars) == 7
    # Day with 0 done should show dot
    assert counts_row[1] == "·"
    # Day with max (4) should show tallest bar
    assert bars[2] == "█"


def test_build_closure_chart_all_zero():
    """All-zero days should produce all dots and no bars."""
    from bute.commands.stats import build_closure_chart

    today = date(2026, 4, 10)
    days = [today - timedelta(days=2 - i) for i in range(3)]
    labels, counts_row, bars = build_closure_chart({}, days)
    assert counts_row == ["·", "·", "·"]
    assert bars == [" ", " ", " "]


def test_get_period_ranges_default():
    """Default view: this/last week and this/last month ranges."""
    from bute.commands.stats import get_period_ranges

    today = date(2026, 4, 10)  # Friday
    ranges = get_period_ranges("default", today)

    # This week starts Monday Apr 6
    assert ranges["this_week"] == (date(2026, 4, 6), today)
    # Last week Mon Mar 30 - Sun Apr 5
    assert ranges["last_week"] == (date(2026, 3, 30), date(2026, 4, 5))
    # This month starts Apr 1
    assert ranges["this_month"] == (date(2026, 4, 1), today)
    # Last month is full March
    assert ranges["last_month"] == (date(2026, 3, 1), date(2026, 3, 31))


def test_get_period_ranges_month():
    """Month view: rolling 30-day windows."""
    from bute.commands.stats import get_period_ranges

    today = date(2026, 4, 10)
    ranges = get_period_ranges("month", today)

    assert ranges["this_period"] == (date(2026, 3, 12), today)
    assert ranges["last_period"] == (date(2026, 2, 10), date(2026, 3, 11))


def test_render_stats_default_empty(tmp_data, tmp_config, capsys):
    """Stats with no data should still render without errors."""
    from bute.commands.stats import render_stats

    render_stats("default", None)
    captured = capsys.readouterr()
    assert "Momentum" in captured.out
    assert "Task Streak" in captured.out
    assert "Plan Streak" in captured.out


from click.testing import CliRunner
from bute.cli import main


def test_stats_cli_default(runner, tmp_config, tmp_data):
    """bt stats should render without errors."""
    result = runner.invoke(main, ["stats"])
    assert result.exit_code == 0
    assert "Momentum" in result.output


def test_stats_cli_week(runner, tmp_config, tmp_data):
    """bt stats week should render without errors."""
    result = runner.invoke(main, ["stats", "week"])
    assert result.exit_code == 0
    assert "Momentum" in result.output


def test_stats_cli_month(runner, tmp_config, tmp_data):
    """bt stats month should render without errors."""
    result = runner.invoke(main, ["stats", "month"])
    assert result.exit_code == 0
    assert "Momentum" in result.output
