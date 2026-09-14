# Capture Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the uncommitted glow work, green the test suite, then make bt safer and faster to capture into: atomic writes, lazy embedding, a recoverable trash, visible custom metadata, `--json` output for scripts and agents, and zsh tag completion.

**Architecture:** Every change stays inside the existing layering: `storage.py` owns file I/O (atomic writes, trash moves), `db.py` owns the SQLite index (missing-vector backfill, tag listing), `display.py` owns rendering (JSON mode is a display concern so numbering matches the state file), `cli.py` owns routing (`--json` flag hoisting, `@tag` completion at the first token). No new dependencies.

**Tech Stack:** Python 3.11+, Click 8.3, Rich, python-frontmatter, SQLite (FTS5 + sqlite-vec), pytest, uv.

**Spec:** This plan was derived from a review conversation on 2026-09-14; there is no separate spec document. The "Why" line under each task is the spec for that task.

## Global Constraints

- Say **bt** in all user-facing text, help rows, README, and commit messages. Never "bute" (the package name stays `bute`).
- Run tests with `uv run pytest -q -m "not slow"`. The suite must be green at the end of every task.
- Use `uv` for everything Python. Never `pip`.
- Never call `save_config()` in a test without the `tmp_config` fixture active. It overwrites the real config.
- When the data model or folder layout changes, update `README.md` in the same commit. README is the contract external agents read.
- Reinstall globally after the last task: `uv tool install --from . --with fastembed --with sqlite-vec bute --force --reinstall`.
- Commit messages follow the existing style: `type(scope): imperative summary`. End every commit message with the two attribution lines given in the executor's session (Co-Authored-By and Claude-Session).
- Keep bt lean. If a step feels like it is adding a feature beyond the task's "Why", stop and do only what the task lists.

---

## File Map

| File | Responsibility in this plan |
|---|---|
| `src/bute/fsutil.py` (new) | `atomic_write_text(path, text)` — temp file in same dir + `os.replace` |
| `src/bute/storage.py` | use atomic writes; `trash_entry`, `restore_entry`, `list_trash`, `trash_dir` |
| `src/bute/state.py` | use atomic writes for `.state.json` and `.undo.json` |
| `src/bute/db.py` | `embed_missing_vectors(config)`; `all_tags(config)` |
| `src/bute/commands/capture.py` | drop synchronous `embed_entry` calls |
| `src/bute/ritual_ops.py` | drop synchronous `embed_entry` call |
| `src/bute/commands/action.py` | delete → trash; `restore` action; edit/mod invalidate vector instead of re-embedding |
| `src/bute/commands/search.py` | `bt like` backfills missing vectors; JSON branch |
| `src/bute/commands/trash.py` (new) | `bt trash` view and `bt trash empty` |
| `src/bute/display.py` | show `extra_meta`; JSON mode (`set_json_mode`, `json_mode`, `emit_json`) |
| `src/bute/commands/views.py` | JSON branches for `due` and `tags`; `shell_complete` on tag args |
| `src/bute/completion.py` (new) | `complete_tags(ctx, param, incomplete)`; `completion` command |
| `src/bute/cli.py` | `--json` hoisting, `DwnGroup.shell_complete`, register new commands, help rows |
| `src/bute/guide.py` | `.trash/` in directory structure |
| `README.md`, `CLAUDE.md` | folder layout, commands, BYOAI reconciliation notes |
| `tests/test_fsutil.py`, `tests/test_trash.py`, `tests/test_json_output.py`, `tests/test_completion.py` (new) | per-feature tests |
| `tests/test_export.py`, `tests/test_rituals.py`, `tests/test_action.py`, `tests/test_capture.py`, `tests/test_db.py` | fixes and additions |

---

### Task 1: Commit the glow `show` work already in the tree

**Why:** `git status` shows an uncommitted, complete feature (glow pager for `bt <n> show`, `view` alias, help row, tests). It must land before anything else is layered on top.

**Files:**
- Modify (already modified, just commit): `CLAUDE.md`, `src/bute/cli.py`, `src/bute/commands/action.py`, `tests/test_action.py`

- [x] **Step 1: Confirm the diff is only the glow work**

Run: `git diff --stat`
Expected: exactly four files — `CLAUDE.md`, `src/bute/cli.py`, `src/bute/commands/action.py`, `tests/test_action.py`. If anything else appears, stop and report.

- [x] **Step 2: Run the action tests to confirm the glow work is green**

Run: `uv run pytest -q tests/test_action.py`
Expected: all pass.

- [x] **Step 3: Commit**

```bash
git add CLAUDE.md src/bute/cli.py src/bute/commands/action.py tests/test_action.py
git commit -m "feat(show): open entry in glow pager when installed; add view alias"
```

---

### Task 2: Fix the two stale tests so the suite is green

**Why:** `test_export_includes_collections` asserts on a `collections/` folder that was removed when tags absorbed collections. `test_bt_noargs_skips_wp_when_done` predates the onboarding rule "no dp history yet → show Focus Log instead of dp" in `cli.py` (`first_day = not get_dp_history(config)`). Both are test bugs, not code bugs.

**Files:**
- Modify: `tests/test_export.py` (delete one test)
- Modify: `tests/test_rituals.py:246-275`

- [x] **Step 1: Confirm both fail today**

Run: `uv run pytest -q tests/test_export.py::test_export_includes_collections tests/test_rituals.py::test_bt_noargs_skips_wp_when_done`
Expected: 2 failed.

- [x] **Step 2: Delete the collections test**

In `tests/test_export.py`, remove the whole function `test_export_includes_collections` (from its `def` line through the final `assert any("collections/" in n for n in names)`). Nothing else in the file references collections.

- [x] **Step 3: Seed dp history in the rituals test**

In `tests/test_rituals.py`, inside `test_bt_noargs_skips_wp_when_done`, directly after the line `mark_wp_done()`, add:

```python
    # cli.py shows the Focus Log instead of dp when there is no dp history
    # at all ("first day" rule). Seed one past day so dp is expected today.
    from datetime import timedelta
    (tmp_data / ".dp_history").write_text(
        (date.today() - timedelta(days=1)).isoformat() + "\n"
    )
```

`date` is already imported at the top of the file. `tmp_data` exists as a directory by this point because `mark_wp_done()` created it.

- [x] **Step 4: Run the whole suite**

Run: `uv run pytest -q -m "not slow"`
Expected: 0 failed (386 passed, 3 skipped, give or take the deleted test).

- [x] **Step 5: Commit**

```bash
git add tests/test_export.py tests/test_rituals.py
git commit -m "test: drop stale collections export test; seed dp history in no-args ritual test"
```

---

### Task 3: Atomic file writes

**Why:** `storage.save_entry` and the state files use `Path.write_text`, which truncates then writes. A crash, or Obsidian/iCloud syncing the data dir mid-write, leaves a truncated entry. Writing to a temp file in the same directory and `os.replace`-ing it is atomic on POSIX.

**Files:**
- Create: `src/bute/fsutil.py`
- Modify: `src/bute/storage.py:20-30` (`save_entry`)
- Modify: `src/bute/state.py` (`save_state`, `record_undo`, `pop_undo`, `mark_dp_done`, `mark_wp_done`)
- Test: `tests/test_fsutil.py` (new)

**Interfaces:**
- Produces: `bute.fsutil.atomic_write_text(path: Path, text: str) -> None`

- [x] **Step 1: Write the failing tests**

Create `tests/test_fsutil.py`:

```python
"""Tests for atomic file writes."""

from pathlib import Path

from bute.fsutil import atomic_write_text


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "sub" / "entry.md"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"


def test_atomic_write_overwrites_existing(tmp_path):
    target = tmp_path / "entry.md"
    target.write_text("old")
    atomic_write_text(target, "new")
    assert target.read_text() == "new"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    target = tmp_path / "entry.md"
    atomic_write_text(target, "x")
    leftovers = [p for p in tmp_path.iterdir() if p.name != "entry.md"]
    assert leftovers == []


def test_atomic_write_failure_keeps_original(tmp_path, monkeypatch):
    import os
    target = tmp_path / "entry.md"
    target.write_text("original")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    try:
        atomic_write_text(target, "partial")
    except OSError:
        pass
    assert target.read_text() == "original"
    leftovers = [p for p in tmp_path.iterdir() if p.name != "entry.md"]
    assert leftovers == []
```

