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
