"""Tests for view commands."""

import json

from bute.cli import main
from bute.state import state_path


def test_ls_today(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["ls"])
    assert result.exit_code == 0
    assert "call dentist" in result.output
    assert "fix bug" in result.output
    assert "OAuth2 tokens" in result.output
    assert "feeling good" in result.output


def test_ls_today_empty(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["ls"])
    assert result.exit_code == 0
    assert "No entries found" in result.output


def test_ls_tasks(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["ls", "tasks"])
    assert result.exit_code == 0
    assert "call dentist" in result.output
    assert "fix bug" in result.output
    # Notes and journals should not appear
    assert "OAuth2 tokens" not in result.output
    assert "feeling good" not in result.output


def test_active(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["active"])
    assert result.exit_code == 0
    assert "Active Tasks" in result.output


def test_tag_filter(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["+backend"])
    assert result.exit_code == 0
    assert "fix bug" in result.output
    assert "call dentist" not in result.output


def test_tag_filter_empty(runner, tmp_config, populated_data):
    result = runner.invoke(main, ["+nonexistent"])
    assert result.exit_code == 0
    assert "No entries found" in result.output


def test_ls_writes_state(runner, tmp_config, populated_data):
    runner.invoke(main, ["ls"])
    path = state_path()
    assert path.exists()
    state = json.loads(path.read_text())
    assert state["view"] == "ls"
    assert len(state["entries"]) == 4


def test_ls_tasks_writes_state(runner, tmp_config, populated_data):
    runner.invoke(main, ["ls", "tasks"])
    path = state_path()
    state = json.loads(path.read_text())
    assert len(state["entries"]) == 2  # only active tasks
