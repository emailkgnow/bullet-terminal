"""One-time moves of the SQLite index to .index/bt.db."""

from bute.db import _db_path, _migrate_index_file


def test_db_path_is_bt_db(tmp_data):
    assert _db_path().name == "bt.db"
    assert _db_path().parent == tmp_data / ".index"


def test_migrate_renames_bute_db_to_bt_db(tmp_data):
    index = tmp_data / ".index"
    index.mkdir(parents=True)
    (index / "bute.db").write_bytes(b"old-index")

    _migrate_index_file()

    assert (index / "bt.db").read_bytes() == b"old-index"
    assert not (index / "bute.db").exists()


def test_migrate_moves_vectors_db_to_bt_db(tmp_data):
    old_dir = tmp_data / ".vectors"
    old_dir.mkdir(parents=True)
    (old_dir / "bute.db").write_bytes(b"very-old-index")

    _migrate_index_file()

    assert (tmp_data / ".index" / "bt.db").read_bytes() == b"very-old-index"
    assert not old_dir.exists()


def test_migrate_keeps_existing_bt_db(tmp_data):
    index = tmp_data / ".index"
    index.mkdir(parents=True)
    (index / "bt.db").write_bytes(b"current")
    (index / "bute.db").write_bytes(b"stale")

    _migrate_index_file()

    assert (index / "bt.db").read_bytes() == b"current"


def test_migrate_is_a_noop_on_fresh_data_dir(tmp_data):
    _migrate_index_file()
    assert not (tmp_data / ".index" / "bt.db").exists()
