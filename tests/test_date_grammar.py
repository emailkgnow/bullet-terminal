"""One spelling per concept: full-word metadata keys, no legacy date/time formats.

Covers the two cuts made together:
  - short keys d:/t:/r: removed in favour of date:/time:/repeat:
  - legacy numeric formats (MMDD, M/D, HHMM, HH:MM) removed
"""

from datetime import date

import pytest

from bute.cli import main
from bute.models import Entry, EntryType
from bute.parser import parse_capture_tokens, resolve_date, resolve_repeat, resolve_time
from bute.state import save_state
from bute.storage import entry_path_from_id, load_entry, save_entry

REF = date(2026, 9, 20)  # a Sunday


# --- Date formats that stay ---

class TestDateFormatsKept:
    @pytest.mark.parametrize("value,expected", [
        ("today", date(2026, 9, 20)),
        ("tomorrow", date(2026, 9, 21)),
        ("friday", date(2026, 9, 25)),
        ("next-friday", date(2026, 10, 2)),
        ("12.25", date(2026, 12, 25)),
        ("4.7", date(2027, 4, 7)),          # already past → next year
        ("mar15", date(2027, 3, 15)),
        ("2026-11-03", date(2026, 11, 3)),
    ])
    def test_resolves(self, value, expected):
        assert resolve_date(value, REF) == expected

    @pytest.mark.parametrize("value,expected", [
        ("tod", date(2026, 9, 20)),
        ("tom", date(2026, 9, 21)),
        ("tmrw", date(2026, 9, 21)),
        ("fri", date(2026, 9, 25)),
    ])
    def test_aliases_survive(self, value, expected):
        assert resolve_date(value, REF) == expected


# --- Date formats that are gone ---

class TestLegacyDateFormatsRejected:
    @pytest.mark.parametrize("value", ["0407", "0330", "1225"])
    def test_four_digit_mmdd_rejected(self, value):
        with pytest.raises(ValueError):
            resolve_date(value, REF)

    @pytest.mark.parametrize("value", ["3/29", "12/25"])
    def test_slash_rejected(self, value):
        with pytest.raises(ValueError):
            resolve_date(value, REF)


# --- Time formats that stay ---

class TestTimeFormatsKept:
    @pytest.mark.parametrize("value,expected", [
        ("9", "09:00"),
        ("14", "14:00"),
        ("14.30", "14:30"),
        ("9.05", "09:05"),
        ("3pm", "15:00"),
        ("2.20pm", "14:20"),
        ("11am", "11:00"),
        ("12am", "00:00"),
    ])
    def test_resolves(self, value, expected):
        assert resolve_time(value) == expected


# --- Time formats that are gone ---

class TestLegacyTimeFormatsRejected:
    @pytest.mark.parametrize("value", ["1430", "0900", "2359"])
    def test_four_digit_hhmm_rejected(self, value):
        with pytest.raises(ValueError):
            resolve_time(value)

    @pytest.mark.parametrize("value", ["14:30", "9:05"])
    def test_colon_time_rejected(self, value):
        with pytest.raises(ValueError):
            resolve_time(value)


# --- Repeat is validated ---

class TestResolveRepeat:
    @pytest.mark.parametrize("value", ["daily", "weekly", "monthly", "yearly"])
    def test_valid_values(self, value):
        assert resolve_repeat(value) == value

    def test_case_insensitive(self):
        assert resolve_repeat("Daily") == "daily"

    @pytest.mark.parametrize("value", ["hourly", "fortnightly", "every-day", ""])
    def test_invalid_rejected(self, value):
        with pytest.raises(ValueError):
            resolve_repeat(value)


# --- Capture: full words work ---

class TestCaptureFullWordKeys:
    def test_date_and_time(self, runner, tmp_config, tmp_data):
        result = runner.invoke(main, ["c", "dentist", "date:12.25", "time:14.30"])
        assert result.exit_code == 0, result.output
        content = next(iter(tmp_data.rglob("*.md"))).read_text()
        assert "date: '2026-12-25'" in content
        assert "time: '14:30'" in content

    def test_due(self, runner, tmp_config, tmp_data):
        result = runner.invoke(main, ["t", "file", "taxes", "due:tomorrow"])
        assert result.exit_code == 0, result.output
        content = next(iter(tmp_data.rglob("*.md"))).read_text()
        assert "due:" in content

    def test_repeat(self, runner, tmp_config, tmp_data):
        result = runner.invoke(main, ["t", "water", "plants", "repeat:daily"])
        assert result.exit_code == 0, result.output
        content = next(iter(tmp_data.rglob("*.md"))).read_text()
        assert "repeat: daily" in content

    def test_invalid_repeat_is_rejected(self, runner, tmp_config, tmp_data):
        result = runner.invoke(main, ["t", "water", "plants", "repeat:hourly"])
        assert result.exit_code != 0
        assert "hourly" in result.output
        assert list(tmp_data.rglob("*.md")) == []


# --- Capture: short keys are gone, and say so ---

