# Type-Based Storage Restructuring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure entry storage from `entries/YYYY-MM/ULID.md` to `entries/{type}/YYYY-MM/ULID.md` for better AI agent access by entry type.

**Architecture:** Four storage path functions in `storage.py` change to include `entry.type.value` in the path. A migration module detects old structure and moves files on first run. The README.md in the data directory becomes auto-generated with live stats.

**Tech Stack:** Python, pathlib, frontmatter, Click, Rich, zipfile

---

### Task 1: Update `entry_path()` and `save_entry()` path construction

**Files:**
- Modify: `src/bute/storage.py:12-17`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing test for new path structure**

In `tests/test_storage.py`, add:

```python
def test_save_path_includes_type(tmp_data):
    entry = Entry.create(EntryType.TASK, "test path")
    path = save_entry(entry)
    # Path should be: tmp_data/entries/task/YYYY-MM/<ulid>.md
    assert "/entries/task/" in str(path)


def test_save_path_note_type(tmp_data):
    entry = Entry.create(EntryType.NOTE, "test note path")
    path = save_entry(entry)
    assert "/entries/note/" in str(path)


def test_save_path_journal_type(tmp_data):
    entry = Entry.create(EntryType.JOURNAL, "test journal path")
    path = save_entry(entry)
    assert "/entries/journal/" in str(path)


def test_save_path_calendar_type(tmp_data):
    entry = Entry.create(EntryType.CALENDAR, "test calendar path")
    path = save_entry(entry)
    assert "/entries/calendar/" in str(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storage.py::test_save_path_includes_type tests/test_storage.py::test_save_path_note_type tests/test_storage.py::test_save_path_journal_type tests/test_storage.py::test_save_path_calendar_type -v`

Expected: FAIL — paths contain `entries/YYYY-MM/` not `entries/task/YYYY-MM/`

- [ ] **Step 3: Update `entry_path()` in `storage.py`**

Change `storage.py:12-17` from:

```python
def entry_path(entry: Entry, config=None) -> Path:
    """Compute the file path for an entry: ~/bute/entries/YYYY-MM/<ulid>.md"""
    data_dir = get_data_dir(config)
    month_dir = data_dir / "entries" / entry.created.strftime("%Y-%m")
    filename = f"{entry.id}.md"
    return month_dir / filename
```

To:

```python
def entry_path(entry: Entry, config=None) -> Path:
    """Compute the file path for an entry: entries/{type}/YYYY-MM/<ulid>.md"""
    data_dir = get_data_dir(config)
    month_dir = data_dir / "entries" / entry.type.value / entry.created.strftime("%Y-%m")
    filename = f"{entry.id}.md"
    return month_dir / filename
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -v`

Expected: All tests pass. Existing roundtrip tests still work because `save_entry` calls `entry_path` and `load_entry` takes a path directly.

- [ ] **Step 5: Update `test_save_path_structure` test**

The existing test at `tests/test_storage.py:32-37` checks `"entries" in str(path)` — this still passes but should be more specific. Update it:

```python
def test_save_path_structure(tmp_data):
    entry = Entry.create(EntryType.TASK, "test")
    path = save_entry(entry)
    # Path should be: tmp_data/entries/task/YYYY-MM/<ulid>.md
    assert "/entries/task/" in str(path)
    assert entry.id in path.name
```

- [ ] **Step 6: Run all storage tests**

Run: `uv run pytest tests/test_storage.py -v`

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/bute/storage.py tests/test_storage.py
git commit -m "feat: entry_path includes type in directory structure"
```

---

### Task 2: Update `entry_path_from_id()` to search across type dirs

**Files:**
- Modify: `src/bute/storage.py:142-153`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing test**

In `tests/test_storage.py`, add:

```python
from bute.storage import entry_path_from_id


def test_entry_path_from_id_finds_task(tmp_data):
    entry = Entry.create(EntryType.TASK, "findable task")
    save_entry(entry)
    path = entry_path_from_id(entry.id)
    assert path is not None
    assert path.exists()
    assert "/entries/task/" in str(path)


def test_entry_path_from_id_finds_journal(tmp_data):
    entry = Entry.create(EntryType.JOURNAL, "findable journal")
    save_entry(entry)
    path = entry_path_from_id(entry.id)
    assert path is not None
    assert "/entries/journal/" in str(path)


