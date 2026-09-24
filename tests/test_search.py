"""Integration tests for rebuild and the retired like command."""

import sqlite3

from bute.cli import main
from bute.models import Entry, EntryType
from bute.storage import save_entry


def test_rebuild_indexes_entries(runner, tmp_config, tmp_data):
    """rebuild re-indexes every .md file and reports the count."""
    save_entry(Entry.create(EntryType.TASK, "call dentist"))
    save_entry(Entry.create(EntryType.NOTE, "dentist is on 5th street"))

    result = runner.invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output
    assert "2 entries indexed" in result.output
    assert "vector" not in result.output.lower()


def test_like_points_to_find(runner, tmp_config, tmp_data):
    """`bt like` was removed; typing it names the replacements."""
    result = runner.invoke(main, ["like", "fun"])
    assert result.exit_code != 0
    assert "'like' was removed" in result.output
    assert "bt find" in result.output


def test_like_absent_from_help(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0, result.output
    assert "bt like" not in result.output


def test_legacy_vec_index_is_discarded_and_rebuilt(tmp_data):
    """An index built with sqlite-vec is replaced by a fresh one.

    Its vec0 table can't be dropped without the sqlite-vec module, so bt
    deletes the derived index file and rebuilds it from the .md files.
    """
    from bute import db

    save_entry(Entry.create(EntryType.TASK, "survives the rebuild"))
    path = db._db_path()
    db.close()

    legacy = sqlite3.connect(str(path))
    legacy.execute("CREATE TABLE vec_entries (entry_id TEXT, embedding BLOB)")
    legacy.commit()
    legacy.close()

    conn = db.get_connection()
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "vec_entries" not in names
    bodies = [r[0] for r in conn.execute("SELECT body FROM entries")]
    assert bodies == ["survives the rebuild"]