- [x] **Step 2: Run to verify they fail**

Run: `uv run pytest -q tests/test_fsutil.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'bute.fsutil'`.

- [x] **Step 3: Implement `fsutil.py`**

Create `src/bute/fsutil.py`:

```python
"""Filesystem helpers — atomic writes for entry and state files."""

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically.

    Writes to a hidden temp file in the same directory, fsyncs, then
    os.replace()s it over the target. A crash or a sync client (iCloud,
    Obsidian) reading mid-write sees either the old file or the new one,
    never a truncated one. The temp name starts with a dot and ends in
    .tmp so rglob("*.md") never matches it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
```

- [x] **Step 4: Run to verify they pass**

Run: `uv run pytest -q tests/test_fsutil.py`
Expected: 4 passed.

- [x] **Step 5: Use it in `storage.save_entry`**

In `src/bute/storage.py`, add `from bute.fsutil import atomic_write_text` to the imports, then in `save_entry` replace:

```python
    path.write_text(frontmatter.dumps(post))
```

with:

```python
    atomic_write_text(path, frontmatter.dumps(post))
```

The `path.parent.mkdir(...)` line above it can stay (harmless).

- [x] **Step 6: Use it in `state.py`**

In `src/bute/state.py`, add `from bute.fsutil import atomic_write_text` to the imports. Replace every `path.write_text(...)` and `history_path`/`with open(history_path, "a")` write with the atomic helper:

- `save_state`: `path.write_text(json.dumps(data))` → `atomic_write_text(path, json.dumps(data))`
- `mark_dp_done`: `path.write_text(date.today().isoformat())` → `atomic_write_text(path, date.today().isoformat())`; and replace the `with open(history_path, "a") as f: f.write(today_iso + "\n")` block with:

```python
    if today_iso not in existing:
        lines = sorted(existing | {today_iso})
        atomic_write_text(history_path, "\n".join(lines) + "\n")
```

- `mark_wp_done`: `path.write_text(...)` → `atomic_write_text(path, date.today().strftime("%G-W%V"))`
- `record_journal_shown`: `path.write_text("\n".join(history) + "\n")` → `atomic_write_text(path, "\n".join(history) + "\n")`
- `record_undo`: `path.write_text(json.dumps(log[-50:]))` → `atomic_write_text(path, json.dumps(log[-50:]))`
- `pop_undo`: `path.write_text(json.dumps(log))` → `atomic_write_text(path, json.dumps(log))`

- [x] **Step 7: Run the full suite**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass.

- [x] **Step 8: Commit**

```bash
git add src/bute/fsutil.py src/bute/storage.py src/bute/state.py tests/test_fsutil.py
git commit -m "fix(storage): write entry and state files atomically via temp file + os.replace"
```

---

### Task 4: Move embedding off the capture path

**Why:** Every capture loads the ONNX model (~0.3 s measured) to embed one entry, tripling capture latency. `bt like` already reconciles the index before searching; extend that to backfill any entry that has no vector. Capture, ritual capture, and undo-delete stop embedding. Edit and mod delete the stale vector instead (cheap, no model load), so it is re-embedded on the next `bt like`.

**Files:**
- Modify: `src/bute/db.py` (add `embed_missing_vectors`)
- Modify: `src/bute/commands/capture.py:109-112, 180-183`
- Modify: `src/bute/ritual_ops.py:272-275`
- Modify: `src/bute/commands/action.py:174-184` (`_reindex_entry`), `:166-172` (`handle_mod`), `:420-424` (undo delete)
- Modify: `src/bute/commands/search.py:29-34` (`like_cmd`)
- Modify: `src/bute/ai/__init__.py` (remove `embed_entry`)
- Modify: `README.md:157` (reconciliation note)
- Test: `tests/test_db.py` (add), `tests/test_capture.py` (add)

**Interfaces:**
- Produces: `bute.db.embed_missing_vectors(config=None) -> int` — number of entries embedded. Returns 0 and does nothing when embeddings are unavailable or the `vec_entries` table is missing.
- Consumes: `bute.ai.embeddings.embed_texts`, `bute.ai.vectors.upsert`, `bute.ai.is_embedding_available`.

- [x] **Step 1: Write the failing db test**

Append to `tests/test_db.py`:

```python
def test_embed_missing_vectors_noop_without_embeddings(tmp_data, monkeypatch):
    """With embeddings unavailable the backfill returns 0 and does not touch the DB."""
    from bute import db
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "needs a vector"))
    monkeypatch.setattr("bute.ai.is_embedding_available", lambda: False)
    assert db.embed_missing_vectors() == 0
    db.close()


def test_embed_missing_vectors_embeds_only_unvectored(tmp_data, monkeypatch):
    """Entries without a vec_entries row get embedded; entries with one are skipped."""
    import sqlite3
    from bute import db
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    conn = db.get_connection()
    try:
        conn.execute("SELECT COUNT(*) FROM vec_entries")
    except sqlite3.OperationalError:
        db.close()
        import pytest
        pytest.skip("sqlite-vec not installed")

    a = Entry.create(EntryType.TASK, "alpha")
    b = Entry.create(EntryType.NOTE, "beta")
    save_entry(a)
    save_entry(b)

    embedded: list[str] = []

    def fake_embed_texts(texts):
        embedded.extend(texts)
        return [[0.0] * 384 for _ in texts]

    monkeypatch.setattr("bute.ai.is_embedding_available", lambda: True)
    monkeypatch.setattr("bute.ai.embeddings.embed_texts", fake_embed_texts)

    assert db.embed_missing_vectors() == 2
    assert sorted(embedded) == ["alpha", "beta"]

    # Second call: nothing left to embed
    embedded.clear()
    assert db.embed_missing_vectors() == 0
    assert embedded == []
    db.close()
```

- [x] **Step 2: Run to verify it fails**

Run: `uv run pytest -q tests/test_db.py -k embed_missing`
Expected: FAIL with `AttributeError: module 'bute.db' has no attribute 'embed_missing_vectors'`.

- [x] **Step 3: Implement `embed_missing_vectors` in `db.py`**

Add after `reconcile_index` in `src/bute/db.py`:

```python
def embed_missing_vectors(config=None) -> int:
    """Embed every indexed entry that has no row in vec_entries.

    Capture never embeds (it would load the ONNX model on every write).
    `bt like` calls this first, so semantic search lazily catches up on
    everything captured, edited, or restored since the last search.

    Returns the number of entries embedded. 0 when embeddings are not
    installed or the vec table does not exist.
    """
    from bute.ai import is_embedding_available
    if not is_embedding_available():
        return 0

    db = get_connection(config)
    try:
        rows = db.execute(
            "SELECT entry_id, body FROM entries "
            "WHERE entry_id NOT IN (SELECT entry_id FROM vec_entries)"
        ).fetchall()
    except sqlite3.OperationalError:
        return 0
    if not rows:
        return 0

    from bute.ai.embeddings import embed_texts
    from bute.ai.vectors import upsert as vec_upsert

    ids = [r[0] for r in rows]
    vectors = embed_texts([r[1] for r in rows])
    embedded = 0
    for entry_id, vector in zip(ids, vectors):
        try:
            vec_upsert(entry_id, vector, config)
            embedded += 1
        except Exception:
            logger.debug("embed_missing_vectors: upsert failed for %s", entry_id, exc_info=True)
    return embedded
```

- [x] **Step 4: Run to verify it passes**

Run: `uv run pytest -q tests/test_db.py -k embed_missing`
Expected: 2 passed (or 1 passed + 1 skipped if sqlite-vec is absent in the test env).

- [x] **Step 5: Write the failing capture test (no model load on capture)**

Append to `tests/test_capture.py`:

```python
def test_capture_does_not_embed(runner, tmp_config, tmp_data, monkeypatch):
    """Capture must never load the embedding model — bt like backfills lazily."""
    import bute.ai.embeddings as emb

    def boom(*args, **kwargs):
        raise AssertionError("embedding model loaded during capture")

    monkeypatch.setattr(emb, "_get_model", boom)
    result = runner.invoke(main, ["t", "fast", "capture"])
    assert result.exit_code == 0, result.output
    assert "fast capture" in result.output
```