def test_entry_path_from_id_returns_none_for_missing(tmp_data):
    path = entry_path_from_id("01ZZZZZZZZZZZZZZZZZZZZZZZZ")
    assert path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storage.py::test_entry_path_from_id_finds_task tests/test_storage.py::test_entry_path_from_id_finds_journal -v`

Expected: FAIL — old `entry_path_from_id` looks in `entries/YYYY-MM/` not `entries/{type}/YYYY-MM/`

- [ ] **Step 3: Update `entry_path_from_id()` in `storage.py`**

Change `storage.py:142-153` from:

```python
def entry_path_from_id(entry_id: str, config=None) -> Path | None:
    """Find an entry file by ULID. Derives month from ULID timestamp."""
    from ulid import ULID

    ulid = ULID.from_str(entry_id)
    ts = ulid.datetime
    data_dir = get_data_dir(config)
    month_dir = data_dir / "entries" / ts.strftime("%Y-%m")
    candidate = month_dir / f"{entry_id}.md"
    if candidate.exists():
        return candidate
    return None
```

To:

```python
ENTRY_TYPE_DIRS = ["task", "note", "journal", "calendar"]


def entry_path_from_id(entry_id: str, config=None) -> Path | None:
    """Find an entry file by ULID. Checks all type dirs for the entry."""
    from ulid import ULID

    ulid = ULID.from_str(entry_id)
    ts = ulid.datetime
    data_dir = get_data_dir(config)
    month = ts.strftime("%Y-%m")
    for type_name in ENTRY_TYPE_DIRS:
        candidate = data_dir / "entries" / type_name / month / f"{entry_id}.md"
        if candidate.exists():
            return candidate
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -v`

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/bute/storage.py tests/test_storage.py
git commit -m "feat: entry_path_from_id searches across type directories"
```

---

### Task 3: Update `load_entries_by_date()` to scan all type dirs

**Files:**
- Modify: `src/bute/storage.py:82-93`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing test**

In `tests/test_storage.py`, add:

```python
from bute.storage import load_entries_by_date


def test_load_entries_by_date_across_types(tmp_data):
    from datetime import date, datetime, timezone

    # Create entries of different types, all "today"
    task = Entry.create(EntryType.TASK, "today task")
    note = Entry.create(EntryType.NOTE, "today note")
    journal = Entry.create(EntryType.JOURNAL, "today journal")
    for e in [task, note, journal]:
        save_entry(e)

    entries = load_entries_by_date(date.today())
    types = {e.type for e in entries}
    assert EntryType.TASK in types
    assert EntryType.NOTE in types
    assert EntryType.JOURNAL in types
    assert len(entries) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage.py::test_load_entries_by_date_across_types -v`

Expected: FAIL — old function only looks in one month dir, not across type dirs.

- [ ] **Step 3: Update `load_entries_by_date()` in `storage.py`**

Change `storage.py:82-93` from:

```python
def load_entries_by_date(target_date: date, config=None) -> list[Entry]:
    """Load all entries created on a specific date, sorted chronologically."""
    data_dir = get_data_dir(config)
    month_dir = data_dir / "entries" / target_date.strftime("%Y-%m")
    if not month_dir.exists():
        return []
    entries = []
    for path in month_dir.glob("*.md"):
        entry = load_entry(path)
        if entry.created.date() == target_date and entry.status != TaskStatus.DROPPED:
            entries.append(entry)
    return sorted(entries, key=lambda e: e.created)
```

To:

```python
def load_entries_by_date(target_date: date, config=None) -> list[Entry]:
    """Load all entries created on a specific date, sorted chronologically."""
    data_dir = get_data_dir(config)
    month = target_date.strftime("%Y-%m")
    entries = []
    for type_name in ENTRY_TYPE_DIRS:
        month_dir = data_dir / "entries" / type_name / month
        if not month_dir.exists():
            continue
        for path in month_dir.glob("*.md"):
            entry = load_entry(path)
            if entry.created.date() == target_date and entry.status != TaskStatus.DROPPED:
                entries.append(entry)
    return sorted(entries, key=lambda e: e.created)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -v`

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/bute/storage.py tests/test_storage.py
git commit -m "feat: load_entries_by_date scans across type directories"
```

---

### Task 4: Update `load_entries_by_filter()` to scan type/month nesting

**Files:**
- Modify: `src/bute/storage.py:96-112`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing test**

In `tests/test_storage.py`, add:

```python
from bute.storage import load_entries_by_filter


