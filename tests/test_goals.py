"""Tests for bt goals command."""

from bute.cli import main
from bute.models import Entry, EntryType, TaskStatus
from bute.storage import save_entry


def _index_entry(entry):
    """Insert entry into the SQLite index so query_entries finds it."""
    from bute.db import upsert_entry
    upsert_entry(entry)


def test_goals_view(runner, tmp_config, tmp_data):
    """bt goals should show goal notes with task progress."""
    goal = Entry.create(EntryType.NOTE, "get fit by summer", tags=["goal", "fitness"])
    save_entry(goal)
    _index_entry(goal)

    t1 = Entry.create(EntryType.TASK, "sign up for gym", tags=["fitness"])
    t1.status = TaskStatus.ACTIVE
    save_entry(t1)
    _index_entry(t1)

    t2 = Entry.create(EntryType.TASK, "buy protein powder", tags=["fitness"])
    t2.status = TaskStatus.DONE
    save_entry(t2)
    _index_entry(t2)

    result = runner.invoke(main, ["goals"])
    assert result.exit_code == 0
    assert "get fit by summer" in result.output
    assert "1 active" in result.output
    assert "1 done" in result.output


def test_goals_unlinked(runner, tmp_config, tmp_data):
    """Goal with only @goal tag shows dash and 0/0."""
    goal = Entry.create(EntryType.NOTE, "write a novel", tags=["goal"])
    save_entry(goal)
    _index_entry(goal)

    result = runner.invoke(main, ["goals"])
    assert result.exit_code == 0
    assert "write a novel" in result.output
    assert "0 active" in result.output
    assert "0 done" in result.output


def test_goals_multi_tag(runner, tmp_config, tmp_data):
    """Goal with multiple connected tags aggregates across all."""
    goal = Entry.create(EntryType.NOTE, "learn islam", tags=["goal", "prayer", "fasting"])
    save_entry(goal)
    _index_entry(goal)

    t1 = Entry.create(EntryType.TASK, "morning prayer routine", tags=["prayer"])
    t1.status = TaskStatus.ACTIVE
    save_entry(t1)
    _index_entry(t1)

    t2 = Entry.create(EntryType.TASK, "ramadan meal plan", tags=["fasting"])
    t2.status = TaskStatus.ACTIVE
    save_entry(t2)
    _index_entry(t2)

    result = runner.invoke(main, ["goals"])
    assert result.exit_code == 0
    assert "learn islam" in result.output
    assert "2 active" in result.output


def test_goals_multi_tag_no_double_count(runner, tmp_config, tmp_data):
    """Task tagged with multiple connected tags should count once, not per tag."""
    goal = Entry.create(EntryType.NOTE, "learn islam", tags=["goal", "prayer", "fasting"])
    save_entry(goal)
    _index_entry(goal)

    t1 = Entry.create(EntryType.TASK, "ramadan routine", tags=["prayer", "fasting"])
    t1.status = TaskStatus.ACTIVE
    save_entry(t1)
    _index_entry(t1)

    result = runner.invoke(main, ["goals"])
    assert result.exit_code == 0
    assert "1 active" in result.output


def test_goals_important_first(runner, tmp_config, tmp_data):
    """Important goals should appear before non-important."""
    g1 = Entry.create(EntryType.NOTE, "normal goal", tags=["goal", "tag1"])
    save_entry(g1)
    _index_entry(g1)

    g2 = Entry.create(EntryType.NOTE, "important goal", important=True, tags=["goal", "tag2"])
    save_entry(g2)
    _index_entry(g2)

    result = runner.invoke(main, ["goals"])
    assert result.exit_code == 0
    imp_pos = result.output.index("important goal")
    norm_pos = result.output.index("normal goal")
    assert imp_pos < norm_pos


def test_goals_state(runner, tmp_config, tmp_data):
    """bt goals should save state for number-actions."""
    import json

    goal = Entry.create(EntryType.NOTE, "test goal", tags=["goal", "testing"])
    save_entry(goal)
    _index_entry(goal)

    result = runner.invoke(main, ["goals"])
    assert result.exit_code == 0

    from bute.state import state_path
    state_file = state_path()
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["view"] == "goals"
    assert goal.id in state["entries"]


def test_goals_empty(runner, tmp_config, tmp_data):
    """bt goals with no goal notes shows empty message."""
    result = runner.invoke(main, ["goals"])
    assert result.exit_code == 0
    assert "No goals" in result.output


def test_goal_drill(runner, tmp_config, tmp_data):
    """bt 1 after bt goals should show entries with connected tags."""
    goal = Entry.create(EntryType.NOTE, "get fit", tags=["goal", "fitness"])
    save_entry(goal)
    _index_entry(goal)

    t1 = Entry.create(EntryType.TASK, "sign up for gym", tags=["fitness"])
    t1.status = TaskStatus.ACTIVE
    save_entry(t1)
    _index_entry(t1)

    # First, run goals to set state
    runner.invoke(main, ["goals"])

    # Then drill into goal #1
    result = runner.invoke(main, ["1"])
    assert result.exit_code == 0
    assert "sign up for gym" in result.output
    assert "@fitness" in result.output


def test_goal_drill_unlinked(runner, tmp_config, tmp_data):
    """bt 1 on a goal with no connected tags shows helpful message."""
    goal = Entry.create(EntryType.NOTE, "write a novel", tags=["goal"])
    save_entry(goal)
    _index_entry(goal)

    runner.invoke(main, ["goals"])

    result = runner.invoke(main, ["1"])
    assert result.exit_code == 0
    assert "No connected tags" in result.output