- [x] **Step 6: Run to verify it fails (only when embeddings are installed)**

Run: `uv run pytest -q tests/test_capture.py::test_capture_does_not_embed`
Expected: FAIL if fastembed + sqlite-vec are in the test env (the capture calls `embed_entry` → `_get_model`). If both are absent the test passes vacuously; continue anyway.

- [x] **Step 7: Remove the synchronous embed calls**

In `src/bute/commands/capture.py`, delete both occurrences of:

```python
    from bute.ai import embed_entry
    embed_entry(entry.id, entry.body, config)
```

(one in `capture_cmd` after `save_entry(entry, config)`, one in `open_capture_cmd` after `save_entry(edited, config)` using `edited`).

In `src/bute/ritual_ops.py`, delete:

```python
    from bute.ai import embed_entry
    embed_entry(entry.id, entry.body, config)
```

(directly after `save_entry(entry, config)` in the ritual capture helper, around line 273).

In `src/bute/commands/action.py`:

Replace `_reindex_entry` with:

```python
def _reindex_entry(path, config):
    """Re-index an entry after edits. Drops its vector so `bt like` re-embeds it."""
    updated = load_entry(path)
    try:
        from bute.db import upsert_entry
        upsert_entry(updated, config)
    except Exception:
        pass
    _invalidate_vector(updated.id, config)


def _invalidate_vector(entry_id: str, config) -> None:
    """Delete an entry's stale vector. Cheap — no model load. Re-embedded lazily."""
    try:
        from bute.ai.vectors import is_available, delete as vec_delete
        if is_available():
            vec_delete(entry_id, config)
    except Exception:
        pass
```

In `handle_mod`, after `update_entry(entry, config)` add `_invalidate_vector(entry.id, config)`.

In `apply_undo`, in the `if action == "delete":` branch, delete the two lines:

```python
        from bute.ai import embed_entry
        embed_entry(entry.id, entry.body, config)
```

- [x] **Step 8: Backfill in `bt like`**

In `src/bute/commands/search.py`, in `like_cmd`, replace:

```python
    from bute.db import reconcile_index
    reconcile_index(config, embed_new=True)
```

with:

```python
    from bute.db import embed_missing_vectors, reconcile_index
    reconcile_index(config)
    embed_missing_vectors(config)
```

- [x] **Step 9: Remove `embed_entry` from `ai/__init__.py`**

Delete the `embed_entry` function from `src/bute/ai/__init__.py`. Confirm nothing references it:

Run: `grep -rn "embed_entry" src tests`
Expected: no output.

Also remove the now-unused `embed_new` parameter and its `if embed_new and new_entries:` block from `reconcile_index` in `src/bute/db.py` (the backfill replaces it). Update the docstring paragraph that starts "When `embed_new=True`" to: "Vectors are not written here; `embed_missing_vectors()` backfills them when `bt like` runs."

Run: `grep -rn "embed_new" src tests`
Expected: no output.

- [x] **Step 10: Update README**

In `README.md`, replace the line:

```
`bt like` additionally runs the embedding step for new entries, so semantic search sees them without manual rebuild.
```

with:

```
Vectors are never written at capture time. `bt like` first embeds every indexed entry that has no vector yet (new captures, external files, edited bodies), so semantic search catches up lazily and capture stays fast.
```

- [x] **Step 11: Run the full suite**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass.

- [x] **Step 12: Commit**

```bash
git add src/bute/db.py src/bute/commands/capture.py src/bute/ritual_ops.py src/bute/commands/action.py src/bute/commands/search.py src/bute/ai/__init__.py README.md tests/test_db.py tests/test_capture.py
git commit -m "perf(capture): stop embedding on capture; bt like backfills missing vectors"
```

---

### Task 5: Recoverable trash — `delete` moves to `.trash/`, `bt trash`, `bt <n> restore`

**Why:** `bt <n> delete` unlinks the file. Undo works only while the record is within the last 50 undo entries. Moving the file to `~/bullet-terminal/.trash/` makes deletion browsable and reversible at any time, which matches the rest of bt where nothing is lost by one keystroke.

**Design:**
- `.trash/` sits beside `entries/` in the data dir (outside `entries/`, so reconciliation, export, and `rglob` in `db.py` never see it).
- Trashed files are flat: `.trash/<ULID>.md`. ULIDs are unique so no collisions.
- `bt trash` lists trashed entries newest-deleted first (file mtime) and saves state as view `trash`, so numbers map like any other view.
- `bt <n> restore` moves the file back to its `entries/{type}/YYYY-MM/` path and re-indexes. Vector is backfilled by the next `bt like`.
- `bt trash empty` permanently deletes everything in `.trash/` after a `click.confirm`. `-y` skips the prompt.
- `bt undo` after a delete restores from trash. Legacy undo records that carry `file_content` still work.

**Files:**
- Modify: `src/bute/storage.py` (add `trash_dir`, `trash_entry`, `restore_entry`, `list_trash`)
- Modify: `src/bute/commands/action.py:139-157` (`handle_delete`), `:398-431` (undo delete), action dispatch (`restore`)
- Create: `src/bute/commands/trash.py`
- Modify: `src/bute/cli.py` (register `trash_cmd`; help rows)
- Modify: `src/bute/guide.py:93-99`, `README.md:54-68, 190-216`, `CLAUDE.md`
- Test: `tests/test_trash.py` (new), `tests/test_action.py:323-336`

**Interfaces:**
- Produces:
  - `bute.storage.trash_dir(config=None) -> Path`
  - `bute.storage.trash_entry(entry_id: str, config=None) -> Path | None` — moves the live file into trash, returns new path, `None` if the entry file did not exist.
  - `bute.storage.restore_entry(entry_id: str, config=None) -> Entry` — moves back and re-indexes. Raises `DwnError` if not in trash.
  - `bute.storage.list_trash(config=None) -> list[Entry]` — newest-trashed first.

- [x] **Step 1: Write the failing storage tests**

Create `tests/test_trash.py`:

```python
"""Tests for the trash: delete moves to .trash/, bt trash lists, restore brings back."""

import json

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
    import os, time
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
    import pytest
    from bute.errors import DwnError
    e = Entry.create(EntryType.TASK, "still live")
    save_entry(e)
    with pytest.raises(DwnError):
        restore_entry(e.id)


# --- CLI ---


def test_delete_action_moves_to_trash(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "delete me")
    save_entry(e)
    runner.invoke(main, ["b"])
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
    runner.invoke(main, ["b"])
    result = runner.invoke(main, ["1", "restore"])
    assert "not in the trash" in result.output


def test_undo_after_delete_restores_from_trash(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "oops")
    save_entry(e)
    runner.invoke(main, ["b"])
    runner.invoke(main, ["1", "delete"])
    assert entry_path_from_id(e.id) is None

    result = runner.invoke(main, ["undo"])
    assert result.exit_code == 0, result.output
    assert entry_path_from_id(e.id) is not None
    assert list_trash() == []


def test_trash_empty_with_yes_deletes_files(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "gone for good")
    save_entry(e)
    trash_entry(e.id)

    result = runner.invoke(main, ["trash", "empty", "-y"])
    assert result.exit_code == 0, result.output
    assert list_trash() == []
    assert not (trash_dir() / f"{e.id}.md").exists()


def test_trash_empty_prompts_and_aborts_on_no(runner, tmp_config, tmp_data):
    e = Entry.create(EntryType.TASK, "keep me")
    save_entry(e)
    trash_entry(e.id)

    result = runner.invoke(main, ["trash", "empty"], input="n\n")
    assert result.exit_code == 0
    assert (trash_dir() / f"{e.id}.md").exists()
```

- [x] **Step 2: Run to verify they fail**

Run: `uv run pytest -q tests/test_trash.py`
Expected: FAIL with `ImportError: cannot import name 'list_trash' from 'bute.storage'`.

- [x] **Step 3: Implement the storage functions**

Append to `src/bute/storage.py`:

