"""Tests for input parsing."""

from datetime import date

import pytest

from bute.errors import InvalidSignifierError
from bute.parser import parse_capture_tokens, resolve_date


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


class TestParseCollection:
    def test_parse_collection_token(self):
        result = parse_capture_tokens(["t", "fix", "faucet", "+home-reno"])
        assert result.collection == "home-reno"
        assert result.body == "fix faucet"
        assert result.signifier == "/t"

    def test_parse_collection_with_tags(self):
        result = parse_capture_tokens(["t", "fix", "faucet", "+home-reno", "@plumbing"])
        assert result.collection == "home-reno"
        assert result.tags == ["plumbing"]
        assert result.body == "fix faucet"

    def test_parse_collection_with_metadata(self):
        result = parse_capture_tokens(["t", "fix", "faucet", "+home-reno", "due:friday"])
        assert result.collection == "home-reno"
        assert result.metadata == {"due": "friday"}
        assert result.body == "fix faucet"

    def test_parse_no_collection(self):
        result = parse_capture_tokens(["t", "fix", "faucet"])
        assert result.collection is None

    def test_parse_multiple_collections_first_wins(self):
        result = parse_capture_tokens(["t", "fix", "+alpha", "+beta"])
        assert result.collection == "alpha"


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
