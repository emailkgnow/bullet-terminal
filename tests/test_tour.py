"""Tests for the guided tour."""

from bute.commands.tour import (
    is_tour_done,
    mark_tour_done,
    load_tour_progress,
    save_tour_progress,
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
