"""One clear way to write a date and a time.

Dates are ISO or an ISO tail (`2026-01-23`, `01-23`), a month abbreviation with
a day (`jan-23`), or a relative word (`today`, `tomorrow`, a weekday). Times are
`HH:MM`, read as 24-hour unless an am/pm suffix is given. Everything is
case-insensitive, and the hyphen is the only date separator.

Also covers the full-word metadata keys (`due:`, `date:`, `time:`, `repeat:`)
that replaced the short `d:`/`t:`/`r:` forms.
"""

from datetime import date

import pytest

from bute.cli import main
from bute.models import Entry, EntryType
from bute.parser import parse_capture_tokens, resolve_date, resolve_repeat, resolve_time
from bute.state import save_state
from bute.storage import entry_path_from_id, load_entry, save_entry

REF = date(2026, 9, 20)  # a Sunday


# --- Dates: the four forms that stay ---

class TestDateFormsKept:
    @pytest.mark.parametrize("value,expected", [
        # relative words
        ("today", date(2026, 9, 20)),
        ("tomorrow", date(2026, 9, 21)),
        # weekdays, full and three-letter
        ("friday", date(2026, 9, 25)),
        ("fri", date(2026, 9, 25)),
        ("sunday", date(2026, 9, 27)),   # today is Sunday → next week's
        ("sun", date(2026, 9, 27)),
        # month abbreviation + day
        ("dec-25", date(2026, 12, 25)),
        ("jan-23", date(2027, 1, 23)),   # already past → next year
        # numeric MM-DD (the ISO tail)
        ("12-25", date(2026, 12, 25)),
        ("01-23", date(2027, 1, 23)),
        ("1-23", date(2027, 1, 23)),     # unpadded is fine, still unambiguous
        # full ISO — exact, never rolls
        ("2026-11-03", date(2026, 11, 3)),
        ("2020-01-01", date(2020, 1, 1)),
    ])
    def test_resolves(self, value, expected):
        assert resolve_date(value, REF) == expected

    @pytest.mark.parametrize("value,expected", [
        ("Today", date(2026, 9, 20)),
        ("Tomorrow", date(2026, 9, 21)),
        ("Friday", date(2026, 9, 25)),
        ("FRI", date(2026, 9, 25)),
        ("Sun", date(2026, 9, 27)),
        ("Jan-23", date(2027, 1, 23)),
        ("DEC-25", date(2026, 12, 25)),
    ])
    def test_capitalization_is_accepted(self, value, expected):
        assert resolve_date(value, REF) == expected

    def test_mm_dd_rolls_forward_but_iso_does_not(self):
        """The ISO tail means "the next one"; full ISO means exactly that date."""
        assert resolve_date("01-23", REF) == date(2027, 1, 23)
        assert resolve_date("2026-01-23", REF) == date(2026, 1, 23)


# --- Dates: what is gone, and what the error tells you ---

class TestRemovedDateForms:
    @pytest.mark.parametrize("value,hint", [
        ("4.7", "04-07"),          # dot dates — the dot is now time-only
        ("12.25", "12-25"),
        ("0407", "04-07"),         # legacy 4-digit
        ("3/29", "03-29"),         # legacy slash
        ("jan15", "jan-15"),       # glued month form
        ("mar3", "mar-03"),
        ("tod", "today"),
        ("tmrw", "tomorrow"),
        ("tmr", "tomorrow"),
        ("tom", "tomorrow"),
    ])
    def test_rejected_with_a_pointer(self, value, hint):
        with pytest.raises(ValueError) as exc:
            resolve_date(value, REF)
        assert hint in str(exc.value)

    @pytest.mark.parametrize("value", [
        "next-friday", "next friday", "next.friday", "nextfriday",
    ])
    def test_next_prefix_is_gone(self, value):
        with pytest.raises(ValueError) as exc:
            resolve_date(value, REF)
        assert "next" in str(exc.value).lower()

    @pytest.mark.parametrize("value", [
        "january-23",   # full month names were never supported and stay unsupported
        "13-01",        # month 13
        "02-30",        # Feb 30
        "notaday",
        "",
    ])
    def test_plain_rejections(self, value):
        with pytest.raises(ValueError):
            resolve_date(value, REF)


# --- Times: HH:MM, 24h unless suffixed ---

