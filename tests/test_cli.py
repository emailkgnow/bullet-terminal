"""Tests for CLI entry point and command routing."""

from bute.cli import main


def test_version(runner):
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_help(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.output


def test_signifier_dispatch_task(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["/t", "hello", "world"])
    assert result.exit_code == 0
    assert "task" in result.output
    assert "hello world" in result.output


def test_signifier_dispatch_important(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["/t!", "fix", "bug"])
    assert result.exit_code == 0
    assert "!" in result.output
    assert "fix bug" in result.output


def test_signifier_dispatch_note(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["/n", "some", "note"])
    assert result.exit_code == 0
    assert "note" in result.output


def test_signifier_dispatch_journal(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["/j", "feeling", "good"])
    assert result.exit_code == 0
    assert "journal" in result.output


def test_signifier_dispatch_calendar(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["/c", "meeting"])
    assert result.exit_code == 0
    assert "event" in result.output


def test_number_action_dispatch_no_state(runner, tmp_config, tmp_data):
    """Without a prior view, action should error about no state."""
    result = runner.invoke(main, ["2", "done"])
    assert result.exit_code == 1
    assert "No active view" in result.output


def test_number_action_routes_to_action(runner, tmp_config, tmp_data):
    """Verify digits route to the action command (not a named command)."""
    # Capture an entry, list it, then act on it
    runner.invoke(main, ["/t", "test", "task"])
    runner.invoke(main, ["t"])
    result = runner.invoke(main, ["1", "done"])
    assert result.exit_code == 0
    assert "done" in result.output


def test_unknown_command(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["foobar"])
    assert result.exit_code != 0


def test_plus_syntax_removed(runner, tmp_config, tmp_data):
    """bt +name should no longer route to collections."""
    result = runner.invoke(main, ["+old-collection"])
    assert result.exit_code != 0 or "no such command" in result.output.lower() or "error" in result.output.lower()


# --- Random journal whisper ---


def _stub_journals(monkeypatch, count):
    """Make `count` journals dated before today visible to _show_random_journal.

    Patches the query rather than writing files: entry lookup keys off the ULID
    timestamp, so back-dating `created` across a month boundary would hide files.
    """
    from datetime import datetime, timedelta

    from bute.models import Entry, EntryType

    entries = []
    for i in range(count):
        e = Entry.create(EntryType.JOURNAL, f"old journal {i}")
        e.created = datetime.now() - timedelta(days=i + 1)
        entries.append(e)

    monkeypatch.setattr("bute.storage.query_and_load", lambda *a, **k: list(entries))
    return entries


def test_random_journal_skips_recently_shown(tmp_config, tmp_data, monkeypatch):
    """With a pool larger than the buffer, no entry repeats within the buffer window."""
    from bute.cli import _show_random_journal
    from bute.state import JOURNAL_HISTORY_LIMIT

    _stub_journals(monkeypatch, JOURNAL_HISTORY_LIMIT + 5)

    seen = [_show_random_journal(None) for _ in range(JOURNAL_HISTORY_LIMIT + 1)]
    assert None not in seen
    assert len(set(seen)) == len(seen), "an entry repeated inside the buffer window"


def test_random_journal_falls_back_when_pool_smaller_than_buffer(tmp_config, tmp_data, monkeypatch):
    """A tiny journal collection still shows something once every entry is in the buffer."""
    from bute.cli import _show_random_journal

    _stub_journals(monkeypatch, 3)

    seen = [_show_random_journal(None) for _ in range(10)]
    assert None not in seen
    assert len(set(seen)) == 3


def test_random_journal_records_history(tmp_config, tmp_data, monkeypatch):
    from bute.cli import _show_random_journal
    from bute.state import get_journal_history

    _stub_journals(monkeypatch, 5)
    shown = _show_random_journal(None)
    assert get_journal_history() == [shown]


def test_help_never_says_the_old_name(runner, tmp_config, tmp_data):
    """The only public names are 'Bullet Terminal' and 'bt'."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "bute" not in result.output.lower()
    assert "ai-powered" not in result.output.lower()
    assert "Bullet Terminal" in result.output
    assert "Bullet-Terminal" not in result.output

    from bute.cli import main as cli_main
    assert "bute" not in (cli_main.__doc__ or "").lower()
    assert "Bullet Terminal" in (cli_main.__doc__ or "")