```python
# ---------------------------------------------------------------------------
# Trash — delete moves files here; restore moves them back
# ---------------------------------------------------------------------------


def trash_dir(config=None) -> Path:
    """Return the trash folder: <data_dir>/.trash (beside entries/, never inside)."""
    return get_data_dir(config) / ".trash"


def trash_entry(entry_id: str, config=None) -> Path | None:
    """Move an entry's .md file into .trash/ and drop it from the index.

    Returns the new path, or None if the entry file does not exist.
    """
    import shutil

    src = entry_path_from_id(entry_id, config)
    if src is None:
        return None
    dest_dir = trash_dir(config)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{entry_id}.md"
    shutil.move(str(src), str(dest))
    try:
        from bute.db import delete_entry
        delete_entry(entry_id, config)
    except Exception:
        import logging
        logging.getLogger(__name__).debug("Index delete failed for %s", entry_id[:8], exc_info=True)
    try:
        from bute.ai.vectors import is_available, delete as vec_delete
        if is_available():
            vec_delete(entry_id, config)
    except Exception:
        pass
    return dest


def restore_entry(entry_id: str, config=None) -> Entry:
    """Move a trashed entry back to entries/{type}/YYYY-MM/ and re-index it.

    Raises DwnError if the entry is not in the trash.
    """
    import shutil

    from bute.errors import DwnError

    src = trash_dir(config) / f"{entry_id}.md"
    if not src.exists():
        raise DwnError(f"Entry {entry_id[:8]} is not in the trash.")
    entry = load_entry(src)
    dest = entry_path(entry, config)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    try:
        from bute.db import upsert_entry
        upsert_entry(entry, config)
    except Exception:
        import logging
        logging.getLogger(__name__).debug("Index write failed for %s", entry_id[:8], exc_info=True)
    return entry


def list_trash(config=None) -> list[Entry]:
    """Load every trashed entry, newest-trashed (file mtime) first."""
    folder = trash_dir(config)
    if not folder.exists():
        return []
    paths = sorted(folder.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    entries: list[Entry] = []
    for path in paths:
        try:
            entries.append(load_entry(path))
        except Exception:
            continue
    return entries
```

- [x] **Step 4: Run the storage-level tests**

Run: `uv run pytest -q tests/test_trash.py -k "trash_entry or list_trash or restore_entry"`
Expected: 6 passed.

- [x] **Step 5: Rewrite `handle_delete` and the undo branch in `action.py`**

Replace `handle_delete` with:

```python
def handle_delete(entry: Entry, args: list[str], config) -> None:
    """Move an entry to .trash/ (recoverable via bt trash → bt <n> restore, or bt undo)."""
    from bute.storage import trash_entry

    trashed = trash_entry(entry.id, config)
    if trashed is not None:
        record_undo(entry.id, "delete", {"trashed": True}, config)
```

In `apply_undo`, replace the whole `if action == "delete":` block (from `if action == "delete":` through `display_action_confirmation(entry, "undo delete")` and its `return`) with:

```python
    if action == "delete":
        from bute.storage import restore_entry, trash_dir
        if (trash_dir(config) / f"{entry_id}.md").exists():
            entry = restore_entry(entry_id, config)
        else:
            # Legacy undo record from before the trash existed: recreate from saved text
            file_content = prev.get("file_content")
            if not file_content:
                raise DwnError(f"Entry {entry_id[:8]} — nothing in trash and no saved content to restore.")
            import frontmatter
            from datetime import datetime
            from bute.config import get_data_dir
            from bute.storage import load_entry as _load
            post = frontmatter.loads(file_content)
            created = post.metadata.get("created", "")
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            entry_type = post.metadata.get("type", "note")
            month_dir = get_data_dir(config) / "entries" / entry_type / created.strftime("%Y-%m")
            month_dir.mkdir(parents=True, exist_ok=True)
            restored_path = month_dir / f"{entry_id}.md"
            restored_path.write_text(file_content)
            entry = _load(restored_path)
            try:
                from bute.db import upsert_entry
                upsert_entry(entry, config)
            except Exception:
                pass
        display_action_confirmation(entry, "undo delete")
        return
```

- [x] **Step 6: Add the `restore` action**

In `action_cmd` in `src/bute/commands/action.py`, directly after the `if action == "undo":` block's `return`, add:

```python
    # Handle restore: bt <n> restore — only meaningful from the bt trash view
    if action == "restore":
        from bute.state import load_state
        from bute.storage import restore_entry
        if load_state(config).get("view") != "trash":
            console.print("  [red]Those numbers are not in the trash. Run [bold]bt trash[/bold] first.[/red]")
            return
        for entry_id in entry_ids:
            try:
                entry = restore_entry(entry_id, config)
            except DwnError as e:
                console.print(f"  [red]{e.format_message()}[/red]")
                continue
            display_action_confirmation(entry, "restore")
        return
```

Update the help row in `cli.py` for delete and add restore/trash rows. In `_print_help`, change:

```python
    t.add_row("bt <n> delete", "Permanently remove from disk", "bt 1 delete")
```

to:

```python
    t.add_row("bt <n> delete", "Move to trash (bt trash to see, restore to recover)", "bt 1 delete")
    t.add_row("bt <n> restore", "Restore from trash (after bt trash)", "bt trash → bt 1 restore")
```

And in the Views table, after the `bt find <text>` row add:

```python
    t.add_row("bt trash", "Trashed entries, newest first", "bt trash empty -y to purge")
```

- [x] **Step 7: Create the `trash` command**

Create `src/bute/commands/trash.py`:

```python
"""Trash commands — bt trash (list), bt trash empty (purge)."""

import click
from rich.console import Console

from bute.display import display_entry_list
from bute.state import save_state
from bute.storage import list_trash, trash_dir

console = Console()


@click.command("trash")
@click.argument("subcommand", required=False, default=None)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation for 'empty'.")
@click.pass_context
def trash_cmd(ctx, subcommand, yes):
    """Show trashed entries. 'bt trash empty' deletes them permanently."""
    config = ctx.obj.get("config")

    if subcommand == "empty":
        paths = list(trash_dir(config).glob("*.md")) if trash_dir(config).exists() else []
        if not paths:
            console.print("  [dim]Trash is empty.[/dim]")
            return
        if not yes and not click.confirm(f"  Permanently delete {len(paths)} trashed entries?", default=False):
            console.print("  [dim]Cancelled.[/dim]")
            return
        for p in paths:
            p.unlink()
        console.print(f"  [green]Emptied trash ({len(paths)} entries).[/green]")
        return

    if subcommand is not None:
        raise click.UsageError(f"Unknown trash subcommand: {subcommand}. Use 'bt trash' or 'bt trash empty'.")

    entries = list_trash(config)
    if not entries:
        console.print("  [dim]Trash is empty.[/dim]")
        save_state("trash", [], config)
        return

    display_entry_list(entries, "Trash")
    save_state("trash", [e.id for e in entries], config)
```

Note: `display_entry_list` sorts `entries` in place (important first). The `save_state` call after it uses the post-sort order, so numbers match.

Register it in `src/bute/cli.py`: add `from bute.commands.trash import trash_cmd  # noqa: E402` next to the other command imports, and `main.add_command(trash_cmd)` next to the other `add_command` lines.

- [x] **Step 8: Update the existing delete test**

In `tests/test_action.py`, `test_handle_delete_removes_from_db` still passes (index row removed) — leave it. No change needed; run it to confirm.

Run: `uv run pytest -q tests/test_action.py -k delete`
Expected: pass.

- [x] **Step 9: Run the trash tests**

Run: `uv run pytest -q tests/test_trash.py`
Expected: 14 passed.

- [x] **Step 10: Document the folder**

`README.md` folder layout (inside the fenced block under "### Folder layout"), add a line before `└── .index/`, changing the tree to:

```
~/bullet-terminal/
├── entries/
│   ├── task/YYYY-MM/<ULID>.md
│   ├── note/YYYY-MM/<ULID>.md
│   ├── journal/YYYY-MM/<ULID>.md
│   └── calendar/YYYY-MM/<ULID>.md
├── .trash/
│   └── <ULID>.md       # deleted entries (bt <n> delete) — flat, restorable with bt trash → bt <n> restore
└── .index/
    └── bute.db         # SQLite index (metadata + FTS5 + vectors) — regenerable
```

