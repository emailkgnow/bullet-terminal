"""Tests for the trash: delete moves to .trash/, bt trash lists, restore brings back."""

import json
import os
import time

import pytest

from bute.cli import main
from bute.models import Entry, EntryType
from bute.state import state_path
from bute.storage import (
    entry_path_from_id,
    list_trash,
    restore_entry,
    save_entry,
    trash_dir,
    trash_entry,
)


def test_trash_entry_moves_file(tmp_data):
    e = Entry.create(EntryType.TASK, "doomed")
    save_entry(e)
    live = entry_path_from_id(e.id)
    assert live is not None

    trashed = trash_entry(e.id)

    assert trashed == trash_dir() / f"{e.id}.md"
    assert trashed.exists()
    assert not live.exists()
    assert entry_path_from_id(e.id) is None


def test_trash_entry_missing_returns_none(tmp_data):
    e = Entry.create(EntryType.TASK, "never saved")
    assert trash_entry(e.id) is None


def test_list_trash_newest_first(tmp_data):
    a = Entry.create(EntryType.TASK, "first")
    b = Entry.create(EntryType.NOTE, "second")
    save_entry(a)
    save_entry(b)
    pa = trash_entry(a.id)
    pb = trash_entry(b.id)
    # Force distinct mtimes: a older, b newer
    now = time.time()
    os.utime(pa, (now - 100, now - 100))
    os.utime(pb, (now, now))

    ids = [e.id for e in list_trash()]
    assert ids == [b.id, a.id]


def test_list_trash_empty(tmp_data):
    assert list_trash() == []


def test_restore_entry_moves_back_and_reindexes(tmp_data):
    from bute.db import close, get_connection
    e = Entry.create(EntryType.TASK, "come back", tags=["x"])
    save_entry(e)
    trash_entry(e.id)

    restored = restore_entry(e.id)

    assert restored.id == e.id
    assert restored.body == "come back"
    live = entry_path_from_id(e.id)
    assert live is not None and live.exists()
    assert not (trash_dir() / f"{e.id}.md").exists()
    row = get_connection().execute(
        "SELECT entry_id FROM entries WHERE entry_id = ?", (e.id,)
    ).fetchone()
    assert row is not None
    close()


def test_restore_entry_not_in_trash_raises(tmp_data):
    from bute.errors import DwnError
    e = Entry.create(EntryType.TASK, "still live")
    save_entry(e)
    with pytest.raises(DwnError):
        restore_entry(e.id)


def test_trash_entry_collision_raises_and_preserves_existing(tmp_data):
    """Trashing the same ULID twice must not clobber the older trashed copy."""
    from bute.errors import DwnError

    e = Entry.create(EntryType.TASK, "first version")
    save_entry(e)
    trash_entry(e.id)
    trashed_path = trash_dir() / f"{e.id}.md"
    original_content = trashed_path.read_text()

    # Simulate the same ULID reappearing on disk (e.g. an external agent
    # rewriting entries/ by ULID) and being deleted again.
    e2 = Entry.create(EntryType.TASK, "second version")
    e2.id = e.id
    save_entry(e2)
    live_path = entry_path_from_id(e.id)
    assert live_path is not None

    with pytest.raises(DwnError):
        trash_entry(e.id)

    # Neither copy was destroyed by the failed second trash attempt.
    assert trashed_path.read_text() == original_content
    assert live_path.exists()
    assert "second version" in live_path.read_text()


def test_restore_entry_collision_raises_and_preserves_existing(tmp_data):
    """Restoring must not overwrite a live file that already occupies the destination."""
    from bute.errors import DwnError

    e = Entry.create(EntryType.TASK, "trashed original")
    save_entry(e)
    trash_entry(e.id)
    trashed_path = trash_dir() / f"{e.id}.md"
    assert trashed_path.exists()

    # A file with the same ULID has since reappeared at the live destination.
    e2 = Entry.create(EntryType.TASK, "live occupant")
    e2.id = e.id
    save_entry(e2)
    live_path = entry_path_from_id(e.id)
    assert live_path is not None
    live_content = live_path.read_text()

    with pytest.raises(DwnError):
        restore_entry(e.id)

    # Neither copy was destroyed by the failed restore attempt.
    assert live_path.read_text() == live_content
    assert trashed_path.exists()


# --- CLI ---


