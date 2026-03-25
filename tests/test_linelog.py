"""Tests for line log storage."""

from datetime import date

from bute.linelog import append_line, load_month


def test_append_and_load(tmp_data):
    target = date(2026, 3, 23)
    append_line("good day, productive", target)
    content = load_month(target)
    assert "23  good day, productive" in content


def test_append_multiple_days(tmp_data):
    append_line("day one", date(2026, 3, 1))
    append_line("day two", date(2026, 3, 2))
    content = load_month(date(2026, 3, 1))
    assert " 1  day one" in content
    assert " 2  day two" in content


def test_load_empty(tmp_data):
    assert load_month(date(2026, 3, 1)) == ""