After the paragraph "Each entry is one file..." add:

```
External agents should ignore `.trash/`. It is outside `entries/`, so reconciliation never indexes it. To delete an entry the bt way, move its file into `.trash/` rather than unlinking it.
```

In the README Commands table, change the `bt <n> done` row's parenthetical to `(also `drop`, `delete`, `!`, `@tag`, `edit`, `later`, `focus`, `restore`)` and add a row after `bt due`:

```
| `bt trash` / `bt trash empty` | list trashed entries (restore with `bt <n> restore`) / purge them |
```

`src/bute/guide.py`: in the directory-structure block, change

```
{type_dirs}└── .index/
    └── bute.db           SQLite index (FTS5 + vectors)
```

to

```
{type_dirs}├── .trash/           deleted entries — ignore; restore with bt trash → bt <n> restore
└── .index/
    └── bute.db           SQLite index (FTS5 + vectors)
```

Check the tests in `tests/test_guide.py` still pass after this edit.

`CLAUDE.md`: in the "Actions" block change `bute 4 delete       # permanently remove from disk` to `bute 4 delete       # move to .trash/ (recoverable)` and add two lines after it:

```
bute trash          # list trashed entries (newest first); bute trash empty -y to purge
bute 2 restore      # restore entry 2 from the trash view
```

- [x] **Step 11: Run the full suite**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass.

- [x] **Step 12: Commit**

```bash
git add src/bute/storage.py src/bute/commands/action.py src/bute/commands/trash.py src/bute/cli.py src/bute/guide.py README.md CLAUDE.md tests/test_trash.py
git commit -m "feat(trash): delete moves to .trash/; add bt trash, bt <n> restore, bt trash empty"
```

---

### Task 6: Display `extra_meta` in confirmations and list views

**Why:** Custom `key:value` pairs (e.g. `bt t call bank project:alpha`) round-trip to YAML but never appear in output, so users cannot tell whether they saved. Show them as `key:value` in the meta column, after the built-in fields and before tags.

**Files:**
- Modify: `src/bute/display.py` (`confirm_capture`, `_build_entry_row`, `display_entry_full`)
- Test: `tests/test_capture.py`, `tests/test_views.py`

- [x] **Step 1: Write the failing tests**

Append to `tests/test_capture.py`:

```python
def test_capture_confirmation_shows_extra_meta(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["t", "call", "bank", "project:alpha"])
    assert result.exit_code == 0, result.output
    assert "project:alpha" in result.output
```

Append to `tests/test_views.py`:

```python
def test_list_view_shows_extra_meta(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    save_entry(Entry.create(EntryType.TASK, "call bank", extra_meta={"project": "alpha"}))
    result = runner.invoke(main, ["b"])
    assert result.exit_code == 0, result.output
    assert "project:alpha" in result.output
```

- [x] **Step 2: Run to verify they fail**

Run: `uv run pytest -q tests/test_capture.py::test_capture_confirmation_shows_extra_meta tests/test_views.py::test_list_view_shows_extra_meta`
Expected: 2 failed (`assert "project:alpha" in ...`).

- [x] **Step 3: Add a shared formatter and use it in all three renderers**

In `src/bute/display.py`, add after `_preview`:

```python
def _extra_meta_parts(entry: Entry) -> list[str]:
    """Render custom key:value frontmatter as 'key:value' strings, sorted by key."""
    return [f"{k}:{v}" for k, v in sorted(entry.extra_meta.items())]
```

In `confirm_capture`, after the `if entry.repeat:` block and before `visible_tags = ...`, add:

```python
    meta_parts.extend(_extra_meta_parts(entry))
```

In `_build_entry_row`, after the `if entry.scheduled_time:` block and before `hidden = hide_tags or set()`, add:

```python
    meta_parts.extend(_extra_meta_parts(entry))
```

In `display_entry_full`, after the `if entry.repeat:` block and before `visible_tags = ...`, add:

```python
    meta_parts.extend(_extra_meta_parts(entry))
```

- [x] **Step 4: Run to verify they pass**

Run: `uv run pytest -q tests/test_capture.py::test_capture_confirmation_shows_extra_meta tests/test_views.py::test_list_view_shows_extra_meta`
Expected: 2 passed.

- [x] **Step 5: Run the full suite and commit**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass.

```bash
git add src/bute/display.py tests/test_capture.py tests/test_views.py
git commit -m "feat(display): show custom key:value metadata in confirmations and list views"
```

Also remove the now-stale bullet from the `### Infrastructure` list in `CLAUDE.md` (the line starting `- Display \`extra_meta\``) and include `CLAUDE.md` in the commit above.

---

### Task 7: `--json` output for views

**Why:** Scripts, bots, and BYOAI agents currently scrape Rich tables to learn what bt shows. `--json` emits the same numbered list as JSON so an agent can say `bt 3 done` with the same numbers the user sees.

**Design:**
- `--json` is a group-level flag on `main`. `DwnGroup.parse_args` hoists a `--json` token from anywhere in argv to the front, so `bt b --json`, `bt --json b`, `bt t --json`, and `bt --json` all work. Hoisting happens before `resolve_command`, so `bt t --json` routes to the view, not capture.
- JSON mode lives in `display.py` as a module flag, set by `main`. `display_entry_list`, `display_entry_list_grouped`, `display_search_results` emit JSON instead of tables. This keeps numbering identical to the state file because the sort happens in the same function.
- Shape: `{"view": "<title>", "entries": [{"n": 1, "id": ..., "type": ..., "body": ..., "status": ..., "important": ..., "due": ..., "date": ..., "time": ..., "repeat": ..., "tags": [...], "focus_date": ..., "week_date": ..., "created": ..., "extra": {...}}]}`. Dates are ISO strings or `null`. `distance` is added for `bt like` results.
- `bt --json` (Focus Log) emits entries only. Habit rows and the journal whisper are skipped in JSON mode and the state is saved without them, so numbers stay aligned.
- `bt due --json` and `bt tags --json` get explicit branches because they build their own tables.

**Files:**
- Modify: `src/bute/display.py` (add `set_json_mode`, `json_mode`, `entry_to_dict`, `emit_json`; branches in three renderers)
- Modify: `src/bute/cli.py` (`parse_args` hoisting; `--json` option on `main`; Focus Log branch)
- Modify: `src/bute/commands/views.py` (`due_cmd`, `tags_cmd`)
- Modify: `src/bute/commands/search.py` (`like_cmd` header print guard)
- Modify: `README.md` (commands table), `CLAUDE.md`
- Test: `tests/test_json_output.py` (new)

**Interfaces:**
- Produces:
  - `bute.display.set_json_mode(enabled: bool) -> None`
  - `bute.display.json_mode() -> bool`
  - `bute.display.entry_to_dict(n: int, entry: Entry, **extra) -> dict`
  - `bute.display.emit_json(view: str, entries: list[Entry], extra_per_entry: list[dict] | None = None) -> None` — prints one JSON object to stdout via `click.echo`.

- [x] **Step 1: Write the failing tests**

Create `tests/test_json_output.py`:

