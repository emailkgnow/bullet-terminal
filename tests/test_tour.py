"""Tests for the guided tour."""

from bute.commands.tour import (
    is_tour_done,
    mark_tour_done,
    load_tour_progress,
    save_tour_progress,
    PHASES,
    Phase,
    Step,
)


def test_tour_not_done_initially(tmp_config):
    assert is_tour_done() is False


def test_mark_tour_done(tmp_config):
    mark_tour_done()
    assert is_tour_done() is True


def test_tour_progress_default(tmp_config):
    assert load_tour_progress() == 0


def test_save_and_load_progress(tmp_config):
    save_tour_progress(5)
    assert load_tour_progress() == 5


def test_mark_done_clears_progress(tmp_config):
    save_tour_progress(7)
    mark_tour_done()
    assert load_tour_progress() == 0


def test_phases_exist():
    assert len(PHASES) == 11


def test_phase_has_intro_and_steps():
    phase = PHASES[0]
    assert isinstance(phase, Phase)
    assert phase.name == "Tasks"
    assert len(phase.intro) > 0
    assert len(phase.steps) >= 1


def test_step_has_required_fields():
    step = PHASES[0].steps[0]
    assert isinstance(step, Step)
    assert len(step.prompt) > 0
    assert step.validate is not None
    assert len(step.feedback) > 0


# ---------------------------------------------------------------------------
# REPL / integration tests
# ---------------------------------------------------------------------------

from click.testing import CliRunner
from bute.cli import main


def test_tour_runs_on_empty_system(runner, tmp_config, tmp_data):
    """Tour triggers when no entries exist and tour not done."""
    result = runner.invoke(main, [], input="/done\n")
    assert result.exit_code == 0
    assert "Tasks" in result.output  # Phase 1 intro


def test_tour_skips_when_done(runner, tmp_config, tmp_data):
    """Tour does not trigger when .tour_done marker exists."""
    mark_tour_done()
    result = runner.invoke(main, [], input="")
    assert "Tasks are things" not in result.output


def test_tour_phase1_capture(runner, tmp_config, tmp_data):
    """Capturing a task in phase 1 advances the step."""
    result = runner.invoke(main, [], input="t call dentist\n/done\n")
    assert result.exit_code == 0
    assert "dot means" in result.output  # Phase 1 Step A feedback


def test_tour_skip_command(runner, tmp_config, tmp_data):
    """User can /skip to advance to next phase."""
    result = runner.invoke(main, [], input="/skip\n/done\n")
    assert result.exit_code == 0
    # Should have shown Phase 1 intro, then Phase 2 intro after /skip
    assert "Notes" in result.output


def test_tour_outro_shown(runner, tmp_config, tmp_data):
    """Completing all phases shows the outro."""
    # Skip through all 11 phases
    skip_all = "/skip\n" * 11
    result = runner.invoke(main, [], input=skip_all)
    assert result.exit_code == 0
    assert "bt start" in result.output  # Outro mentions cheat sheet
    assert "bt -h" in result.output
