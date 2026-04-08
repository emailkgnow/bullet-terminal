"""Tests for storage migration from month-first to type-first layout."""

import frontmatter

from bute.migration import needs_migration, migrate_entries


def _write_old_entry(data_dir, entry_type, body, entry_id, created_month="2026-04"):
    """Write an entry in the OLD layout: entries/YYYY-MM/ULID.md"""
    from datetime import datetime, timezone
    month_dir = data_dir / "entries" / created_month
    month_dir.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(
        content=body,
        id=entry_id,
        type=entry_type,
        created=datetime.now(timezone.utc).isoformat(),
        status="active" if entry_type == "task" else None,
    )
    path = month_dir / f"{entry_id}.md"
    path.write_text(frontmatter.dumps(post))
    return path


def test_needs_migration_old_structure(tmp_data):
    _write_old_entry(tmp_data, "task", "old task", "01AAAAAAAAAAAAAAAAAAAAAAAA")
    assert needs_migration(None) is True


def test_needs_migration_new_structure(tmp_data):
    type_dir = tmp_data / "entries" / "task" / "2026-04"
    type_dir.mkdir(parents=True)
    (type_dir / "01AAAAAAAAAAAAAAAAAAAAAAAA.md").write_text("test")
    assert needs_migration(None) is False


def test_needs_migration_empty(tmp_data):
    (tmp_data / "entries").mkdir(parents=True, exist_ok=True)
    assert needs_migration(None) is False


def test_migrate_moves_files_to_type_dirs(tmp_data):
    _write_old_entry(tmp_data, "task", "my task", "01AAAAAAAAAAAAAAAAAAAAAAAA")
    _write_old_entry(tmp_data, "note", "my note", "01BBBBBBBBBBBBBBBBBBBBBBBB")
    _write_old_entry(tmp_data, "journal", "my journal", "01CCCCCCCCCCCCCCCCCCCCCCCC")
    _write_old_entry(tmp_data, "calendar", "my event", "01DDDDDDDDDDDDDDDDDDDDDD")

    result = migrate_entries(None)

    assert result["task"] == 1
    assert result["note"] == 1
    assert result["journal"] == 1
    assert result["calendar"] == 1
    assert result["total"] == 4

    # Files should be in new location
    assert (tmp_data / "entries" / "task" / "2026-04" / "01AAAAAAAAAAAAAAAAAAAAAAAA.md").exists()
    assert (tmp_data / "entries" / "note" / "2026-04" / "01BBBBBBBBBBBBBBBBBBBBBBBB.md").exists()
    assert (tmp_data / "entries" / "journal" / "2026-04" / "01CCCCCCCCCCCCCCCCCCCCCCCC.md").exists()
    assert (tmp_data / "entries" / "calendar" / "2026-04" / "01DDDDDDDDDDDDDDDDDDDDDD.md").exists()

    # Old month dir should be gone
    assert not (tmp_data / "entries" / "2026-04").exists()

    # Should no longer need migration
    assert needs_migration(None) is False


def test_migrate_creates_backup(tmp_data):
    _write_old_entry(tmp_data, "task", "backup test", "01EEEEEEEEEEEEEEEEEEEEEEEE")

    migrate_entries(None)

    backups = list(tmp_data.glob("entries-backup-*.zip"))
    assert len(backups) == 1


def test_migrate_handles_missing_type(tmp_data):
    """Entry with no type field defaults to note."""
    from datetime import datetime, timezone
    month_dir = tmp_data / "entries" / "2026-04"
    month_dir.mkdir(parents=True)
    post = frontmatter.Post(
        content="no type",
        id="01FFFFFFFFFFFFFFFFFFFFFF",
        created=datetime.now(timezone.utc).isoformat(),
    )
    path = month_dir / "01FFFFFFFFFFFFFFFFFFFFFF.md"
    path.write_text(frontmatter.dumps(post))

    result = migrate_entries(None)
    assert result["note"] == 1
    assert (tmp_data / "entries" / "note" / "2026-04" / "01FFFFFFFFFFFFFFFFFFFFFF.md").exists()