```python
"""Tests for --json output on views."""

import json
from datetime import date

from bute.cli import main
from bute.models import Entry, EntryType
from bute.state import state_path
from bute.storage import save_entry


def _parse(output: str) -> dict:
    return json.loads(output)


def test_backlog_json_flag_after_command(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "alpha", tags=["x"], due=date(2026, 9, 20)))
    result = runner.invoke(main, ["b", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"] == "Task Backlog"
    assert len(data["entries"]) == 1
    e = data["entries"][0]
    assert e["n"] == 1
    assert e["body"] == "alpha"
    assert e["type"] == "task"
    assert e["status"] == "active"
    assert e["tags"] == ["x"]
    assert e["due"] == "2026-09-20"
    assert e["date"] is None


def test_json_flag_before_command(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "alpha"))
    result = runner.invoke(main, ["--json", "b"])
    assert result.exit_code == 0, result.output
    assert _parse(result.output)["entries"][0]["body"] == "alpha"


def test_signifier_view_with_json_is_a_view_not_capture(runner, tmp_config, tmp_data):
    """bt t --json must route to the Tasks view, not capture a task named '--json'."""
    result = runner.invoke(main, ["t", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"] == "Task Log"
    entries_dir = tmp_data / "entries"
    assert not entries_dir.exists() or list(entries_dir.rglob("*.md")) == []


def test_json_numbers_match_state(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "plain"))
    save_entry(Entry.create(EntryType.TASK, "urgent", important=True))
    result = runner.invoke(main, ["b", "--json"])
    data = _parse(result.output)
    state = json.loads(state_path().read_text())
    assert [e["id"] for e in data["entries"]] == state["entries"]
    assert data["entries"][0]["body"] == "urgent"  # important sorts first


def test_grouped_view_json(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.NOTE, "a note"))
    result = runner.invoke(main, ["n", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"] == "Notes"
    assert data["entries"][0]["body"] == "a note"


def test_empty_view_json(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["b", "--json"])
    assert result.exit_code == 0, result.output
    assert _parse(result.output) == {"view": "Task Backlog", "entries": []}


def test_focus_log_json_skips_habits_and_whisper(runner, tmp_config, tmp_data):
    from bute.config import TOUR_DONE
    TOUR_DONE.parent.mkdir(parents=True, exist_ok=True)
    TOUR_DONE.touch()
    from bute.state import mark_dp_done, mark_wp_done
    mark_dp_done()
    mark_wp_done()  # never fall into the interactive weekly plan on its trigger day
    save_entry(Entry.create(EntryType.TASK, "today task", focus_date=date.today()))
    save_entry(Entry.create(EntryType.TASK, "meditate", repeat="daily"))

    result = runner.invoke(main, ["--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"].startswith("Focus Log")
    bodies = [e["body"] for e in data["entries"]]
    assert "today task" in bodies
    # Output must be a single JSON document — no habit table or whisper appended
    assert result.output.strip().count("\n") == 0
    state = json.loads(state_path().read_text())
    assert [e["id"] for e in data["entries"]] == state["entries"]
    assert "extra_entries" not in state


def test_due_json(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "late", due=date(2020, 1, 1)))
    result = runner.invoke(main, ["due", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["view"] == "Due Tasks"
    assert data["entries"][0]["body"] == "late"
    assert data["entries"][0]["group"] == "Overdue"


def test_tags_json(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.TASK, "a", tags=["x", "y"]))
    save_entry(Entry.create(EntryType.TASK, "b", tags=["x"]))
    result = runner.invoke(main, ["tags", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data == {"view": "Tags", "tags": [{"tag": "x", "count": 2}, {"tag": "y", "count": 1}]}


def test_find_json(runner, tmp_config, tmp_data):
    save_entry(Entry.create(EntryType.NOTE, "OAuth tokens expire"))
    result = runner.invoke(main, ["find", "OAuth", "--json"])
    assert result.exit_code == 0, result.output
    data = _parse(result.output)
    assert data["entries"][0]["body"] == "OAuth tokens expire"
```

- [x] **Step 2: Run to verify they fail**

Run: `uv run pytest -q tests/test_json_output.py`
Expected: all fail (`--json` is currently either captured as text or rejected as an unknown option).

- [x] **Step 3: Add JSON mode to `display.py`**

Add near the top of `src/bute/display.py`, after `console = Console()`:

```python
import json as _json

import click

_JSON_MODE = False


def set_json_mode(enabled: bool) -> None:
    """Switch every list renderer to emit JSON instead of Rich tables."""
    global _JSON_MODE
    _JSON_MODE = enabled


def json_mode() -> bool:
    return _JSON_MODE


def entry_to_dict(n: int, entry: Entry, **extra) -> dict:
    """Serialize one entry for --json output. n is its 1-based display number."""
    d = {
        "n": n,
        "id": entry.id,
        "type": entry.type.value,
        "body": entry.body,
        "status": entry.status.value if entry.status else None,
        "important": entry.important,
        "due": entry.due.isoformat() if entry.due else None,
        "date": entry.scheduled_date.isoformat() if entry.scheduled_date else None,
        "time": entry.scheduled_time,
        "repeat": entry.repeat,
        "tags": list(entry.tags),
        "focus_date": entry.focus_date.isoformat() if entry.focus_date else None,
        "week_date": entry.week_date.isoformat() if entry.week_date else None,
        "created": entry.created.isoformat(),
        "extra": dict(entry.extra_meta),
    }
    d.update(extra)
    return d


def emit_json(view: str, entries: list[Entry], extra_per_entry: list[dict] | None = None) -> None:
    """Print {"view": ..., "entries": [...]} as one JSON document."""
    rows = []
    for i, entry in enumerate(entries, 1):
        extra = extra_per_entry[i - 1] if extra_per_entry else {}
        rows.append(entry_to_dict(i, entry, **extra))
    click.echo(_json.dumps({"view": view, "entries": rows}))
```

Then add JSON branches:

In `display_entry_list`, replace the opening `if not entries:` block and the table build with:

```python
    if not entries:
        if json_mode():
            emit_json(title, [])
            return
        if title:
            console.print(f"[bold]{title}[/bold]", justify="center")
        console.print(f"  [dim]No entries found.[/dim]")
        return

    # Stable sort: important first, done/dropped last
    entries.sort(key=_display_sort_key)

    if json_mode():
        emit_json(title, entries)
        return
```

(everything after — the `table = Table(...)` build — stays as is).

In `display_entry_list_grouped`, change the empty check to:

```python
    if not entries:
        if json_mode():
            emit_json(title, [])
        else:
            console.print(f"  [dim]No entries found.[/dim]")
        return
```

and directly after the block that rebuilds `entries` in display order (after the `for d in sorted_dates: entries.extend(grouped[d])` loop), add:

```python
    if json_mode():
        emit_json(title, entries)
        return
```

In `display_search_results`, change the empty check to:

```python
    if not entries:
        if json_mode():
            emit_json(f'Like: "{query}"' if query else "Like", [])
        else:
            console.print("  [dim]No results found.[/dim]")
        return
    if json_mode():
        emit_json(
            f'Like: "{query}"' if query else "Like",
            entries,
            [{"distance": d} for d in distances],
        )
        return
```

- [x] **Step 4: Hoist `--json` and add the option in `cli.py`**

In `DwnGroup.parse_args`, replace the body with:

```python
    def parse_args(self, ctx, args):
        """Prevent Click from treating -@tag as an option flag; hoist --json to the front."""
        args = list(args)
        if "--json" in args:
            args = ["--json"] + [a for a in args if a != "--json"]
        if args and args[0].startswith("-@"):
            args = ["--"] + args
        return super().parse_args(ctx, args)
```

On `main`, add an option between the existing `-a/--all` option and `@click.pass_context`:

```python
@click.option("--json", "as_json", is_flag=True, help="Emit views as JSON (for scripts and agents)")
```

and add `as_json` as the last parameter of `def main(ctx, interactive, demo, toggle_journal, show_all, as_json):`. At the top of the body, right after `ctx.ensure_object(dict)`, add:

```python
    if as_json:
        from bute.display import set_json_mode
        set_json_mode(True)
```

In the Focus Log branch of `main` (inside `if is_dp_done_today(config) or first_day or show_all:`), change the tail after `display_entry_list(entries, title)` to:

```python
            display_entry_list(entries, title)

            from bute.display import json_mode
            if json_mode():
                save_state("ls", [e.id for e in entries], config)
                return

            # Show recurring tasks — their IDs flow into the main entries list
            # for uniform numbering (bt <n> done works the same as for any entry)
            from bute.commands.views import _show_habits
            habit_ids = _show_habits(config, len(entries))

            entry_ids = [e.id for e in entries] + habit_ids

            # Random old journal whisper (numbered after entries + habits)
            journal_id = _show_random_journal(config, len(entry_ids))

            save_state("ls", entry_ids, config, extra_entries=[journal_id] if journal_id else None)
```

Note: in JSON mode `title` may contain `[strike]...[/strike]` markup when no tasks are active. Strip it: right before `display_entry_list(entries, title)`, add