def test_delete_action_moves_to_trash(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "delete me")
    save_entry(e)
    runner.invoke(main, ["t", "-b"])
    result = runner.invoke(main, ["1", "delete"])
    assert result.exit_code == 0, result.output
    assert (trash_dir() / f"{e.id}.md").exists()
    assert entry_path_from_id(e.id) is None


def test_trash_view_lists_and_saves_state(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "in the bin")
    save_entry(e)
    trash_entry(e.id)

    result = runner.invoke(main, ["trash"])
    assert result.exit_code == 0, result.output
    assert "in the bin" in result.output
    state = json.loads(state_path().read_text())
    assert state["view"] == "trash"
    assert state["entries"] == [e.id]


def test_trash_view_empty(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["trash"])
    assert result.exit_code == 0
    assert "Trash is empty" in result.output


def test_empty_trash_view_preserves_previous_numbering(runner, tmp_config, tmp_data):
    """`bt trash` on an empty trash must not clobber the last view's number map."""
    e = Entry.create(EntryType.TASK, "still numbered")
    save_entry(e)
    runner.invoke(main, ["t", "-b"])
    before = json.loads(state_path().read_text())

    runner.invoke(main, ["trash"])

    assert json.loads(state_path().read_text()) == before


def test_trash_view_empty_json(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["trash", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"view": "Trash", "entries": []}


def test_restore_action_from_trash_view(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.NOTE, "restore me")
    save_entry(e)
    trash_entry(e.id)
    runner.invoke(main, ["trash"])

    result = runner.invoke(main, ["1", "restore"])
    assert result.exit_code == 0, result.output
    assert "restore" in result.output
    assert entry_path_from_id(e.id) is not None
    assert list_trash() == []


def test_restore_action_outside_trash_view_errors(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "live one")
    save_entry(e)
    runner.invoke(main, ["t", "-b"])
    result = runner.invoke(main, ["1", "restore"])
    assert "not in the trash" in result.output


def test_undo_after_delete_restores_from_trash(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "oops")
    save_entry(e)
    runner.invoke(main, ["t", "-b"])
    runner.invoke(main, ["1", "delete"])
    assert entry_path_from_id(e.id) is None

    result = runner.invoke(main, ["undo"])
    assert result.exit_code == 0, result.output
    assert entry_path_from_id(e.id) is not None
    assert list_trash() == []


def test_trash_purge_with_yes_deletes_files(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "gone for good")
    save_entry(e)
    trash_entry(e.id)

    result = runner.invoke(main, ["trash", "purge", "-y"])
    assert result.exit_code == 0, result.output
    assert list_trash() == []
    assert not (trash_dir() / f"{e.id}.md").exists()


def test_trash_purge_prompts_and_aborts_on_no(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "keep me")
    save_entry(e)
    trash_entry(e.id)

    result = runner.invoke(main, ["trash", "purge"], input="n\n")
    assert result.exit_code == 0
    assert (trash_dir() / f"{e.id}.md").exists()


def test_trash_empty_points_to_purge(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "not yet")
    save_entry(e)
    trash_entry(e.id)

    result = runner.invoke(main, ["trash", "empty", "-y"])
    assert result.exit_code != 0
    assert "bt trash purge" in result.output
    assert (trash_dir() / f"{e.id}.md").exists()


def _trash_two():
    a = Entry.create(EntryType.TASK, "first")
    save_entry(a)
    time.sleep(0.002)
    b = Entry.create(EntryType.NOTE, "second")
    save_entry(b)
    trash_entry(a.id)
    trash_entry(b.id)
    return a, b


def test_purge_action_deletes_only_selected(runner, tmp_config, tmp_data):
    _trash_two()
    runner.invoke(main, ["trash"])
    ids = json.loads(state_path().read_text())["entries"]

    result = runner.invoke(main, ["1", "purge", "-y"])
    assert result.exit_code == 0, result.output
    assert not (trash_dir() / f"{ids[0]}.md").exists()
    assert (trash_dir() / f"{ids[1]}.md").exists()


def test_purge_action_prompts_and_aborts_on_no(runner, tmp_config, tmp_data):
    a, b = _trash_two()
    runner.invoke(main, ["trash"])

    result = runner.invoke(main, ["1-2", "purge"], input="n\n")
    assert result.exit_code == 0, result.output
    assert len(list_trash()) == 2


def test_purge_action_outside_trash_view_errors(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "live one")
    save_entry(e)
    runner.invoke(main, ["t", "-b"])
    result = runner.invoke(main, ["1", "purge", "-y"])
    assert "not in the trash" in result.output
    assert entry_path_from_id(e.id) is not None
