"""Tests for the first-run onboarding tour."""

from datetime import date

import pytest
from click.testing import CliRunner

from bute.cli import main
from bute.commands.tour import (
    _has_entries,
    is_tour_done,
    mark_tour_done,
    should_run_tour,
)
from bute.models import Entry, EntryType
from bute.storage import save_entry


# ---------------------------------------------------------------------------
# Marker helpers
# ---------------------------------------------------------------------------


def test_tour_not_done_initially(tmp_config):
    assert is_tour_done() is False


def test_mark_tour_done(tmp_config):
    mark_tour_done()
    assert is_tour_done() is True


# ---------------------------------------------------------------------------
# Trigger logic
# ---------------------------------------------------------------------------


def test_should_run_when_empty_and_not_done(tmp_config, tmp_data):
    assert should_run_tour(None) is True


def test_should_skip_when_done(tmp_config, tmp_data):
    mark_tour_done()
    assert should_run_tour(None) is False


def test_should_skip_when_entries_exist(tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "existing task")
    save_entry(e)
    assert _has_entries(None) is True
    assert should_run_tour(None) is False


# ---------------------------------------------------------------------------
# Integration via main()
# ---------------------------------------------------------------------------


@pytest.fixture
def _mock_questionary(monkeypatch):
    """Mock questionary.checkbox to avoid TUI in tests (returns no selection)."""
    import questionary
    monkeypatch.setattr(
        questionary,
        "checkbox",
        lambda *a, **kw: type("Q", (), {"ask": lambda self: []})(),
    )


def test_tour_runs_on_empty_system(runner, tmp_config, tmp_data, _mock_questionary):
    """First `bt` on empty system shows the welcome panel."""
    # Blank line ends wp dump phase; questionary mocked above.
    result = runner.invoke(main, [], input="\n")
    assert result.exit_code == 0
    assert "Welcome to bt" in result.output


def test_tour_skips_when_done(runner, tmp_config, tmp_data):
    """Tour does not trigger when .tour_done marker exists."""
    mark_tour_done()
    result = runner.invoke(main, [], input="")
    assert "Welcome to bt" not in result.output


def test_tour_skips_when_entries_exist(runner, tmp_config, tmp_data):
    """Tour does not trigger if entries already exist on disk."""
    e = Entry.create(EntryType.TASK, "pre-existing task")
    save_entry(e)
    result = runner.invoke(main, [], input="")
    assert "Welcome to bt" not in result.output


def test_tour_marks_done_after_completion(runner, tmp_config, tmp_data, _mock_questionary):
    """Completing the tour writes the .tour_done marker."""
    assert is_tour_done() is False
    runner.invoke(main, [], input="\n")
    assert is_tour_done() is True


def test_tour_runs_wp_then_dp(runner, tmp_config, tmp_data, _mock_questionary):
    """The flow invokes wp (Plan header) and dp (Daily Plan header)."""
    result = runner.invoke(main, [], input="\n")
    assert result.exit_code == 0
    assert "Plan" in result.output
    assert "Daily Plan" in result.output


def test_tour_outro_points_to_focus_log(runner, tmp_config, tmp_data, _mock_questionary):
    """Outro points the user to `bt` and `bt -h`."""
    result = runner.invoke(main, [], input="\n")
    assert result.exit_code == 0
    assert "bt -h" in result.output
    assert "Focus Log" in result.output


def test_tour_brain_dump_creates_tasks(runner, tmp_config, tmp_data, _mock_questionary):
    """Tasks typed during the welcome dump phase get saved."""
    # wp dump phase reads lines until blank; first line becomes a task.
    result = runner.invoke(main, [], input="call dentist\n\n")
    assert result.exit_code == 0
    from bute.storage import load_entries_by_filter
    entries = load_entries_by_filter(lambda e: True)
    bodies = [e.body for e in entries]
    assert any("call dentist" in b for b in bodies)