```python
            from bute.display import json_mode as _jm
            if _jm():
                title = f"Focus Log — {date.today().strftime('%a %b %d')}{suffix}"
```

- [x] **Step 5: JSON branches for `due` and `tags`**

In `src/bute/commands/views.py`, import `emit_json, json_mode, entry_to_dict` from `bute.display` (extend the existing `from bute.display import ...` line).

In `due_cmd`: the `scope == "all"` and `scope == "overdue"` paths call `display_entry_list`, which already handles JSON. For the grouped default path, right after the `filtered = overdue + due_today + due_week` / empty check, before `# Build grouped table`, add:

```python
    if json_mode():
        ordered = overdue + due_today + due_week
        labels = (["Overdue"] * len(overdue)) + (["Today"] * len(due_today)) + (["Next 7 Days"] * len(due_week))
        emit_json("Due Tasks", ordered, [{"group": g} for g in labels])
        save_state("due", [e.id for e in ordered], config)
        return
```

Also the early `if not entries:` message in `due_cmd` (`No tasks with due dates.`) must emit `emit_json("Due Tasks", [])` when in JSON mode; and the `if not filtered:` branch the same. Apply:

```python
    if not entries:
        if json_mode():
            emit_json("Due Tasks", [])
        else:
            console.print("  [dim]No tasks with due dates.[/dim]")
        return
```

and likewise for `if not filtered:` with the message `Nothing due this week.`.

In `tags_cmd`, after `counts` is built and before `if not counts:`, add:

```python
    if json_mode():
        import json as _json
        import click as _click
        ordered = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        _click.echo(_json.dumps({"view": "Tags", "tags": [{"tag": t, "count": c} for t, c in ordered]}))
        return
```

- [x] **Step 6: Silence the `bt like` header in JSON mode**

In `src/bute/commands/search.py`, `like_cmd`, wrap the header line:

```python
        console.print(f"\n  [bold]Like:[/bold] {source_entry.body}")
```

as

```python
        from bute.display import json_mode
        if not json_mode():
            console.print(f"\n  [bold]Like:[/bold] {source_entry.body}")
```

and in the search-mode `if not results:` branch, emit JSON when in JSON mode:

```python
        if not results:
            from bute.display import emit_json, json_mode
            if json_mode():
                emit_json(f'Like: "{query_text}"', [])
            else:
                console.print("  [dim]No results found.[/dim]")
            return
```

- [x] **Step 7: Run the JSON tests**

Run: `uv run pytest -q tests/test_json_output.py`
Expected: 10 passed. If `test_focus_log_json_skips_habits_and_whisper` fails on `view`, check that the strike markup was stripped (Step 4 note).

- [x] **Step 8: Document**

`README.md` Commands table: add a row after `bt find <q>`:

```
| `bt <view> --json` | any view as JSON — same numbers as the table, so `bt 3 done` works from a script |
```

And in the "Bring Your Own AI" section, after the "The contract" list, add a short paragraph:

```
To read what bt shows without parsing tables, append `--json` to any view (`bt --json`, `bt b --json`, `bt @home --json`, `bt find x --json`). The `n` field is the number you would pass to `bt <n> done`.
```

`CLAUDE.md` Views block: add `bute b --json        # any view as JSON (n = display number)` after the `bute like` line.

`cli.py` help: in the System table add `t.add_row("bt <view> --json", "Emit any view as JSON", "bt b --json, bt @home --json")`.

- [x] **Step 9: Run the full suite and commit**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass.

```bash
git add src/bute/display.py src/bute/cli.py src/bute/commands/views.py src/bute/commands/search.py README.md CLAUDE.md tests/test_json_output.py
git commit -m "feat(views): add --json output with display numbers for scripts and agents"
```

---

### Task 8: zsh tag completion

**Why:** Click ships shell completion for free. Completing `@ba` to `@backend` in capture, action, and filter positions prevents tag drift from typos. Command-name completion (`bt ta<TAB>` → `tags tasks`) already works through Click; this task adds `@tag` values.