class TestTimeFormsKept:
    @pytest.mark.parametrize("value,expected", [
        ("9:00", "09:00"),
        ("14:30", "14:30"),
        ("0:00", "00:00"),
        ("23:59", "23:59"),
        ("09:05", "09:05"),
    ])
    def test_24h_is_the_default(self, value, expected):
        assert resolve_time(value) == expected

    @pytest.mark.parametrize("value,expected", [
        ("9:00am", "09:00"),
        ("9:00pm", "21:00"),
        ("2:20pm", "14:20"),
        ("12:00am", "00:00"),
        ("12:00pm", "12:00"),
        ("11:30am", "11:30"),
    ])
    def test_suffix_switches_to_12h(self, value, expected):
        assert resolve_time(value) == expected

    @pytest.mark.parametrize("value,expected", [
        ("2:20PM", "14:20"),
        ("9:00AM", "09:00"),
        ("2:20Pm", "14:20"),
    ])
    def test_capitalized_suffix_is_accepted(self, value, expected):
        assert resolve_time(value) == expected


class TestRemovedTimeForms:
    @pytest.mark.parametrize("value,hint", [
        ("9", "9:00"),          # bare hour — minutes are required
        ("14", "14:00"),
        ("3pm", "3:00pm"),      # bare hour with a suffix
        ("11am", "11:00am"),
        ("14.30", "14:30"),     # dot times — the dot is gone entirely
        ("2.20pm", "2:20pm"),
        ("1430", "14:30"),      # legacy 4-digit
    ])
    def test_rejected_with_a_pointer(self, value, hint):
        with pytest.raises(ValueError) as exc:
            resolve_time(value)
        assert hint in str(exc.value)

    @pytest.mark.parametrize("value", [
        "24:00",     # hour out of range for 24h
        "12:60",     # minute out of range
        "13:00pm",   # hour out of range for a suffixed time
        "0:00am",
        "notatime",
        "",
    ])
    def test_plain_rejections(self, value):
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


# --- Capture: full words, new value forms ---

class TestCaptureFullWordKeys:
    def test_date_and_time(self, runner, tmp_config, tmp_data):
        result = runner.invoke(main, ["c", "dentist", "date:12-25", "time:14:30"])
        assert result.exit_code == 0, result.output
        saved = load_entry(next(iter(tmp_data.rglob("*.md"))))
        assert saved.scheduled_date == date(2026, 12, 25)
        assert saved.scheduled_time == "14:30"

    def test_month_name_and_suffixed_time(self, runner, tmp_config, tmp_data):
        """A 12-hour input is stored in the canonical 24-hour form."""
        result = runner.invoke(main, ["c", "standup", "date:dec-25", "time:9:00am"])
        assert result.exit_code == 0, result.output
        saved = load_entry(next(iter(tmp_data.rglob("*.md"))))
        assert saved.scheduled_date == date(2026, 12, 25)
        assert saved.scheduled_time == "09:00"

    def test_due(self, runner, tmp_config, tmp_data):
        result = runner.invoke(main, ["t", "file", "taxes", "due:tomorrow"])
        assert result.exit_code == 0, result.output
        assert "due:" in next(iter(tmp_data.rglob("*.md"))).read_text()

    def test_repeat(self, runner, tmp_config, tmp_data):
        result = runner.invoke(main, ["t", "water", "plants", "repeat:daily"])
        assert result.exit_code == 0, result.output
        assert "repeat: daily" in next(iter(tmp_data.rglob("*.md"))).read_text()

    def test_invalid_repeat_is_rejected(self, runner, tmp_config, tmp_data):
        result = runner.invoke(main, ["t", "water", "plants", "repeat:hourly"])
        assert result.exit_code != 0
        assert "hourly" in result.output
        assert list(tmp_data.rglob("*.md")) == []

    @pytest.mark.parametrize("token,hint", [
        ("date:4.7", "04-07"),
        ("time:14.30", "14:30"),
        ("time:9", "9:00"),
        ("date:next-friday", "next"),
    ])
    def test_removed_value_forms_are_rejected_at_capture(
        self, runner, tmp_config, tmp_data, token, hint
    ):
        result = runner.invoke(main, ["c", "thing", token])
        assert result.exit_code != 0, result.output
        assert hint in result.output
        assert list(tmp_data.rglob("*.md")) == [], "nothing should be written"


# --- Capture: short keys are gone, and say so ---

