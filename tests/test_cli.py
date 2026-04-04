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


def test_unknown_command(runner):
    result = runner.invoke(main, ["foobar"])
    assert result.exit_code != 0


def test_plus_syntax_removed(runner, tmp_config, tmp_data):
    """bt +name should no longer route to collections."""
    result = runner.invoke(main, ["+old-collection"])
    assert result.exit_code != 0 or "no such command" in result.output.lower() or "error" in result.output.lower()
