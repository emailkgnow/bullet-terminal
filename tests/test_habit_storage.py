"""Tests for YAML habit storage."""

from datetime import date, timedelta

from bute.habit_storage import get_habit_history, get_habit_summary, load_habits_for_date, save_habit


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


def test_get_habit_history_basic(tmp_data):
    """Returns history for configured habits over date range."""
    save_habit("quran", True, date(2026, 3, 28))
    save_habit("quran", False, date(2026, 3, 29))
    save_habit("walking", True, date(2026, 3, 28))

    history = get_habit_history(7, ["quran", "walking"], target_date=date(2026, 3, 30))
    assert history["quran"][date(2026, 3, 28)] is True
    assert history["quran"][date(2026, 3, 29)] is False
    assert history["quran"][date(2026, 3, 30)] is None
    assert history["walking"][date(2026, 3, 28)] is True
    assert history["walking"][date(2026, 3, 25)] is None


def test_get_habit_history_cross_month(tmp_data):
    """History spans across month boundaries."""
    save_habit("quran", True, date(2026, 2, 27))
    save_habit("quran", True, date(2026, 3, 1))

    history = get_habit_history(7, ["quran"], target_date=date(2026, 3, 3))
    assert history["quran"][date(2026, 2, 27)] is True
    assert history["quran"][date(2026, 2, 28)] is None
    assert history["quran"][date(2026, 3, 1)] is True


def test_get_habit_history_empty(tmp_data):
    """No data at all returns all None."""
    history = get_habit_history(7, ["quran"], target_date=date(2026, 3, 30))
    assert all(v is None for v in history["quran"].values())
    assert len(history["quran"]) == 7


# --- compute_streak tests ---

from bute.habit_storage import compute_streak


def test_compute_streak_consecutive(tmp_data):
    """Streak counts consecutive true days backwards from yesterday."""
    save_habit("quran", True, date(2026, 3, 27))
    save_habit("quran", True, date(2026, 3, 28))
    save_habit("quran", True, date(2026, 3, 29))

    history = get_habit_history(30, ["quran"], target_date=date(2026, 3, 30))
    assert compute_streak(history, "quran", target_date=date(2026, 3, 30)) == 3


def test_compute_streak_broken(tmp_data):
    """Streak resets when a day is missed."""
    save_habit("quran", True, date(2026, 3, 27))
    save_habit("quran", False, date(2026, 3, 28))
    save_habit("quran", True, date(2026, 3, 29))

    history = get_habit_history(30, ["quran"], target_date=date(2026, 3, 30))
    assert compute_streak(history, "quran", target_date=date(2026, 3, 30)) == 1


def test_compute_streak_zero(tmp_data):
    """Streak is 0 if yesterday was not done."""
    save_habit("quran", True, date(2026, 3, 27))
    save_habit("quran", False, date(2026, 3, 29))

    history = get_habit_history(30, ["quran"], target_date=date(2026, 3, 30))
    assert compute_streak(history, "quran", target_date=date(2026, 3, 30)) == 0


def test_compute_streak_no_data(tmp_data):
    """Streak is 0 with no history."""
    history = get_habit_history(30, ["quran"], target_date=date(2026, 3, 30))
    assert compute_streak(history, "quran", target_date=date(2026, 3, 30)) == 0
