"""Tests for input parsing."""

from datetime import date

import pytest

from bute.errors import InvalidSignifierError
from bute.parser import parse_capture_tokens, resolve_date, resolve_time


class TestParseCapture:
    def test_basic_task(self):
        result = parse_capture_tokens(("/t", "call", "dentist"))
        assert result.signifier == "/t"
        assert result.important is False
        assert result.body == "call dentist"
        assert result.tags == []
        assert result.metadata == {}

    def test_important_task(self):
        result = parse_capture_tokens(("/t!", "fix", "prod", "bug"))
        assert result.signifier == "/t"
        assert result.important is True
        assert result.body == "fix prod bug"

    def test_note(self):
        result = parse_capture_tokens(("/n", "API", "uses", "OAuth2"))
        assert result.signifier == "/n"
        assert result.body == "API uses OAuth2"

    def test_journal(self):
        result = parse_capture_tokens(("/j", "feeling", "good", "today"))
        assert result.signifier == "/j"
        assert result.body == "feeling good today"

    def test_calendar(self):
        result = parse_capture_tokens(("/c", "team", "standup"))
        assert result.signifier == "/c"
        assert result.body == "team standup"

    def test_important_calendar(self):
        result = parse_capture_tokens(("/c!", "deadline"))
        assert result.signifier == "/c"
        assert result.important is True

    def test_tags(self):
        result = parse_capture_tokens(("/t", "fix", "bug", "@backend", "@urgent"))
        assert result.tags == ["backend", "urgent"]
        assert result.body == "fix bug"

    def test_key_value(self):
        result = parse_capture_tokens(("/t", "call", "dentist", "due:tomorrow"))
        assert result.metadata == {"due": "tomorrow"}
        assert result.body == "call dentist"

    def test_multiple_key_values(self):
        result = parse_capture_tokens(
            ("/c", "meeting", "time:2pm", "date:mar29")
        )
        assert result.metadata == {"time": "2pm", "date": "mar29"}
        assert result.body == "meeting"

    def test_mixed_input(self):
        result = parse_capture_tokens(
            ("/c!", "1:1", "with", "Ahmed", "time:2pm", "date:mar29", "@work")
        )
        assert result.signifier == "/c"
        assert result.important is True
        assert result.body == "1:1 with Ahmed"
        assert result.metadata == {"time": "2pm", "date": "mar29"}
        assert result.tags == ["work"]

    def test_colon_in_body_numeric_prefix(self):
        """1:1 should be treated as body text, not key:value."""
        result = parse_capture_tokens(("/c", "1:1", "with", "Ahmed"))
        assert result.body == "1:1 with Ahmed"
        assert result.metadata == {}

    def test_invalid_signifier(self):
        with pytest.raises(InvalidSignifierError):
            parse_capture_tokens(("/x", "test"))

    def test_empty_tokens(self):
        with pytest.raises(InvalidSignifierError):
            parse_capture_tokens(())

    def test_signifier_only(self):
        """Just /t with no body should work."""
        result = parse_capture_tokens(("/t",))
        assert result.signifier == "/t"
        assert result.body == ""

    def test_body_with_only_tags_and_metadata(self):
        result = parse_capture_tokens(("/t", "due:tomorrow", "@urgent"))
        assert result.body == ""
        assert result.metadata == {"due": "tomorrow"}
        assert result.tags == ["urgent"]


class TestPlusTokenAsBody:
    def test_plus_token_becomes_body_text(self):
        """After collection removal, +token should be treated as body text."""
        result = parse_capture_tokens(["/t", "fix", "faucet", "+home-reno"])
        assert "+home-reno" in result.body