class TestCaptureShortKeysRemoved:
    @pytest.mark.parametrize("token,replacement", [
        ("d:friday", "date:"),
        ("t:9:00", "time:"),
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


# --- Action: same grammar on an existing entry ---

def _one_task():
    entry = Entry.create(EntryType.TASK, "review budget")
    save_entry(entry)
    save_state("tasks", [entry.id])
    return entry


class TestActionFullWordKeys:
    def test_set_date_and_time(self, runner, tmp_config, tmp_data):
        entry = _one_task()
        result = runner.invoke(main, ["1", "date:12-25", "time:9:00"])
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

    @pytest.mark.parametrize("token,hint", [
        ("date:4.7", "04-07"),
        ("time:9", "9:00"),
    ])
    def test_removed_value_forms_rejected(self, runner, tmp_config, tmp_data, token, hint):
        entry = _one_task()
        result = runner.invoke(main, ["1", token])
        assert hint in result.output
        reloaded = load_entry(entry_path_from_id(entry.id))
        assert reloaded.scheduled_date is None
        assert reloaded.scheduled_time is None

    @pytest.mark.parametrize("token,replacement", [
        ("d:friday", "date:"),
        ("t:9:00", "time:"),
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


# --- Reading is looser than typing ---

class TestReadingIsLooserThanTyping:
    """Files on disk outlive the input grammar, so reads must not depend on it.

    Every spelling below is rejected at the CLI but must still load, because a
    hand-written or agent-written file (BYOAI) may use any of them.
    """

    def test_stored_hh_mm_round_trips(self, runner, tmp_config, tmp_data):
        entry = Entry.create(EntryType.CALENDAR, "meeting", scheduled_time="14:30")
        save_entry(entry)
        assert load_entry(entry_path_from_id(entry.id)).scheduled_time == "14:30"

    @pytest.mark.parametrize("stored,expected", [
        ("14:30", "14:30"),
        ("09:00", "09:00"),
        (870, "14:30"),        # unquoted "14:30" is sexagesimal in YAML 1.1
        (0, "00:00"),
        ("3pm", "15:00"),      # retired input spellings still read
        ("14.30", "14:30"),
        ("1430", "14:30"),
        ("2:20pm", "14:20"),
        ("12:00am", "00:00"),
    ])
    def test_tolerated_on_read(self, stored, expected):
        from bute.storage import _normalize_time
        assert _normalize_time(stored) == expected

    @pytest.mark.parametrize("stored", ["garbage", "", None, 99999, -5, True, "25:00"])
    def test_unreadable_time_yields_none_rather_than_raising(self, stored):
        """One bad field must not hide the whole entry from every view."""
        from bute.storage import _normalize_time
        assert _normalize_time(stored) is None

    def test_agent_written_file_with_unquoted_time_loads(self, tmp_path):
        """`time: 14:30` unquoted reaches us as the int 870 — it must still work."""
        from pathlib import Path
        f = tmp_path / "01M2ZHF4B3GA137E6P56AHX4TM.md"
        f.write_text(
            "---\n"
            "id: 01M2ZHF4B3GA137E6P56AHX4TM\n"
            "type: calendar\n"
            "created: '2026-09-20T09:00:00+03:00'\n"
            "date: '2026-09-20'\n"
            "time: 14:30\n"
            "---\n\nagent-written event\n"
        )
        entry = load_entry(Path(f))
        assert entry.scheduled_time == "14:30"
        assert entry.body == "agent-written event"


# --- due: is a task deadline, nothing else ---

class TestDueIsTaskOnly:
    @pytest.mark.parametrize("sig,noun", [("n", "note"), ("j", "journal"), ("c", "calendar")])
    def test_capture_rejects_due_on_non_task(self, runner, tmp_config, tmp_data, sig, noun):
        result = runner.invoke(main, [sig, "thing", "due:friday"])
        assert result.exit_code != 0, result.output
        assert "date:" in result.output, "should point at date: instead"
        assert noun in result.output
        assert list(tmp_data.rglob("*.md")) == [], "nothing should be written"

    def test_capture_rejects_due_time_shortcut_on_non_task(self, runner, tmp_config, tmp_data):
        result = runner.invoke(main, ["c", "thing", "due:3:00pm"])
        assert result.exit_code != 0, result.output
        assert list(tmp_data.rglob("*.md")) == []

    def test_action_rejects_due_on_non_task(self, runner, tmp_config, tmp_data):
        entry = Entry.create(EntryType.NOTE, "oauth docs")
        save_entry(entry)
        save_state("notes", [entry.id])
        result = runner.invoke(main, ["1", "due:friday"])
        assert "date:" in result.output
        assert load_entry(entry_path_from_id(entry.id)).due is None

    def test_action_can_still_clear_stray_due_on_non_task(self, runner, tmp_config, tmp_data):
        """A due: written by an external agent must stay removable."""
        entry = Entry.create(EntryType.NOTE, "oauth docs", due=date(2026, 10, 1))
        save_entry(entry)
        save_state("notes", [entry.id])
        result = runner.invoke(main, ["1", "clear", "due"])
        assert result.exit_code == 0, result.output
        assert load_entry(entry_path_from_id(entry.id)).due is None
