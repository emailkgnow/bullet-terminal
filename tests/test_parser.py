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
        assert resolve_date("mar-29", ref) == date(2026, 3, 29)

    def test_month_day_past_rolls_to_next_year(self):
        ref = date(2026, 3, 23)
        assert resolve_date("jan-15", ref) == date(2027, 1, 15)

    def test_month_day_with_hyphen(self):
        ref = date(2026, 3, 23)
        assert resolve_date("mar-29", ref) == date(2026, 3, 29)

    def test_iso_format(self):
        assert resolve_date("2026-04-15") == date(2026, 4, 15)

    def test_case_insensitive(self):
        ref = date(2026, 3, 23)
        assert resolve_date("TOMORROW", ref) == date(2026, 3, 24)
        assert resolve_date("Friday", ref) == date(2026, 3, 27)
        assert resolve_date("Mar-29", ref) == date(2026, 3, 29)

class TestResolveTimeAmPm:
    """The dot separator is gone; am/pm rides on HH:MM like every other time."""

    def test_pm(self):
        assert resolve_time("2:20pm") == "14:20"

    def test_am(self):
        assert resolve_time("9:05am") == "09:05"

    def test_space_before_period(self):
        assert resolve_time("2:20 pm") == "14:20"

    def test_12pm_noon(self):
        assert resolve_time("12:00pm") == "12:00"

    def test_12am_midnight(self):
        assert resolve_time("12:30am") == "00:30"

    def test_invalid_hour(self):
        with pytest.raises(ValueError):
            resolve_time("13:20pm")

    def test_invalid_minutes(self):
        with pytest.raises(ValueError):
            resolve_time("2:99pm")


class TestResolveTimeInvalid:
    def test_resolve_time_invalid_ampm(self):
        """am/pm with hour > 12 should raise."""
        with pytest.raises(ValueError):
            resolve_time("13pm")

    def test_resolve_time_invalid_minutes(self):
        """Minutes >= 60 should raise."""
        with pytest.raises(ValueError):
            resolve_time("1:60")

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


class TestDoubleDutyTags:
    """@@word keeps the word in the body AND records it as a tag."""

    def test_double_tag_keeps_word_mid_sentence(self):
        result = parse_capture_tokens(("/j", "i", "went", "with", "@@sam", "to", "lunch"))
        assert result.body == "i went with sam to lunch"
        assert result.tags == ["sam"]

    def test_double_tag_preserves_typed_capitalization_in_body(self):
        result = parse_capture_tokens(("/j", "lunch", "with", "@@Sam"))
        assert result.body == "lunch with Sam"

    def test_double_tag_lowercases_the_tag(self):
        result = parse_capture_tokens(("/j", "lunch", "with", "@@Sam"))
        assert result.tags == ["sam"]

    def test_double_tag_with_trailing_punctuation(self):
        result = parse_capture_tokens(("/j", "i", "love", "@@Sam,", "truly"))
        assert result.body == "i love Sam, truly"
        assert result.tags == ["sam"]

    def test_double_tag_inside_quoted_token(self):
        result = parse_capture_tokens(('/j', 'i said to @@Sam, "dont try"'))
        assert result.body == 'i said to Sam, "dont try"'
        assert result.tags == ["sam"]

    def test_double_tag_mixed_with_plain_tag(self):
        result = parse_capture_tokens(("/j", "movie", "with", "@@Sam", "@fav"))
        assert result.body == "movie with Sam"
        assert result.tags == ["sam", "fav"]

    def test_acronym_keeps_case_in_body_lowercase_in_tag(self):
        result = parse_capture_tokens(("/n", "read", "about", "@@AI", "today"))
        assert result.body == "read about AI today"
        assert result.tags == ["ai"]

    def test_double_tag_appears_once_in_tags(self):
        result = parse_capture_tokens(("/j", "@@sam", "and", "@@sam"))
        assert result.tags == ["sam"]


class TestTagLowercasing:
    def test_plain_tag_is_lowercased(self):
        result = parse_capture_tokens(("/t", "fix", "bug", "@Backend"))
        assert result.tags == ["backend"]
        assert result.body == "fix bug"


class TestTagScanningDoesNotOvermatch:
    """Single @ keeps whole-token matching so literal text stays literal."""

    def test_decorator_in_note_stays_literal(self):
        result = parse_capture_tokens(("/n", "wraps", "with", "@server.tool()"))
        assert result.body == "wraps with @server.tool()"
        assert result.tags == []

    def test_email_address_is_not_a_tag(self):
        result = parse_capture_tokens(("/n", "mail", "khalid@gmail.com"))
        assert result.body == "mail khalid@gmail.com"
        assert result.tags == []

    def test_plain_tag_inside_quoted_token_stays_literal(self):
        result = parse_capture_tokens(("/n", "use @backend to filter"))
        assert result.body == "use @backend to filter"
        assert result.tags == []

    def test_bare_double_at_is_body_text(self):
        result = parse_capture_tokens(("/n", "wat", "@@"))
        assert result.body == "wat @@"
        assert result.tags == []