class TestResolveDate:
    def test_today(self):
        ref = date(2026, 3, 23)
        assert resolve_date("today", ref) == date(2026, 3, 23)

    def test_tomorrow(self):
        ref = date(2026, 3, 23)
        assert resolve_date("tomorrow", ref) == date(2026, 3, 24)

    def test_day_of_week_future(self):
        ref = date(2026, 3, 23)  # Monday
        assert resolve_date("wednesday", ref) == date(2026, 3, 25)

    def test_day_of_week_same_day_goes_next_week(self):
        ref = date(2026, 3, 23)  # Monday
        assert resolve_date("monday", ref) == date(2026, 3, 30)

    def test_day_of_week_friday(self):
        ref = date(2026, 3, 23)  # Monday
        assert resolve_date("friday", ref) == date(2026, 3, 27)

    def test_month_day_future(self):
        ref = date(2026, 3, 23)
        assert resolve_date("mar29", ref) == date(2026, 3, 29)

    def test_month_day_past_rolls_to_next_year(self):
        ref = date(2026, 3, 23)
        assert resolve_date("jan15", ref) == date(2027, 1, 15)

    def test_month_day_with_hyphen(self):
        ref = date(2026, 3, 23)
        assert resolve_date("mar-29", ref) == date(2026, 3, 29)

    def test_slash_format(self):
        ref = date(2026, 3, 23)
        assert resolve_date("3/29", ref) == date(2026, 3, 29)

    def test_slash_format_past_rolls(self):
        ref = date(2026, 3, 23)
        assert resolve_date("1/15", ref) == date(2027, 1, 15)

    def test_iso_format(self):
        assert resolve_date("2026-04-15") == date(2026, 4, 15)

    def test_case_insensitive(self):
        ref = date(2026, 3, 23)
        assert resolve_date("TOMORROW", ref) == date(2026, 3, 24)
        assert resolve_date("Friday", ref) == date(2026, 3, 27)
        assert resolve_date("Mar29", ref) == date(2026, 3, 29)

    def test_next_day_with_hyphen(self):
        ref = date(2026, 3, 23)  # Monday
        # "monday" → Mar 30 (+7), "next-monday" → Apr 6 (+14)
        assert resolve_date("next-monday", ref) == date(2026, 4, 6)

    def test_next_day_no_separator(self):
        ref = date(2026, 3, 23)  # Monday
        assert resolve_date("nextmonday", ref) == date(2026, 4, 6)

    def test_next_day_with_dot(self):
        ref = date(2026, 3, 23)  # Monday
        assert resolve_date("next.monday", ref) == date(2026, 4, 6)

    def test_next_day_with_space(self):
        ref = date(2026, 3, 23)  # Monday
        assert resolve_date("next monday", ref) == date(2026, 4, 6)

    def test_next_day_abbrev(self):
        ref = date(2026, 3, 23)  # Monday
        assert resolve_date("next-mon", ref) == date(2026, 4, 6)

    def test_next_day_friday_from_monday(self):
        ref = date(2026, 3, 23)  # Monday
        # "friday" → Mar 27 (+4), "next-friday" → Apr 3 (+11)
        assert resolve_date("next-friday", ref) == date(2026, 4, 3)

    def test_next_day_case_insensitive(self):
        ref = date(2026, 3, 23)  # Monday
        assert resolve_date("Next-Friday", ref) == date(2026, 4, 3)

    def test_next_day_invalid_day(self):
        with pytest.raises(ValueError):
            resolve_date("next-foo")


class TestResolveTimeAmPmDot:
    def test_pm_with_dot(self):
        assert resolve_time("2.20pm") == "14:20"

    def test_am_with_dot(self):
        assert resolve_time("9.05am") == "09:05"

    def test_dot_with_space_before_period(self):
        assert resolve_time("2.20 pm") == "14:20"

    def test_dot_form_12pm_noon(self):
        assert resolve_time("12.00pm") == "12:00"

    def test_dot_form_12am_midnight(self):
        assert resolve_time("12.30am") == "00:30"

    def test_dot_form_invalid_hour(self):
        with pytest.raises(ValueError):
            resolve_time("13.20pm")

    def test_dot_form_invalid_minutes(self):
        with pytest.raises(ValueError):
            resolve_time("2.99pm")


class TestResolveTimeInvalid:
    def test_resolve_time_invalid_ampm(self):
        """am/pm with hour > 12 should raise."""
        with pytest.raises(ValueError):
            resolve_time("13pm")

    def test_resolve_time_invalid_minutes(self):
        """Minutes >= 60 should raise."""
        with pytest.raises(ValueError):
            resolve_time("1.60")

    def test_resolve_time_invalid_hour(self):
        """Hour >= 24 in HH:MM should raise."""
        with pytest.raises(ValueError):
            resolve_time("25:30")

    def test_resolve_time_invalid_99pm(self):
        """99pm should raise."""
        with pytest.raises(ValueError):
            resolve_time("99pm")

    def test_resolve_time_unrecognized_format(self):
        """Completely unrecognized input should raise."""
        with pytest.raises(ValueError):
            resolve_time("noon")


class TestResolveDateInvalid:
    def test_resolve_date_invalid_month(self):
        """Month 13 should raise."""
        with pytest.raises(ValueError):
            resolve_date("13.45")

    def test_resolve_date_invalid_day(self):
        """Feb 30 should raise."""
        with pytest.raises(ValueError):
            resolve_date("2.30")

    def test_resolve_date_invalid_month_day(self):
        """mar32 should raise."""
        with pytest.raises(ValueError):
            resolve_date("mar32")

    def test_resolve_date_invalid_iso(self):
        """Garbage ISO string should raise with clear message."""
        with pytest.raises(ValueError, match="Invalid date"):
            resolve_date("not-a-date")
