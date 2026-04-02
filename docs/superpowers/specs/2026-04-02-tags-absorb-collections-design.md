# Tags Absorb Collections — Design Spec

**Date**: 2026-04-02
**Status**: Draft

## Summary

Merge collections into tags. Drop the `+` syntax and `collection_storage.py`. Tags gain two new sub-commands (`analyze`, `execute`) and stage tracking via a `tag_stages` table in the SQLite DB. One grouping concept instead of two.

## Motivation

Tags (`@`) and collections (`+`) are both labels on entries. The only difference was that collections had a separate file format with AI processing stages. By giving tags the same analyze/execute capability, we eliminate a separate concept, separate storage, and separate routing — while enabling richer AI processing (structured entry data instead of raw text lines).

Tags now have a dual role:
- **Tag as label (means to an end)** — `bt t @backend`, `bt @home-reno` — organizes and filters entries
- **Tag as goal (end in itself)** — `bt @home-reno analyze`, `bt @home-reno execute` — the tag is the project, entries serve it

The distinction is in usage, not data model. Commands determine the role.

## Data Model

### Entries — no change

Tags remain in YAML frontmatter: `tags: [home-reno, backend]`. No new fields.

### Stage tracking — new `tag_stages` table

```sql
CREATE TABLE IF NOT EXISTS tag_stages (
    tag         TEXT PRIMARY KEY,
    stage       TEXT NOT NULL DEFAULT 'raw',
    analysis    TEXT,
    tasks_text  TEXT,
    analyzed_at TEXT,
    executed_at TEXT
);
```

- `stage`: `raw` | `analyzed` | `executed`
- `analysis`: stored AI analysis output
- `tasks_text`: stored AI execute output
- `analyzed_at` / `executed_at`: ISO timestamps
- Row is created on first `analyze` call. Tags without a row are implicitly `raw`.

Re-running `analyze` overwrites previous analysis and rolls stage back to `analyzed`. Re-running `execute` re-generates tasks.

## CLI Routing

### resolve_command() changes

**Remove** the `+` branch (current step 6, lines 117-133 of `cli.py`).

**Extend** the `@` branch (current step 5, lines 111-115) to detect sub-commands:

```python
# 5. Tag filter — @tagname [subcommand]
if first.startswith("@") and len(first) > 1:
    tag_name = first[1:]
    subcommand = rest[0] if rest else None

    if subcommand == "analyze":
        cmd = self.get_command(ctx, "analyze_tag")
        if cmd is not None:
            return "analyze_tag", cmd, [tag_name]
    elif subcommand == "execute":
        cmd = self.get_command(ctx, "execute_tag")
        if cmd is not None:
            return "execute_tag", cmd, [tag_name]
    else:
        cmd = self.get_command(ctx, "tag_filter")
        if cmd is not None:
            return "tag_filter", cmd, [tag_name]
```

**Remove** the collections number-select branch (lines 141-149) that handles number selection from `bt collections` view.

### New commands

| Command | Description |
|---------|-------------|
| `bt @tag analyze` | AI analyzes all entries with tag |
| `bt @tag execute` | AI generates sequenced tasks from analysis |
| `bt tags` | List all tags with stage and entry count |

### Removed commands

| Command | Replacement |
|---------|-------------|
| `bt +name` | `bt @name` (already works) |
| `bt +name analyze` | `bt @name analyze` |
| `bt +name execute` | `bt @name execute` |
| `bt collections` | `bt tags` |

### Capture

No change. `bt t fix faucet @home-reno` already creates a task with the tag. The `+collection` capture path in `capture.py` (which redirected to collection files) gets removed.

## Analyze Flow

`bt @home-reno analyze`:

1. Query all entries with tag `home-reno` from SQLite (all types, all statuses)
2. Format entries for AI — include type icon, status, body, due date, created date
3. Send to LLM with `analyze_prompt()` (updated for structured entry input)
4. Display response, prompt "Accept this analysis?"
5. If accepted: upsert `tag_stages` row — `stage=analyzed`, store analysis text, set `analyzed_at`
6. If rejected: no changes

## Execute Flow

`bt @home-reno execute`:

1. Load `tag_stages` row for tag
2. If no analysis exists (stage is `raw` or no row), run analyze first
3. Send analysis to LLM with `execute_prompt()`
4. Display response, prompt "Create these tasks?"
5. If accepted:
   - Parse numbered/bulleted tasks from response
   - Create each as an Entry with `entry_type=TASK`, tagged `home-reno`
   - Upsert `tag_stages` row — `stage=executed`, store tasks text, set `executed_at`
6. If rejected: analysis preserved, no tasks created

## Tags List Command

`bt tags` replaces `bt collections`:

- Query all distinct tags from entries table
- Left join with `tag_stages` for stage info
- Display table: `#`, `Tag`, `Stage`, `Entries` (count)
- Stage colors: raw=dim, analyzed=yellow, executed=green
- Tags without a `tag_stages` row show as `raw`
- Save state so `bt <n>` can drill into a tag view

## Files Changed

### Remove
- `src/bute/collection_storage.py` — entire module
- `src/bute/commands/collections.py` — entire module
- `~/bute/collections/` demo file

### Add
- `src/bute/commands/tags.py` — `analyze_tag_cmd`, `execute_tag_cmd`, `tags_list_cmd`

### Modify
- `src/bute/db.py` — add `tag_stages` table to schema
- `src/bute/cli.py` — remove `+` routing, extend `@` routing with sub-commands, replace collection command registrations with tag commands, update help text
- `src/bute/commands/capture.py` — remove `+collection` capture path
- `src/bute/parser.py` — remove collection token parsing (if applicable)
- `src/bute/ai/prompts.py` — update analyze/execute prompts for structured entry input
- `CLAUDE.md` — update CLI grammar, architecture docs, backlog

## What's NOT in scope

- Long-form note display (title truncation) — separate follow-up
- "bt this" Claude convention for creating long-form notes — separate follow-up
- `bt @tag view` full rendered display (like old `display_collection`) — entries already display via `bt @tag`
