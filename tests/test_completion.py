"""Tests for @tag shell completion."""

from click.shell_completion import ShellComplete

from bute.cli import main
from bute.models import Entry, EntryType
from bute.storage import save_entry


def _complete(args: list[str], incomplete: str) -> list[str]:
    comp = ShellComplete(main, {}, "bt", "_BT_COMPLETE")
    return sorted(item.value for item in comp.get_completions(args, incomplete))


def _seed(tmp_data):
    save_entry(Entry.create(EntryType.TASK, "a", tags=["backend", "bank"]))
    save_entry(Entry.create(EntryType.NOTE, "b", tags=["health"]))


def test_capture_completes_tags(tmp_config, tmp_data):
    _seed(tmp_data)
    assert _complete(["t", "call"], "@ba") == ["@backend", "@bank"]


def test_capture_no_completion_for_plain_words(tmp_config, tmp_data):
    _seed(tmp_data)
    assert _complete(["t", "call"], "den") == []


def test_action_completes_tags(tmp_config, tmp_data):
    _seed(tmp_data)
    assert _complete(["3"], "@he") == ["@health"]


def test_first_token_tag_filter_completes(tmp_config, tmp_data):
    _seed(tmp_data)
    assert _complete([], "@b") == ["@backend", "@bank"]


def test_first_token_command_names_still_complete(tmp_config, tmp_data):
    assert "tasks" in _complete([], "ta")


def test_view_tag_argument_completes(tmp_config, tmp_data):
    _seed(tmp_data)
    assert _complete(["tasks"], "@he") == ["@health"]


def test_completion_command_prints_zsh_line(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["completion"])
    assert result.exit_code == 0
    assert '_BT_COMPLETE=zsh_source bt' in result.output


def test_completion_command_bash(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["completion", "bash"])
    assert result.exit_code == 0
    assert '_BT_COMPLETE=bash_source bt' in result.output
