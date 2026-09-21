"""The help screen must teach the grammar the parser actually accepts.

The date/time grammar has now been cut twice. Both times the help text was a
separate edit from the parser change, which is exactly how a help screen ends
up advertising a format that no longer works. These tests close that gap: the
examples printed in `bt -h` are fed back through the resolvers.
"""

import re

import pytest

from bute.cli import main
from bute.parser import resolve_date, resolve_repeat, resolve_time

# date:friday, time:14:30, due:friday, repeat:daily — but not the <placeholders>
EXAMPLE_RE = re.compile(r"\b(date|time|due|repeat):([^\s<>|\]]+)")

RESOLVERS = {
    "date": resolve_date,
    "due": resolve_date,
    "time": resolve_time,
    "repeat": resolve_repeat,
}


def _help_text(runner, tmp_config, tmp_data) -> str:
    result = runner.invoke(main, ["-h"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    return result.output


def _examples(text: str) -> list[tuple[str, str]]:
    found = []
    for key, value in EXAMPLE_RE.findall(text):
        value = value.rstrip(".,;")
        # skip wrapped/placeholder fragments
        if not value or value.startswith("<"):
            continue
        found.append((key, value))
    return found


def test_help_contains_metadata_examples(runner, tmp_config, tmp_data):
    """Guard the guard — if the regex stops matching, the test below is vacuous."""
    examples = _examples(_help_text(runner, tmp_config, tmp_data))
    assert len(examples) >= 6, f"expected real examples, found {examples}"


def test_every_help_example_actually_parses(runner, tmp_config, tmp_data):
    """No example in the help may be a spelling the parser rejects."""
    failures = []
    for key, value in _examples(_help_text(runner, tmp_config, tmp_data)):
        try:
            RESOLVERS[key](value)
        except ValueError as exc:
            failures.append(f"{key}:{value} — {exc}")
    assert not failures, "help advertises input the parser rejects:\n  " + "\n  ".join(failures)


class TestHelpDocumentsTheGrammar:
    def test_lists_every_date_form(self, runner, tmp_config, tmp_data):
        text = _help_text(runner, tmp_config, tmp_data)
        for form in ["today", "tomorrow", "friday", "jan-23", "01-23", "2026-01-23"]:
            assert form in text, f"help does not mention the date form {form!r}"

    def test_explains_forward_resolution(self, runner, tmp_config, tmp_data):
        """The year-roll is the one surprising thing left; it must be stated."""
        text = _help_text(runner, tmp_config, tmp_data).lower()
        assert "resolve forward" in text
        assert "iso" in text

    def test_states_that_minutes_are_required(self, runner, tmp_config, tmp_data):
        text = _help_text(runner, tmp_config, tmp_data).lower()
        assert "minutes" in text, "help must say minutes are required"

    def test_shows_both_24h_and_am_pm(self, runner, tmp_config, tmp_data):
        text = _help_text(runner, tmp_config, tmp_data)
        assert "14:30" in text
        assert re.search(r"\d:\d{2}(am|pm)", text, re.IGNORECASE), "no am/pm example"

    @pytest.mark.parametrize("retired", ["date:4.7", "time:14.30", "next-friday", "jan15"])
    def test_does_not_advertise_retired_spellings(self, runner, tmp_config, tmp_data, retired):
        assert retired not in _help_text(runner, tmp_config, tmp_data)


def _row(text: str, marker: str) -> str:
    """The single help line containing `marker` (COLUMNS=200 keeps rows unwrapped)."""
    rows = [line for line in text.splitlines() if marker in line]
    assert len(rows) == 1, f"expected exactly one row for {marker!r}, got {rows}"
    return rows[0]


class TestHelpDocumentsTheFocusFlow:
    """`-l` and `-b` decide which of the three task views a capture lands in.

    The help called `-l` the "Task log" long after that view was renamed
    Tasks — Weekly Log, so it described a destination that no longer had a
    name. Pin each flag to the view command that shows its result.
    """

    def test_later_flag_names_the_weekly_log(self, runner, tmp_config, tmp_data):
        row = _row(_help_text(runner, tmp_config, tmp_data), "-l|--later")
        assert "bt w" in row, f"the -l row must point at bt w: {row!r}"

    def test_backlog_flag_names_the_backlog(self, runner, tmp_config, tmp_data):
        row = _row(_help_text(runner, tmp_config, tmp_data), "-b|--backlog")
        assert "bt b" in row, f"the -b row must point at bt b: {row!r}"

    def test_does_not_use_the_retired_task_log_name(self, runner, tmp_config, tmp_data):
        text = _help_text(runner, tmp_config, tmp_data).lower()
        assert "task log" not in text, "the view is Tasks — Weekly Log (bt w)"

    def test_important_is_shown_as_a_signifier_suffix(self, runner, tmp_config, tmp_data):
        """`!` only works glued to the letter — `bt t x !` puts a literal ! in the body."""
        text = _help_text(runner, tmp_config, tmp_data)
        assert "bt t!" in text, "help must show ! attached to the signifier"