def test_load_entries_by_filter_finds_all_types(tmp_data):
    task = Entry.create(EntryType.TASK, "filter task")
    note = Entry.create(EntryType.NOTE, "filter note")
    for e in [task, note]:
        save_entry(e)

    entries = load_entries_by_filter(lambda e: True)
    assert len(entries) == 2
    types = {e.type for e in entries}
    assert EntryType.TASK in types
    assert EntryType.NOTE in types
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage.py::test_load_entries_by_filter_finds_all_types -v`

Expected: FAIL — old function iterates `entries/` expecting month dirs at top level.

- [ ] **Step 3: Update `load_entries_by_filter()` in `storage.py`**

Change `storage.py:96-112` from:

```python
def load_entries_by_filter(
    predicate: "Callable[[Entry], bool]", config=None
) -> list[Entry]:
    """Load all entries matching a predicate, sorted newest first."""
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return []
    entries = []
    for month_dir in sorted(entries_dir.iterdir()):
        if not month_dir.is_dir():
            continue
        for path in month_dir.glob("*.md"):
            entry = load_entry(path)
            if predicate(entry):
                entries.append(entry)
    return sorted(entries, key=lambda e: e.created, reverse=True)
```

To:

```python
def load_entries_by_filter(
    predicate: "Callable[[Entry], bool]", config=None
) -> list[Entry]:
    """Load all entries matching a predicate, sorted newest first."""
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return []
    entries = []
    for type_name in ENTRY_TYPE_DIRS:
        type_dir = entries_dir / type_name
        if not type_dir.exists():
            continue
        for month_dir in sorted(type_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for path in month_dir.glob("*.md"):
                entry = load_entry(path)
                if predicate(entry):
                    entries.append(entry)
    return sorted(entries, key=lambda e: e.created, reverse=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -v`

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/bute/storage.py tests/test_storage.py
git commit -m "feat: load_entries_by_filter scans type/month directory nesting"
```

---

### Task 5: Fix undo delete path construction in `action.py`

**Files:**
- Modify: `src/bute/commands/action.py:258-267`
- Test: `tests/test_storage.py` (or a new action test — but the path fix is straightforward)

- [ ] **Step 1: Write failing test**

In `tests/test_storage.py`, add:

```python
def test_delete_and_undo_roundtrip(tmp_data):
    """Delete then undo should restore entry to the type-based path."""
    from bute.commands.action import handle_delete, apply_undo
    from bute.state import pop_undo

    entry = Entry.create(EntryType.NOTE, "will be deleted")
    save_entry(entry)
    original_path = entry_path_from_id(entry.id)
    assert original_path is not None

    handle_delete(entry, [], None)
    assert entry_path_from_id(entry.id) is None

    from bute.state import _undo_path
    import json
    undo_data = json.loads(_undo_path(None).read_text())
    apply_undo(undo_data, None)

    restored_path = entry_path_from_id(entry.id)
    assert restored_path is not None
    assert "/entries/note/" in str(restored_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage.py::test_delete_and_undo_roundtrip -v`

Expected: FAIL — undo restores to `entries/YYYY-MM/` not `entries/note/YYYY-MM/`

- [ ] **Step 3: Update `apply_undo()` in `action.py`**

Change `action.py:258-267` from:

```python
        created = post.metadata.get("created", "")
        if isinstance(created, str):
            from datetime import datetime
            created = datetime.fromisoformat(created)
        month_dir = data_dir / "entries" / created.strftime("%Y-%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        restored_path = month_dir / f"{entry_id}.md"
```

To:

```python
        created = post.metadata.get("created", "")
        if isinstance(created, str):
            from datetime import datetime
            created = datetime.fromisoformat(created)
        entry_type = post.metadata.get("type", "note")
        month_dir = data_dir / "entries" / entry_type / created.strftime("%Y-%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        restored_path = month_dir / f"{entry_id}.md"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage.py::test_delete_and_undo_roundtrip -v`

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/bute/commands/action.py tests/test_storage.py
git commit -m "fix: undo delete restores to type-based path"
```

---

### Task 6: Fix `_has_entries()` in `tour.py`

**Files:**
- Modify: `src/bute/commands/tour.py:338-348`

- [ ] **Step 1: Update `_has_entries()` to handle deeper nesting**

Change `tour.py:338-348` from:

```python
def _has_entries(config) -> bool:
    """Check if any entries exist on disk."""
    from bute.config import get_data_dir
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return False
    for month_dir in entries_dir.iterdir():
        if month_dir.is_dir() and any(month_dir.glob("*.md")):
            return True
    return False
```

To:

```python
def _has_entries(config) -> bool:
    """Check if any entries exist on disk."""
    from bute.config import get_data_dir
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return False
    return any(entries_dir.rglob("*.md"))
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest -v`

Expected: All pass. The `rglob` approach works with any nesting depth.

- [ ] **Step 3: Commit**

```bash
git add src/bute/commands/tour.py
git commit -m "fix: _has_entries uses rglob for type-based directory nesting"
```

---

### Task 7: Auto-migration module

**Files:**
- Create: `src/bute/migration.py`
- Test: `tests/test_migration.py`

- [ ] **Step 1: Write failing test for migration detection**

Create `tests/test_migration.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_migration.py -v`

Expected: FAIL — `bute.migration` module does not exist.

- [ ] **Step 3: Implement `needs_migration()` in `migration.py`**

Create `src/bute/migration.py`:

```python
"""Storage migration — moves entries from month-first to type-first layout."""

import re

from bute.config import get_data_dir

MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def needs_migration(config=None) -> bool:
    """Check if entries/ contains old-style YYYY-MM dirs at the top level."""
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return False
    for child in entries_dir.iterdir():
        if child.is_dir() and MONTH_PATTERN.match(child.name):
            if any(child.glob("*.md")):
                return True
    return False
```

- [ ] **Step 4: Run detection tests**

Run: `uv run pytest tests/test_migration.py::test_needs_migration_old_structure tests/test_migration.py::test_needs_migration_new_structure tests/test_migration.py::test_needs_migration_empty -v`

Expected: All pass.

- [ ] **Step 5: Write failing test for migration**

Add to `tests/test_migration.py`:

```python
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
        id="01FFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"[:26],
        created=datetime.now(timezone.utc).isoformat(),
    )
    path = month_dir / "01FFFFFFFFFFFFFFFFFFFFFF.md"
    path.write_text(frontmatter.dumps(post))

    result = migrate_entries(None)
    assert result["note"] == 1
    assert (tmp_data / "entries" / "note" / "2026-04" / "01FFFFFFFFFFFFFFFFFFFFFF.md").exists()
```

- [ ] **Step 6: Run migration tests to verify they fail**

Run: `uv run pytest tests/test_migration.py::test_migrate_moves_files_to_type_dirs -v`

Expected: FAIL — `migrate_entries` not yet implemented.

- [ ] **Step 7: Implement `migrate_entries()` in `migration.py`**

Add to `src/bute/migration.py`:

```python
import zipfile
from datetime import date
from pathlib import Path

import frontmatter as fm

from bute.config import get_data_dir


def migrate_entries(config=None) -> dict:
    """Move entries from entries/YYYY-MM/ to entries/{type}/YYYY-MM/.

    Returns a dict with counts: {"task": N, "note": N, ..., "total": N}
    """
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"

    # Backup first
    _backup_entries(data_dir, entries_dir)

    counts = {"task": 0, "note": 0, "journal": 0, "calendar": 0, "total": 0}

    # Find old-style month dirs
    old_month_dirs = [
        d for d in sorted(entries_dir.iterdir())
        if d.is_dir() and MONTH_PATTERN.match(d.name)
    ]

    for month_dir in old_month_dirs:
        for md_file in month_dir.glob("*.md"):
            try:
                post = fm.load(str(md_file))
                entry_type = post.metadata.get("type", "note")
                if entry_type not in counts:
                    entry_type = "note"
            except Exception:
                entry_type = "note"

            new_dir = entries_dir / entry_type / month_dir.name
            new_dir.mkdir(parents=True, exist_ok=True)
            new_path = new_dir / md_file.name
            md_file.rename(new_path)

            counts[entry_type] += 1
            counts["total"] += 1

        # Remove empty old month dir
        if not any(month_dir.iterdir()):
            month_dir.rmdir()

    return counts


def _backup_entries(data_dir: Path, entries_dir: Path) -> Path:
    """Zip the entries directory before migration."""
    today = date.today().isoformat()
    backup_path = data_dir / f"entries-backup-{today}.zip"
    counter = 1
    while backup_path.exists():
        counter += 1
        backup_path = data_dir / f"entries-backup-{today}-{counter}.zip"

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(entries_dir.rglob("*")):
            if file_path.is_file():
                arcname = str(file_path.relative_to(data_dir))
                zf.write(file_path, arcname)

    return backup_path
```

- [ ] **Step 8: Run all migration tests**

Run: `uv run pytest tests/test_migration.py -v`

Expected: All pass.

- [ ] **Step 9: Commit**

```bash
git add src/bute/migration.py tests/test_migration.py
git commit -m "feat: auto-migration from month-first to type-first storage layout"
```

---

### Task 8: Wire migration into CLI startup

**Files:**
- Modify: `src/bute/cli.py:407-417`

- [ ] **Step 1: Add migration check after config load**

In `src/bute/cli.py`, after the config is loaded (line 417: `ctx.obj["config"] = config`), add migration check. Change:

```python
    if "config" in ctx.obj:
        config = ctx.obj["config"]
    else:
        from bute.config import load_config
        config = load_config()
        ctx.obj["config"] = config
```

To:

```python
    if "config" in ctx.obj:
        config = ctx.obj["config"]
    else:
        from bute.config import load_config
        config = load_config()
        ctx.obj["config"] = config

    # One-time migration: month-first → type-first storage layout
    if not ctx.obj.get("_migrated"):
        from bute.migration import needs_migration, migrate_entries
        if needs_migration(config):
            from rich.console import Console
            console = Console()
            result = migrate_entries(config)
            console.print(f"\n  [green]Migrated {result['total']} entries "
                          f"({result['task']} tasks, {result['note']} notes, "
                          f"{result['journal']} journals, {result['calendar']} calendar)[/green]")
            console.print(f"  [dim]Backup saved to ~/bullet-terminal/entries-backup-*.zip[/dim]\n")
        ctx.obj["_migrated"] = True
```

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -v`

Expected: All pass. The migration check is a no-op when `entries/` has no old-style month dirs.

- [ ] **Step 3: Commit**

```bash
git add src/bute/cli.py
git commit -m "feat: wire auto-migration into CLI startup"
```

---

### Task 9: Auto-generated README with live stats

**Files:**
- Modify: `src/bute/guide.py` (replace static GUIDE with dynamic generation)
- Modify: `src/bute/config.py:117-126` (`ensure_data_dirs` calls `write_guide`)
- Modify: `src/bute/commands/search.py:203-223` (`rebuild_cmd` should also regenerate README)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

In `tests/test_config.py`, add:

```python
def test_generated_readme_contains_stats(tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "task one"))
    save_entry(Entry.create(EntryType.TASK, "task two"))
    save_entry(Entry.create(EntryType.NOTE, "note one"))
    save_entry(Entry.create(EntryType.JOURNAL, "journal one"))

    from bute.guide import write_guide
    write_guide(tmp_data)

    readme = (tmp_data / "README.md").read_text()
    assert "task" in readme.lower()
    assert "note" in readme.lower()
    assert "entries/" in readme
    # Should contain type-first directory structure
    assert "task/" in readme or "entries/task/" in readme
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_generated_readme_contains_stats -v`

Expected: FAIL — current README is static and doesn't have live stats.

- [ ] **Step 3: Rewrite `guide.py` with dynamic README generation**

Replace the entire contents of `src/bute/guide.py` with:

```python
"""AI agent guide — generates README.md for the data directory."""

from collections import Counter
from pathlib import Path

import frontmatter


def _count_entries(entries_dir: Path) -> dict:
    """Scan entries and return counts by type and date range."""
    counts = Counter()
    earliest = None
    latest = None

    if not entries_dir.exists():
        return {"counts": counts, "earliest": earliest, "latest": latest, "total": 0}

    for md_file in entries_dir.rglob("*.md"):
        try:
            post = frontmatter.load(str(md_file))
            entry_type = post.metadata.get("type", "unknown")
            counts[entry_type] += 1
            created = post.metadata.get("created", "")
            if isinstance(created, str) and created:
                date_str = created[:10]
            else:
                date_str = str(created)[:10] if created else None
            if date_str:
                if earliest is None or date_str < earliest:
                    earliest = date_str
                if latest is None or date_str > latest:
                    latest = date_str
        except Exception:
            continue

    return {"counts": counts, "earliest": earliest, "latest": latest, "total": sum(counts.values())}


def _collect_tags(entries_dir: Path) -> list[str]:
    """Collect all unique tags across entries."""
    tags = set()
    if not entries_dir.exists():
        return []
    for md_file in entries_dir.rglob("*.md"):
        try:
            post = frontmatter.load(str(md_file))
            for tag in post.metadata.get("tags", []):
                tags.add(str(tag))
        except Exception:
            continue
    return sorted(tags)


def generate_readme(data_dir: Path) -> str:
    """Generate the README.md content with live stats."""
    entries_dir = data_dir / "entries"
    stats = _count_entries(entries_dir)
    tags = _collect_tags(entries_dir)

    # Build type folder tree
    type_dirs = ""
    for type_name in ["task", "note", "journal", "calendar"]:
        count = stats["counts"].get(type_name, 0)
        type_dirs += f"│   ├── {type_name}/              {count} entries\n"
        type_dirs += f"│   │   └── YYYY-MM/\n"
        type_dirs += f"│   │       └── <ULID>.md\n"

    date_range = ""
    if stats["earliest"] and stats["latest"]:
        date_range = f"\n**Date range:** {stats['earliest']} to {stats['latest']}\n"

    tag_list = ""
    if tags:
        tag_list = "\n### All tags\n\n" + ", ".join(f"`@{t}`" for t in tags) + "\n"

    return f"""\
# Bullet Terminal — Data Directory

This file describes the data in this directory so any AI agent can understand
and work with it. Auto-generated by bt — do not edit manually.

## What is this?

This is a Bullet Journal system stored as plain Markdown files. One file per
entry. Entries are tasks, notes, journal reflections, or calendar events.
Organized by type, then by month.

**Total entries:** {stats['total']}
{date_range}
## Directory structure

```
bullet-terminal/
├── README.md             ← you are here
├── entries/
{type_dirs}└── .index/
    └── bute.db           SQLite index (FTS5 + vectors)
```

## Entry format

Every `.md` file in `entries/` follows this structure:

```yaml
---
created: '2026-04-01T18:29:20.178347+03:00'   # ISO 8601 with timezone
id: 01KN4TKN9JPJBPP9RMYAH4GPH2               # ULID (time-sortable, 26 chars)
type: journal                                  # task | note | journal | calendar
status: active                                 # tasks only: active | done | dropped
important: true                                # optional, boolean
tags:                                          # optional, list of strings
- home-reno
- backend
due: '2026-04-10'                              # optional, tasks only, ISO date
scheduled_date: '2026-04-05'                   # optional, any type — resurface date
scheduled_time: '14:30'                        # optional, HH:MM 24h format
repeat: daily                                  # optional, recurrence pattern
extra_meta:                                    # optional, arbitrary key:value pairs
  priority: high
---

The entry body goes here. Plain text or markdown.
```

## Entry types and their BuJo signifiers

| Type     | Signifier | Purpose                                    |
|----------|-----------|-------------------------------------------|
| task     | .         | Actions to take — has a status lifecycle   |
| note     | -         | Ideas, facts, reference material           |
| journal  | =         | Reflections, feelings, stream of thought   |
| calendar | o         | Events with optional date and time         |

## Task statuses

- `active` — open, needs attention
- `done` — completed
- `dropped` — consciously abandoned (not deleted — the decision is preserved)

There is no `migrated` status. Tasks stay active until done or dropped.

## Tags

Tags are plain strings stored in the `tags` list. They serve two roles:
- **Labels** — organizing entries (`@backend`, `@health`)
- **Goals** — notes tagged `@goal` become goals; other tags on that note connect tasks to the goal

Special tags with meaning:
- `@today` — selected for the Focus Log (today's curated view)
- `@thisweek` — selected for this week's task focus
- `@goal` — marks a note as a goal
- `@habit` — marks a recurring task as a habit (tracked via `bt h`)
{tag_list}
## First sentence convention

The first sentence of an entry's body (up to the first period) serves as its
title in list views. When reading entries, treat the first sentence as the
summary. A `>` after the first sentence in views indicates more content follows.

Entries created via AI capture ("bt this") have an explicit title as the first
line, followed by a blank line, then the full body.

## IDs

Entry IDs are ULIDs — Universally Unique Lexicographically Sortable Identifiers.
They encode creation time and are 26 characters long. Sorting by ID is equivalent
to sorting by creation time.

## Reading entries

To read all entries, glob `entries/**/*.md` and parse the YAML frontmatter.
The Python `python-frontmatter` library handles this, or any YAML parser
can split on the `---` delimiters.

To read only one type: `entries/task/**/*.md`, `entries/journal/**/*.md`, etc.

To read a specific period: `entries/*/2026-04/*.md` for all April 2026 entries.

To read one type for one period: `entries/journal/2026-04/*.md`.

## Creating entries

To create a new entry:
1. Generate a ULID for the ID
2. Set `created` to the current ISO 8601 timestamp with timezone
3. Set `type` to one of: task, note, journal, calendar
4. If type is task, set `status` to `active`
5. Write the file to `entries/{{type}}/YYYY-MM/<ULID>.md` using the type and month from `created`
6. YAML frontmatter between `---` delimiters, body after

## Modifying entries

Edit the frontmatter or body in place. The file path never changes — it stays
in its original type and month folder regardless of status changes.

## Habits

Habits are recurring task entries tagged `@habit` with a `repeat` field.
They live in `entries/task/` like other tasks — no separate storage. The
`bt h` command shows today's habit status, and `bt streak` shows streaks.

## SQLite index

`.index/bute.db` is a derived index — it can be rebuilt from the `.md` files
at any time via `bt rebuild`. It contains:
- Metadata table for structured queries
- FTS5 full-text search index
- Vector embeddings for semantic search

The `.md` files are the source of truth, not the database.
"""


def write_guide(data_dir):
    """Write the README.md guide to the data directory."""
    path = data_dir / "README.md"
    content = generate_readme(data_dir)
    path.write_text(content)
    return path
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_config.py::test_generated_readme_contains_stats -v`

Expected: PASS.

- [ ] **Step 5: Update export README template**

In `src/bute/commands/export.py`, update the `README_CONTENT` string. Change:

```python
README_CONTENT = """\
# Bullet Terminal Export

This archive is a complete snapshot of your Bullet Terminal (bt) data,
exported on {date}.

## What's Inside

```
entries/          Your entries — tasks, notes, journals, calendar events
  YYYY-MM/        Organized by month
    <ULID>.md     One Markdown file per entry (YAML frontmatter + body)
```

## Entry Format

Each `.md` file in `entries/` is a standalone Markdown file with YAML
frontmatter containing structured metadata:

```yaml
---
id: 01ABC123...          # ULID (time-sortable unique ID)
type: task               # task, note, journal, or calendar
status: active           # active, done, or dropped (tasks only)
created: 2026-01-15T...  # ISO timestamp
tags:                    # Optional tags
  - backend
  - urgent
due: 2026-01-20          # Optional due date (tasks)
date: 2026-01-20         # Optional scheduled date (calendar)
time: '14:30'            # Optional scheduled time (calendar)
---

The entry body text goes here.
```

## Directory Structure Rationale

- **Month folders** (`YYYY-MM/`) keep the filesystem manageable as entries
  grow over time. ULIDs encode their creation timestamp, so entries
  naturally sort chronologically within each folder.

## Using This Export

These are plain Markdown files. You can:

- Read them in any text editor or Markdown viewer
- Import them into Obsidian, Notion, or any PKM tool
- Search them with grep, ripgrep, or your editor's search
- Reinstall Bullet Terminal and point it at these files to restore

The `.md` files are the source of truth — Bullet Terminal's SQLite
index is just a performance cache and is rebuilt automatically from
these files on first run.

## Learn More

Bullet Terminal: https://github.com/emailkgnow/bullet-terminal
"""
```

To:

```python
README_CONTENT = """\
# Bullet Terminal Export

This archive is a complete snapshot of your Bullet Terminal (bt) data,
exported on {date}.

## What's Inside

```
entries/              Your entries — organized by type, then by month
  task/
    YYYY-MM/
      <ULID>.md       Tasks — actions with a status lifecycle
  note/
    YYYY-MM/
      <ULID>.md       Notes — ideas, facts, reference material
  journal/
    YYYY-MM/
      <ULID>.md       Journals — reflections, stream of thought
  calendar/
    YYYY-MM/
      <ULID>.md       Calendar — events with optional date and time
```

## Entry Format

Each `.md` file is a standalone Markdown file with YAML frontmatter:

```yaml
---
id: 01ABC123...          # ULID (time-sortable unique ID)
type: task               # task, note, journal, or calendar
status: active           # active, done, or dropped (tasks only)
created: 2026-01-15T...  # ISO timestamp
tags:                    # Optional tags
  - backend
  - urgent
due: 2026-01-20          # Optional due date (tasks)
date: 2026-01-20         # Optional scheduled date
time: '14:30'            # Optional scheduled time
---

The entry body text goes here.
```

## Using This Export

These are plain Markdown files. You can:

- Read them in any text editor or Markdown viewer
- Import them into Obsidian, Notion, or any PKM tool
- Search them with grep, ripgrep, or your editor's search
- Reinstall Bullet Terminal and point it at these files to restore

To read one type: `entries/task/**/*.md` or `entries/journal/**/*.md`
To read one period across types: `entries/*/2026-04/*.md`

The `.md` files are the source of truth — Bullet Terminal's SQLite
index is just a performance cache and is rebuilt automatically from
these files on first run.

## Learn More

Bullet Terminal: https://github.com/emailkgnow/bullet-terminal
"""
```

- [ ] **Step 6: Add `bt readme` command and update `rebuild` to regenerate README**

In `src/bute/commands/search.py`, after the `rebuild_cmd` prints its summary (around line 222), add a README regeneration call. Add after the `console.print` lines:

```python
        from bute.guide import write_guide
        write_guide(get_data_dir(config))
```

For the `bt readme` command, add to `src/bute/commands/search.py`:

```python
@click.command("readme")
@click.pass_context
def readme_cmd(ctx):
    """Regenerate the data directory README.md."""
    config = ctx.obj.get("config")
    from bute.guide import write_guide
    path = write_guide(get_data_dir(config))
    console.print(f"  [green]README regenerated:[/green] {path}")
```

Register the command in `src/bute/cli.py` — find where other commands are registered and add `readme_cmd`.

- [ ] **Step 7: Register `readme` command in `cli.py`**

Find where commands are added to the main group in `cli.py` and add the readme command import and registration alongside the others.

- [ ] **Step 8: Run full test suite**

Run: `uv run pytest -v`

Expected: All pass.

- [ ] **Step 9: Commit**

```bash
git add src/bute/guide.py src/bute/commands/export.py src/bute/commands/search.py src/bute/cli.py tests/test_config.py
git commit -m "feat: auto-generated README with live stats, bt readme command"
```

---

### Task 10: Update `ensure_data_dirs` and documentation references

**Files:**
- Modify: `src/bute/config.py:117-126`
- Modify: `tests/test_config.py:54-59`
- Modify: `CLAUDE.md` (data model section)

- [ ] **Step 1: Update `ensure_data_dirs` — no longer needs to create flat `entries/`**

The `entries/` dir and its type subdirs are created lazily by `save_entry` via `path.parent.mkdir(parents=True, exist_ok=True)`. But `ensure_data_dirs` should still create `.index/`. Change `config.py:117-126`:

From:

```python
def ensure_data_dirs(config: tomlkit.TOMLDocument | None = None) -> Path:
    """Create the data directory structure. Returns the data dir path."""
    data_dir = get_data_dir(config)
    for subdir in ["entries", ".index"]:
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)

    from bute.guide import write_guide
    write_guide(data_dir)

    return data_dir
```

To:

```python
def ensure_data_dirs(config: tomlkit.TOMLDocument | None = None) -> Path:
    """Create the data directory structure. Returns the data dir path."""
    data_dir = get_data_dir(config)
    for subdir in ["entries", ".index"]:
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)

    from bute.guide import write_guide
    write_guide(data_dir)

    from bute.migration import needs_migration, migrate_entries
    if needs_migration(config):
        migrate_entries(config)

    return data_dir
```

- [ ] **Step 2: Update `test_ensure_data_dirs_creates_structure` in `tests/test_config.py`**

The test at line 54-59 checks for `collections` and `habits` dirs. Update to reflect current structure:

```python
def test_ensure_data_dirs_creates_structure(tmp_data):
    path = ensure_data_dirs(None)
    assert (path / "entries").is_dir()
    assert (path / ".index").is_dir()
```

- [ ] **Step 3: Update CLAUDE.md data model section**

In `CLAUDE.md`, the storage line was already updated earlier. Verify the data model section says:

```
- **Storage**: one `.md` file per entry at `~/bullet-terminal/entries/{type}/YYYY-MM/<ULID>.md`
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/bute/config.py tests/test_config.py CLAUDE.md
git commit -m "chore: update ensure_data_dirs, docs, and tests for type-based storage"
```

---

### Task 11: Reinstall and smoke test

**Files:** None (manual verification)

- [ ] **Step 1: Reinstall bt globally**

```bash
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall
```

- [ ] **Step 2: Run bt — should trigger migration**

```bash
bt
```

Expected: Migration message showing counts. Focus Log displays as normal after migration.

- [ ] **Step 3: Verify file structure**

```bash
ls ~/bullet-terminal/entries/
```

Expected: `task/`, `note/`, `journal/`, `calendar/` directories. No `YYYY-MM/` dirs at the top level.

```bash
ls ~/bullet-terminal/entries/task/
```

Expected: `2026-03/`, `2026-04/` (or whichever months have tasks).

- [ ] **Step 4: Verify backup exists**

```bash
ls ~/bullet-terminal/entries-backup-*.zip
```

Expected: One backup zip file.

- [ ] **Step 5: Verify README was regenerated**

```bash
head -20 ~/bullet-terminal/README.md
```

Expected: New format with "Organized by type, then by month" and live stats.

- [ ] **Step 6: Test core operations**

```bash
bt t new test task after migration
bt t
bt 1 done
bt undo
bt n test note after migration
bt j test journal after migration
bt d
bt rebuild
```

Expected: All commands work normally. Entries saved to type-based paths.

- [ ] **Step 7: Run full test suite one final time**

```bash
uv run pytest -v
```

Expected: All pass.

- [ ] **Step 8: Final commit if any fixes needed**

If smoke testing revealed issues, commit the fixes.