class TestCaptureShortKeysRemoved:
    @pytest.mark.parametrize("token,replacement", [
        ("d:friday", "date:"),
        ("t:9", "time:"),
        ("r:daily", "repeat:"),
    ])
    def test_short_key_errors_with_pointer(self, runner, tmp_config, tmp_data, token, replacement):
        result = runner.invoke(main, ["t", "do", "thing", token])
        assert result.exit_code != 0, result.output
        assert replacement in result.output
        assert list(tmp_data.rglob("*.md")) == [], "nothing should be written"

    def test_unrelated_key_still_becomes_extra_meta(self, runner, tmp_config, tmp_data):
        """Only d/t/r are special-cased; other key:value tokens are untouched."""
        result = runner.invoke(main, ["t", "call", "bank", "project:alpha"])
        assert result.exit_code == 0, result.output
        assert "project:alpha" in result.output

    def test_prose_colon_is_not_metadata(self):
        """A bare 'date:' followed by a space stays in the body."""
        parsed = parse_capture_tokens(["j", "had", "a", "date:", "with", "sara"])
        assert parsed.body == "had a date: with sara"
        assert parsed.metadata == {}


# --- Action: full words work on an existing entry ---

def _one_task(config=None):
    entry = Entry.create(EntryType.TASK, "review budget")
    save_entry(entry)
    save_state("tasks", [entry.id])
    return entry


class TestActionFullWordKeys:
    def test_set_date_and_time(self, runner, tmp_config, tmp_data):
        entry = _one_task()
        result = runner.invoke(main, ["1", "date:12.25", "time:9"])
        assert result.exit_code == 0, result.output
        reloaded = load_entry(entry_path_from_id(entry.id))
        assert reloaded.scheduled_date == date(2026, 12, 25)
        assert reloaded.scheduled_time == "09:00"

    def test_set_repeat(self, runner, tmp_config, tmp_data):
        """repeat: was capture-only before; it now works on an existing entry."""
        entry = _one_task()
        result = runner.invoke(main, ["1", "repeat:weekly"])
        assert result.exit_code == 0, result.output
        assert load_entry(entry_path_from_id(entry.id)).repeat == "weekly"

    def test_set_invalid_repeat_rejected(self, runner, tmp_config, tmp_data):
        entry = _one_task()
        result = runner.invoke(main, ["1", "repeat:hourly"])
        assert "Invalid repeat" in result.output
        assert load_entry(entry_path_from_id(entry.id)).repeat is None

    @pytest.mark.parametrize("token,replacement", [
        ("d:friday", "date:"),
        ("t:9", "time:"),
        ("r:daily", "repeat:"),
    ])
    def test_short_keys_removed(self, runner, tmp_config, tmp_data, token, replacement):
        """Rejected with a pointer, and — critically — not misread as a tag.

        The action path reports bad meta values inline and still exits 0; that
        is its existing convention for every invalid value, so what matters
        here is that the entry comes back untouched.
        """
        entry = _one_task()
        result = runner.invoke(main, ["1", token])
        assert "was removed" in result.output
        assert replacement in result.output
        reloaded = load_entry(entry_path_from_id(entry.id))
        assert reloaded.scheduled_date is None
        assert reloaded.scheduled_time is None
        assert reloaded.repeat is None
        assert reloaded.tags == [], "must not be misread as a tag"


# --- Clear: full words only ---

class TestClearFullWords:
    def test_clear_date(self, runner, tmp_config, tmp_data):
        entry = Entry.create(EntryType.TASK, "x", scheduled_date=date(2026, 12, 25))
        save_entry(entry)
        save_state("tasks", [entry.id])
        assert runner.invoke(main, ["1", "clear", "date"]).exit_code == 0
        assert load_entry(entry_path_from_id(entry.id)).scheduled_date is None

    def test_clear_time(self, runner, tmp_config, tmp_data):
        entry = Entry.create(EntryType.TASK, "x", scheduled_time="14:30")
        save_entry(entry)
        save_state("tasks", [entry.id])
        assert runner.invoke(main, ["1", "clear", "time"]).exit_code == 0
        assert load_entry(entry_path_from_id(entry.id)).scheduled_time is None

    def test_clear_repeat(self, runner, tmp_config, tmp_data):
        entry = Entry.create(EntryType.TASK, "x", repeat="daily")
        save_entry(entry)
        save_state("tasks", [entry.id])
        assert runner.invoke(main, ["1", "clear", "repeat"]).exit_code == 0
        assert load_entry(entry_path_from_id(entry.id)).repeat is None

    @pytest.mark.parametrize("field,replacement", [("d", "date"), ("t", "time")])
    def test_clear_short_key_does_not_silently_remove_a_tag(
        self, runner, tmp_config, tmp_data, field, replacement
    ):
        entry = Entry.create(EntryType.TASK, "x", scheduled_date=date(2026, 12, 25))
        save_entry(entry)
        save_state("tasks", [entry.id])
        result = runner.invoke(main, ["1", "clear", field])
        assert result.exit_code != 0, result.output
        assert replacement in result.output
        assert load_entry(entry_path_from_id(entry.id)).scheduled_date is not None