**Design:**
- `bute/completion.py` holds `complete_tags(ctx, param, incomplete)` returning `CompletionItem`s for every known tag when `incomplete` starts with `@`, and an empty list otherwise (so Click's default file completion never kicks in for bt).
- Tag source: new `db.all_tags(config) -> list[str]` (distinct, sorted) via `json_each`. Wrapped in try/except so completion never prints or crashes; an empty list is the failure mode.
- Attached with `shell_complete=complete_tags` on: `capture_cmd`'s `tokens`, `action_cmd`'s `tokens`, the `tag` argument of `tasks`, `backlog`, and the `_dimension_command` factory, and `tag_filter_cmd`'s `tags`.
- `DwnGroup.shell_complete` override: if `incomplete.startswith("@")` return tag items, else `super()`. This covers `bt @ba<TAB>`.
- `bt completion [zsh|bash|fish]` prints the one line to add to the shell rc. Default `zsh`.
- Tested with `click.shell_completion.ShellComplete.get_completions`, which was verified to resolve through `DwnGroup` (`bt ta<TAB>` → `tags`, `tasks`).

**Files:**
- Modify: `src/bute/db.py` (add `all_tags`)
- Create: `src/bute/completion.py`
- Modify: `src/bute/commands/capture.py`, `src/bute/commands/action.py`, `src/bute/commands/views.py` (attach `shell_complete`)
- Modify: `src/bute/cli.py` (`DwnGroup.shell_complete`, register `completion_cmd`, help row)
- Modify: `README.md` (Install section), `CLAUDE.md`
- Test: `tests/test_completion.py` (new), `tests/test_db.py` (add)

**Interfaces:**
- Produces:
  - `bute.db.all_tags(config=None) -> list[str]`
  - `bute.completion.complete_tags(ctx, param, incomplete) -> list[click.shell_completion.CompletionItem]`
  - `bute.completion.completion_cmd` (Click command named `completion`)

- [x] **Step 1: Write the failing tests**

Append to `tests/test_db.py`:

```python
def test_all_tags_distinct_sorted(tmp_data):
    from bute import db
    from bute.models import Entry, EntryType
    from bute.storage import save_entry
    save_entry(Entry.create(EntryType.TASK, "a", tags=["zeta", "alpha"]))
    save_entry(Entry.create(EntryType.NOTE, "b", tags=["alpha"]))
    save_entry(Entry.create(EntryType.NOTE, "c"))
    assert db.all_tags() == ["alpha", "zeta"]
    db.close()
```

Create `tests/test_completion.py`:

```python
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


def test_completion_command_prints_zsh_line(runner):
    result = runner.invoke(main, ["completion"])
    assert result.exit_code == 0
    assert '_BT_COMPLETE=zsh_source bt' in result.output


def test_completion_command_bash(runner):
    result = runner.invoke(main, ["completion", "bash"])
    assert result.exit_code == 0
    assert '_BT_COMPLETE=bash_source bt' in result.output
```

- [x] **Step 2: Run to verify they fail**

Run: `uv run pytest -q tests/test_completion.py tests/test_db.py::test_all_tags_distinct_sorted`
Expected: `test_all_tags_distinct_sorted` fails with AttributeError; the completion tests fail with empty lists (and `completion` → usage error).

- [x] **Step 3: Add `all_tags` to `db.py`**

Append to the Query operations section of `src/bute/db.py`:

```python
def all_tags(config=None) -> list[str]:
    """Return every distinct tag across all entries, sorted."""
    db = get_connection(config)
    rows = db.execute(
        "SELECT DISTINCT j.value FROM entries e, json_each(e.tags) j ORDER BY j.value"
    ).fetchall()
    return [r[0] for r in rows]
```

- [x] **Step 4: Create `completion.py`**

Create `src/bute/completion.py`:

```python
"""Shell completion for @tags, plus the `bt completion` helper command."""

import click
from click.shell_completion import CompletionItem


def _known_tags() -> list[str]:
    """All tags from the index. Never raises, never prints — completion must stay silent."""
    try:
        from bute.config import get_data_dir, load_config
        from bute.db import all_tags
        config = load_config()
        if not (get_data_dir(config) / ".index" / "bute.db").exists():
            return []  # a fresh DB would auto-rebuild and print — never during completion
        return all_tags(config)
    except Exception:
        return []


def complete_tags(ctx, param, incomplete: str) -> list[CompletionItem]:
    """Complete '@ba' → '@backend'. Anything not starting with '@' gets no suggestions."""
    if not incomplete.startswith("@"):
        return []
    prefix = incomplete[1:]
    return [CompletionItem(f"@{t}") for t in _known_tags() if t.startswith(prefix)]


_RC_LINE = {
    "zsh": 'eval "$(_BT_COMPLETE=zsh_source bt)"',
    "bash": 'eval "$(_BT_COMPLETE=bash_source bt)"',
    "fish": '_BT_COMPLETE=fish_source bt | source',
}
_RC_FILE = {"zsh": "~/.zshrc", "bash": "~/.bashrc", "fish": "~/.config/fish/completions/bt.fish"}


@click.command("completion")
@click.argument("shell", required=False, default="zsh", type=click.Choice(list(_RC_LINE)))
def completion_cmd(shell):
    """Print the line that enables tab completion for your shell (default zsh)."""
    click.echo(f"  Add this to {_RC_FILE[shell]}, then open a new shell:")
    click.echo()
    click.echo(f"    {_RC_LINE[shell]}")
    click.echo()
    click.echo("  Then: bt t call den @ba<TAB>  →  @backend")
```

- [x] **Step 5: Attach `shell_complete` to the arguments**

`src/bute/commands/capture.py`: add `from bute.completion import complete_tags` to imports and change the argument decorator on `capture_cmd` to:

```python
@click.argument("tokens", nargs=-1, required=True, shell_complete=complete_tags)
```

`src/bute/commands/action.py`: add `from bute.completion import complete_tags` and change the argument on `action_cmd` to:

```python
@click.argument("tokens", nargs=-1, required=True, shell_complete=complete_tags)
```

`src/bute/commands/views.py`: add `from bute.completion import complete_tags` and change every `@click.argument("tag", required=False, default=None)` (in `_dimension_command`, `tasks_cmd`, `backlog_cmd`) to:

```python
@click.argument("tag", required=False, default=None, shell_complete=complete_tags)
```

and `tag_filter_cmd`'s `@click.argument("tags", nargs=-1)` to `@click.argument("tags", nargs=-1, shell_complete=complete_tags)`.

Note: view commands receive the tag without `@` at runtime (the router strips it), but the completion item keeps the `@` because that is what the user typed. When the user then presses Enter, `bt tasks @health` routes through `DwnGroup.resolve_command` → named command `tasks` with rest `["@health"]`. Verify `tasks_cmd` strips a leading `@`: add at the top of `tasks_cmd` and `backlog_cmd` and the `_dimension_command` body:

```python
        if tag and tag.startswith("@"):
            tag = tag[1:]
```

- [x] **Step 6: First-token `@tag` completion in `DwnGroup`**

In `src/bute/cli.py`, add to `DwnGroup`:

```python
    def shell_complete(self, ctx, incomplete):
        """Complete @tags at the first position (bt @ba<TAB>); otherwise command names."""
        if incomplete.startswith("@"):
            from bute.completion import complete_tags
            return complete_tags(ctx, None, incomplete)
        return super().shell_complete(ctx, incomplete)
```

Register the command: add `from bute.completion import completion_cmd  # noqa: E402` with the command imports and `main.add_command(completion_cmd)`.

Help: in the System table add `t.add_row("bt completion [zsh|bash|fish]", "Print the shell line that enables @tag tab completion", "bt completion")`.

- [x] **Step 7: Run the completion tests**

Run: `uv run pytest -q tests/test_completion.py tests/test_db.py::test_all_tags_distinct_sorted`
Expected: 9 passed.

If `test_first_token_tag_filter_completes` fails, check that `DwnGroup.shell_complete` is being reached: Click calls `_resolve_context` then `obj.shell_complete(ctx, incomplete)` where `obj` is the group when no subcommand has been matched.

- [ ] **Step 8: Verify in a real zsh (manual, outside pytest)** — DEFERRED to user (live-zsh manual check skipped per task-8 instructions; verified programmatically instead)

Run:

```bash
uv tool install --from . --with fastembed --with sqlite-vec bute --force --reinstall
_BT_COMPLETE=zsh_source bt | head -5
```

Expected: a `#compdef bt` script is printed. Do not add it to the user's rc file; that is the user's choice.

- [x] **Step 9: Document**

`README.md` Install section: after the `bt init` bullet add:

```
- Tab completion for `@tags` and command names: run `bt completion` and add the printed line to `~/.zshrc`.
```

`CLAUDE.md` System block: add `bute completion     # print the shell line that enables @tag tab completion`.

- [x] **Step 10: Run the full suite and commit**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass.

```bash
git add src/bute/db.py src/bute/completion.py src/bute/commands/capture.py src/bute/commands/action.py src/bute/commands/views.py src/bute/cli.py README.md CLAUDE.md tests/test_completion.py tests/test_db.py
git commit -m "feat(cli): @tag shell completion and bt completion helper"
```

---

### Task 9: Final verification and reinstall

**Why:** The user's standing rule is to reinstall bt globally after code changes, and every task above touched user-facing behaviour.

- [x] **Step 1: Full suite including slow tests if embeddings are installed** — 459 passed (3 PytestUnknownMarkWarning, deferred minor)

Run: `uv run pytest -q`
Expected: all pass (slow embedding tests may take ~10 s).

- [x] **Step 2: Reinstall** — Installed 1 executable: bt

Run: `uv tool install --from . --with fastembed --with sqlite-vec bute --force --reinstall`

- [x] **Step 3: Smoke test** — run as a scripted CliRunner equivalent in an isolated temp dir (the `bt -d` REPL is not scriptable: its first-run tour consumes piped stdin). All four behaviours verified: capture shows `project:plan`, `b --json` emits one entry with n=1 and raw extra, delete lists in trash, restore returns it to the backlog.

Run:

```bash
bt -d
```

Inside the demo session (it is isolated per `bt -d`), type:

```
t smoke test project:plan @demo
b --json
1 delete
trash
1 restore
b
/exit
```

Expected: capture confirmation shows `project:plan`; the JSON has one entry; delete → trash lists it → restore brings it back → backlog shows it again.

- [x] **Step 4: Confirm the tree is clean**

Run: `git status --short`
Expected: no output. If the smoke test left files, they are in the demo dir, not the repo.

---

## Self-Review

**Coverage against the requested items:**

| Item requested | Task |
|---|---|
| 1. Two failing tests | Task 2 |
| 2. Commit glow work | Task 1 |
| 5. Embedding off capture path | Task 4 |
| 6. Shell completion for tags | Task 8 |
| 7. Atomic writes | Task 3 |
| 8. Recoverable delete + check trash + retrieve | Task 5 (`bt trash`, `bt <n> restore`, `bt trash empty`, `bt undo`) |
| 11. `--json` on views | Task 7 |
| 12. Display `extra_meta` | Task 6 |

**Placeholder scan:** none. Every code step has the code; every test step has the test.

**Type consistency:**
- `atomic_write_text(path, text)` — defined Task 3, used Task 3 only.
- `trash_dir / trash_entry / restore_entry / list_trash` — defined Task 5 Step 3, used in Steps 5–7 and tests with the same names and signatures.
- `embed_missing_vectors(config)` — defined Task 4 Step 3, called Task 4 Step 8.
- `set_json_mode / json_mode / emit_json / entry_to_dict` — defined Task 7 Step 3, used Steps 4–6.
- `complete_tags(ctx, param, incomplete)` and `all_tags(config)` — defined Task 8 Steps 3–4, used Steps 5–6.
- `_invalidate_vector(entry_id, config)` — defined and used inside Task 4 Step 7 only.

**Known judgment calls the executor should not relitigate:**
- `bt trash empty` was added beyond "check and retrieve" because a trash with no purge grows forever. It is confirmation-gated.
- JSON Focus Log omits habit rows and the journal whisper. Including them would require a second entry shape; agents that need habits can read `bt streak` later if that ever gets `--json`.
- Vectors are invalidated (deleted) on edit/mod rather than re-embedded, so edits stay fast and `bt like` catches up.
