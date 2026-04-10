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
