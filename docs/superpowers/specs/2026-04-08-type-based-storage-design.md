# Type-Based Storage Restructuring

## Problem

The current storage structure (`entries/YYYY-MM/ULID.md`) organizes entries by creation month. When an AI agent needs to analyze entries by type (e.g., "analyze my journals"), it must scan every file across every month folder and filter by frontmatter — expensive in tokens and round trips at scale.

## Solution

Restructure entries to be organized by type first, then month:

```
entries/{type}/YYYY-MM/ULID.md
```

This gives AI agents direct filesystem access by entry type while preserving chronological partitioning within each type.

## New Directory Structure

```
~/bullet-terminal/
├── README.md                          ← auto-generated
├── entries/
│   ├── task/
│   │   ├── 2026-03/
│   │   │   └── <ULID>.md
│   │   └── 2026-04/
│   ├── note/
│   │   └── 2026-04/
│   ├── journal/
│   │   └── 2026-03/
│   └── calendar/
│       └── 2026-04/
└── .index/
    └── bute.db
```

- Folder names match `type:` frontmatter values exactly: `task`, `note`, `journal`, `calendar`
- Month subfolders within each type: `YYYY-MM/`
- Path formula: `entries/{entry.type.value}/{created.strftime("%Y-%m")}/{entry.id}.md`
- Month dirs created lazily on first write via `mkdir(parents=True, exist_ok=True)`

## Storage Path Changes

### `entry_path(entry, config)`

Changes from:
```python
data_dir / "entries" / entry.created.strftime("%Y-%m") / f"{entry.id}.md"
```
To:
```python
data_dir / "entries" / entry.type.value / entry.created.strftime("%Y-%m") / f"{entry.id}.md"
```

### `entry_path_from_id(entry_id, config)`

Currently derives path from ULID timestamp alone. New behavior: extract month from ULID, then check all 4 type dirs for existence. No DB dependency.

```python
month = ulid_to_month(entry_id)
for type_name in ["task", "note", "journal", "calendar"]:
    path = data_dir / "entries" / type_name / month / f"{entry_id}.md"
    if path.exists():
        return path
return None
```

Four `Path.exists()` calls — trivially fast, no DB dependency, works even when index is missing.

### `load_entries_by_date(target_date, config)`

Currently scans one month dir. New behavior: scan the month dir across all 4 type folders and combine results.

```python
month = target_date.strftime("%Y-%m")
for type_name in ["task", "note", "journal", "calendar"]:
    month_dir = data_dir / "entries" / type_name / month
    # load .md files from month_dir
```

### `load_entries_by_filter(predicate, config)`

Currently iterates `entries/` → month dirs → `*.md`. New behavior: use `rglob("*.md")` on `entries/` to find all files regardless of nesting depth. Or iterate type dirs → month dirs → `*.md`.

### `action.py` undo delete (line 265)

Direct path construction during undo. The `.undo.json` payload already stores the full entry data including `type`, so the type is available for path reconstruction.

## Auto-Migration

On first run after update, detect old structure and migrate automatically.

### Detection

Check if `entries/` contains `YYYY-MM/` dirs directly (old structure). Presence of dirs matching `^\d{4}-\d{2}$` at the top level of `entries/` triggers migration.

### Process

1. **Backup**: Zip `entries/` to `entries-backup-YYYY-MM-DD.zip` in the data dir
2. **Read and move**: For each `.md` file in old `entries/YYYY-MM/` dirs, read frontmatter `type:`, move to `entries/{type}/YYYY-MM/`
3. **Cleanup**: Remove empty old month dirs after all files are moved
4. **Log**: Print summary — e.g., "Migrated 215 entries (131 tasks, 35 notes, 35 journals, 15 calendar)"

### Edge Cases

- Entry with no `type:` in frontmatter: default to `note`, print warning
- Migration interrupted: backup exists, user can restore manually. Re-running detects remaining old-structure dirs and continues.

### Trigger

Called early in CLI startup — either within `ensure_data_dirs()` or as a dedicated `migrate_if_needed()` function called from the CLI entry point.

## README Auto-Generation

A `generate_readme(config)` function that writes `~/bullet-terminal/README.md` with current data stats.

### Triggers

- `bt rebuild` — natural fit, already a "reindex everything" command
- After auto-migration completes
- `bt readme` — new command for manual regeneration

### Content

- What this directory is and what bt is
- Directory structure (reflecting actual type folders found on disk)
- Entry format and frontmatter schema (all fields documented)
- Entry types and BuJo signifiers
- Task statuses
- Tag conventions (special tags: `@today`, `@thisweek`, `@goal`, `@habit`)
- How to read, create, and modify entries (for AI agents)
- Live stats: entry counts per type, date range, tag list

The function scans the actual filesystem to generate stats rather than hardcoding values.

## What Doesn't Change

- **`db.py` rebuild** — already uses `rglob("*.md")`, works with deeper nesting
- **`export.py`** — already uses `rglob("*")` under `entries/`, captures new structure automatically
- **SQLite schema** — stores no file paths, unaffected
- **Frontmatter format** — identical, `type:` field unchanged
- **CLI grammar** — no user-facing command changes
- **Entry IDs** — ULIDs unchanged
- **`.state.json`** — stores ULIDs, not paths
- **Linelog** — separate `linelog/` directory, untouched

## Files to Modify

| File | Change | Severity |
|------|--------|----------|
| `storage.py` | `entry_path()`, `load_entries_by_date()`, `load_entries_by_filter()`, `entry_path_from_id()` | Critical |
| `action.py` | Undo delete path construction (line 265) | Critical |
| `tour.py` | `_has_entries()` — assumes 1-level nesting (line 345) | High |
| `config.py` | `ensure_data_dirs()` — create type subdirs or add migration call | Medium |
| `guide.py` | Documentation strings referencing path structure | Medium |
| `export.py` | README template strings | Medium |
| Tests | Path assertions in `test_storage.py`, `test_export.py` | Medium |

## New Files

| File | Purpose |
|------|---------|
| `readme_gen.py` (or function in existing module) | `generate_readme()` function |
| `migration.py` (or function in `storage.py`) | `migrate_if_needed()` function |

## User-Visible Changes

- One-time migration message on first run after update
- Updated README.md in data directory
- New `bt readme` command
- `bt rebuild` also regenerates README
