"""Tests for YAML habit storage."""

from datetime import date

from bute.habit_storage import get_habit_summary, load_habits_for_date, save_habit


def test_save_and_load(tmp_data):
    target = date(2026, 3, 23)
    save_habit("quran", True, target)
    habits = load_habits_for_date(target)
    assert habits["quran"] is True


def test_save_not_done(tmp_data):
    target = date(2026, 3, 23)
    save_habit("walking", False, target)
    habits = load_habits_for_date(target)
    assert habits["walking"] is False


def test_load_empty(tmp_data):
    habits = load_habits_for_date(date(2026, 3, 23))
    assert habits == {}


def test_multiple_habits_same_day(tmp_data):
    target = date(2026, 3, 23)
    save_habit("quran", True, target)
    save_habit("walking", False, target)
    save_habit("reading", True, target)
    habits = load_habits_for_date(target)
    assert habits == {"quran": True, "walking": False, "reading": True}


def test_multiple_days(tmp_data):
    save_habit("quran", True, date(2026, 3, 23))
    save_habit("quran", False, date(2026, 3, 24))
    assert load_habits_for_date(date(2026, 3, 23))["quran"] is True
    assert load_habits_for_date(date(2026, 3, 24))["quran"] is False


def test_overwrite_habit(tmp_data):
    target = date(2026, 3, 23)
    save_habit("quran", True, target)
    save_habit("quran", False, target)
    assert load_habits_for_date(target)["quran"] is False


def test_get_habit_summary(tmp_data):
    target = date(2026, 3, 23)
    save_habit("quran", True, target)
    summary = get_habit_summary(target, ["quran", "walking", "reading"])
    assert summary == {"quran": True, "walking": None, "reading": None}


def test_get_habit_summary_empty(tmp_data):
    summary = get_habit_summary(date(2026, 3, 23), ["quran", "walking"])
    assert summary == {"quran": None, "walking": None}
