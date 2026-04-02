# Tags Absorb Collections — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge collections into tags — tags gain `analyze` and `execute` sub-commands with stage tracking, replacing the separate collection system entirely.

**Architecture:** Remove `collection_storage.py` and `commands/collections.py`. Add a `tag_stages` table to the SQLite DB for tracking analysis/execute state. Create `commands/tags.py` with `analyze_tag_cmd`, `execute_tag_cmd`, and an updated `tags_list_cmd`. Modify `cli.py` routing to extend `@tag` with sub-commands and remove `+` routing. Remove `+collection` capture path from `capture.py` and `parser.py`.

**Tech Stack:** Python, Click, SQLite, Rich, python-frontmatter

---

### Task 1: Add `tag_stages` table to SQLite schema

**Files:**
- Modify: `src/bute/db.py:76-115` (add table to `ensure_schema`)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_db.py`, add:

```python
def test_tag_stages_table_exists(tmp_data):
    """tag_stages table should be created by ensure_schema."""
    from bute.db import get_connection
    db = get_connection()
    # Insert a row to prove the table exists and has correct columns
    db.execute(
        "INSERT INTO tag_stages (tag, stage) VALUES (?, ?)",
        ("test-tag", "raw"),
    )
    db.commit()
    row = db.execute("SELECT tag, stage, analysis, tasks_text, analyzed_at, executed_at FROM tag_stages WHERE tag = ?", ("test-tag",)).fetchone()
    assert row is not None
    assert row[0] == "test-tag"
    assert row[1] == "raw"
    assert row[2] is None  # analysis
    assert row[3] is None  # tasks_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py::test_tag_stages_table_exists -v`
Expected: FAIL with "no such table: tag_stages"

- [ ] **Step 3: Add `tag_stages` table to schema**

In `src/bute/db.py`, inside `ensure_schema()`, add after the `entries` table creation (after line 103, before the vec0 block):

```python
        CREATE TABLE IF NOT EXISTS tag_stages (
            tag         TEXT PRIMARY KEY,
            stage       TEXT NOT NULL DEFAULT 'raw',
            analysis    TEXT,
            tasks_text  TEXT,
            analyzed_at TEXT,
            executed_at TEXT
        );
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py::test_tag_stages_table_exists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/db.py tests/test_db.py
git commit -m "feat: add tag_stages table to SQLite schema"
```

---

### Task 2: Add DB helper functions for tag stages

**Files:**
- Modify: `src/bute/db.py` (add functions at end of file)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_db.py`, add:

```python
def test_upsert_tag_stage(tmp_data):
    """upsert_tag_stage creates and updates tag stage rows."""
    from bute.db import get_tag_stage, upsert_tag_stage
    # Create
    upsert_tag_stage("home-reno", "analyzed", analysis="Theme A\n- item one")
    row = get_tag_stage("home-reno")
    assert row is not None
    assert row["stage"] == "analyzed"
    assert row["analysis"] == "Theme A\n- item one"
    assert row["analyzed_at"] is not None
    assert row["executed_at"] is None
    # Update
    upsert_tag_stage("home-reno", "executed", tasks_text="1. Do thing")
    row = get_tag_stage("home-reno")
    assert row["stage"] == "executed"
    assert row["tasks_text"] == "1. Do thing"
    assert row["executed_at"] is not None
    assert row["analysis"] == "Theme A\n- item one"  # preserved


def test_get_tag_stage_missing(tmp_data):
    """get_tag_stage returns None for unknown tags."""
    from bute.db import get_tag_stage
    assert get_tag_stage("nonexistent") is None


def test_get_all_tag_stages(tmp_data):
    """get_all_tag_stages returns all rows."""
    from bute.db import get_all_tag_stages, upsert_tag_stage
    upsert_tag_stage("alpha", "analyzed", analysis="a")
    upsert_tag_stage("beta", "raw")
    rows = get_all_tag_stages()
    tags = [r["tag"] for r in rows]
    assert "alpha" in tags
    assert "beta" in tags
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py::test_upsert_tag_stage tests/test_db.py::test_get_tag_stage_missing tests/test_db.py::test_get_all_tag_stages -v`
Expected: FAIL with "cannot import name 'upsert_tag_stage'"

- [ ] **Step 3: Implement helper functions**

Add to the end of `src/bute/db.py` (before the `count` function, in the Query operations section):

```python
# ---------------------------------------------------------------------------
# Tag stage operations
# ---------------------------------------------------------------------------

def upsert_tag_stage(
    tag: str,
    stage: str,
    *,
    analysis: str | None = None,
    tasks_text: str | None = None,
    config=None,
) -> None:
    """Insert or update a tag's processing stage."""
    from datetime import datetime, timezone

    db = get_connection(config)
    now = datetime.now(timezone.utc).astimezone().isoformat()

    existing = get_tag_stage(tag, config)
    if existing is None:
        db.execute(
            """INSERT INTO tag_stages (tag, stage, analysis, tasks_text, analyzed_at, executed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                tag,
                stage,
                analysis,
                tasks_text,
                now if stage in ("analyzed", "executed") else None,
                now if stage == "executed" else None,
            ),
        )
    else:
        updates = ["stage = ?"]
        params: list = [stage]
        if analysis is not None:
            updates.append("analysis = ?")
            params.append(analysis)
        if tasks_text is not None:
            updates.append("tasks_text = ?")
            params.append(tasks_text)
        if stage in ("analyzed", "executed"):
            updates.append("analyzed_at = ?")
            params.append(existing["analyzed_at"] or now)
        if stage == "executed":
            updates.append("executed_at = ?")
            params.append(now)
        # If rolling back to analyzed, clear executed fields
        if stage == "analyzed":
            updates.append("executed_at = ?")
            params.append(None)
            updates.append("tasks_text = ?")
            params.append(None)
            updates.append("analyzed_at = ?")
            params.append(now)
        params.append(tag)
        db.execute(f"UPDATE tag_stages SET {', '.join(updates)} WHERE tag = ?", params)
    db.commit()


def get_tag_stage(tag: str, config=None) -> dict | None:
    """Get a tag's processing stage. Returns dict or None."""
    db = get_connection(config)
    row = db.execute(
        "SELECT tag, stage, analysis, tasks_text, analyzed_at, executed_at FROM tag_stages WHERE tag = ?",
        (tag,),
    ).fetchone()
    if row is None:
        return None
    return {
        "tag": row[0],
        "stage": row[1],
        "analysis": row[2],
        "tasks_text": row[3],
        "analyzed_at": row[4],
        "executed_at": row[5],
    }


def get_all_tag_stages(config=None) -> list[dict]:
    """Get all tag stage rows."""
    db = get_connection(config)
    rows = db.execute(
        "SELECT tag, stage, analysis, tasks_text, analyzed_at, executed_at FROM tag_stages ORDER BY tag"
    ).fetchall()
    return [
        {
            "tag": r[0],
            "stage": r[1],
            "analysis": r[2],
            "tasks_text": r[3],
            "analyzed_at": r[4],
            "executed_at": r[5],
        }
        for r in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py::test_upsert_tag_stage tests/test_db.py::test_get_tag_stage_missing tests/test_db.py::test_get_all_tag_stages -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/db.py tests/test_db.py
git commit -m "feat: add tag stage DB helpers (upsert, get, get_all)"
```

---

### Task 3: Create `commands/tags.py` with analyze and execute commands

**Files:**
- Create: `src/bute/commands/tags.py`
- Test: `tests/test_tags.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tags.py`:

```python
"""Tests for tag analyze and execute commands."""

from unittest.mock import MagicMock, patch

import pytest

from bute.cli import main
from bute.config import default_config, save_config
from bute.db import get_tag_stage
from bute.models import Entry, EntryType
from bute.storage import save_entry


def _setup(tmp_config, tmp_data):
    doc = default_config(provider="anthropic")
    doc["ai"]["api_key"] = "sk-test"
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


@pytest.fixture(autouse=True)
def _reset_llm():
    from bute.ai.llm import reset as reset_llm
    reset_llm()
    yield
    reset_llm()


def _mock_llm(response):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = response
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    return patch("bute.ai.llm._get_client", return_value=mock_client)


def _create_tagged_entries(tag):
    """Create sample entries with the given tag."""
    entries = [
        Entry.create(EntryType.TASK, "fix faucet", tags=[tag]),
        Entry.create(EntryType.NOTE, "kitchen is 12x15", tags=[tag]),
        Entry.create(EntryType.JOURNAL, "excited about reno", tags=[tag]),
    ]
    for e in entries:
        save_entry(e)
    return entries


# --- Analyze ---

def test_analyze_tag(runner, tmp_config, tmp_data):
    """bt @home-reno analyze should analyze all tagged entries."""
    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")

    with _mock_llm("Theme A\n- fix faucet\n- kitchen dimensions"):
        result = runner.invoke(main, ["@home-reno", "analyze"], input="y\n")

    assert result.exit_code == 0
    stage = get_tag_stage("home-reno")
    assert stage is not None
    assert stage["stage"] == "analyzed"
    assert "Theme A" in stage["analysis"]


def test_analyze_tag_no_entries(runner, tmp_config, tmp_data):
    """Analyzing a tag with no entries should show a message."""
    _setup(tmp_config, tmp_data)
    result = runner.invoke(main, ["@empty-tag", "analyze"])
    assert "no entries" in result.output.lower()


def test_analyze_tag_rerun_overwrites(runner, tmp_config, tmp_data):
    """Re-running analyze should overwrite previous analysis."""
    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")

    with _mock_llm("First analysis"):
        runner.invoke(main, ["@home-reno", "analyze"], input="y\n")

    with _mock_llm("Second analysis"):
        runner.invoke(main, ["@home-reno", "analyze"], input="y\n")

    stage = get_tag_stage("home-reno")
    assert "Second analysis" in stage["analysis"]
    assert stage["stage"] == "analyzed"


# --- Execute ---

def test_execute_analyzed_tag(runner, tmp_config, tmp_data):
    """bt @home-reno execute should generate tasks from analysis."""
    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")

    # Analyze first
    with _mock_llm("Theme A\n- items"):
        runner.invoke(main, ["@home-reno", "analyze"], input="y\n")

    # Execute
    with _mock_llm("1. Measure kitchen\n2. Buy supplies"):
        result = runner.invoke(main, ["@home-reno", "execute"], input="y\n")

    assert result.exit_code == 0

    # Verify tasks were created with the tag
    from bute.storage import load_entries_by_filter
    tasks = load_entries_by_filter(lambda e: e.type == EntryType.TASK and "home-reno" in e.tags)
    task_bodies = [t.body for t in tasks]
    assert "Measure kitchen" in task_bodies
    assert "Buy supplies" in task_bodies

    stage = get_tag_stage("home-reno")
    assert stage["stage"] == "executed"


def test_execute_raw_tag_analyzes_first(runner, tmp_config, tmp_data):
    """Execute on un-analyzed tag should run analyze first."""
    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")

    analyze_response = "Theme A\n- items"
    task_response = "1. Do the thing"

    mock_resp_1 = MagicMock()
    mock_resp_1.choices = [MagicMock()]
    mock_resp_1.choices[0].message.content = analyze_response

    mock_resp_2 = MagicMock()
    mock_resp_2.choices = [MagicMock()]
    mock_resp_2.choices[0].message.content = task_response

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [mock_resp_1, mock_resp_2]

    with patch("bute.ai.llm._get_client", return_value=mock_client):
        result = runner.invoke(main, ["@home-reno", "execute"], input="y\ny\n")

    assert result.exit_code == 0
    stage = get_tag_stage("home-reno")
    assert stage["stage"] == "executed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tags.py -v`
Expected: FAIL (commands don't exist yet)

- [ ] **Step 3: Create `commands/tags.py`**

Create `src/bute/commands/tags.py`:

```python
"""Tag processing commands — analyze and execute."""

import re

import click
from rich.console import Console

from bute.db import get_tag_stage, upsert_tag_stage

console = Console()


def _load_tagged_entries(tag: str, config=None):
    """Load all entries with the given tag."""
    from bute.storage import query_and_load

    return query_and_load(config, tag=tag)


def _run_analyze(tag: str, entries, config) -> str | None:
    """Run the analyze stage. Returns analysis text or None if rejected."""
    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send
    from bute.ai.prompts import analyze_prompt, format_entries

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return None

    console.print(f"  [dim]Analyzing {len(entries)} entries for @{tag}...[/dim]")

    formatted = format_entries(entries)
    response = llm_send(analyze_prompt(), f"Tag: \"@{tag}\"\n\nEntries:\n{formatted}", config)
    console.print(f"\n{response}")

    if click.confirm("\n  Accept this analysis?", default=True):
        upsert_tag_stage(tag, "analyzed", analysis=response, config=config)
        console.print(f"  [green]@{tag} → analyzed[/green]")
        return response
    else:
        console.print(f"  [dim]Analysis discarded. Run analyze again when ready.[/dim]")
        return None


@click.command("analyze_tag", hidden=True)
@click.argument("tag_name")
@click.pass_context
def analyze_tag_cmd(ctx, tag_name):
    """AI analyzes all entries with the given tag."""
    config = ctx.obj.get("config")

    entries = _load_tagged_entries(tag_name, config)
    if not entries:
        console.print(f"  [dim]No entries found with @{tag_name}.[/dim]")
        return

    _run_analyze(tag_name, entries, config)


@click.command("execute_tag", hidden=True)
@click.argument("tag_name")
@click.pass_context
def execute_tag_cmd(ctx, tag_name):
    """AI generates sequenced tasks from tag analysis."""
    from bute.ai import _LLM_INSTALL_MSG, embed_entry, is_llm_available, llm_send
    from bute.ai.prompts import execute_prompt
    from bute.display import confirm_capture
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    config = ctx.obj.get("config")

    entries = _load_tagged_entries(tag_name, config)
    if not entries:
        console.print(f"  [dim]No entries found with @{tag_name}.[/dim]")
        return

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    # Check current stage
    stage_row = get_tag_stage(tag_name, config=config)
    analysis_content = stage_row["analysis"] if stage_row else None

    # If no analysis yet, run analyze first
    if not analysis_content:
        console.print(f"  [dim]No analysis found. Running analysis first...[/dim]")
        analysis_content = _run_analyze(tag_name, entries, config)
        if analysis_content is None:
            return  # user rejected analysis

    # Generate tasks
    console.print(f"  [dim]Generating tasks...[/dim]")
    response = llm_send(execute_prompt(), f"Tag: \"@{tag_name}\"\n\nAnalysis:\n{analysis_content}", config)
    console.print(f"\n{response}")

    if not click.confirm("\n  Create these tasks?", default=True):
        console.print(f"  [dim]Task generation discarded. Analysis preserved. Run execute again when ready.[/dim]")
        return

    # Parse numbered tasks (lines starting with digit or -)
    tasks = []
    for line in response.split("\n"):
        stripped = line.strip()
        numbered = re.match(r"^\d+\.\s+(.+)$", stripped)
        bulleted = re.match(r"^-\s+(.+)$", stripped)
        if numbered:
            tasks.append(numbered.group(1))
        elif bulleted:
            tasks.append(bulleted.group(1))

    for task_text in tasks:
        entry = Entry.create(
            entry_type=EntryType.TASK,
            body=task_text,
            tags=[tag_name],
        )
        save_entry(entry, config)
        embed_entry(entry.id, entry.body, config)
        confirm_capture(entry)

    upsert_tag_stage(tag_name, "executed", tasks_text=response, config=config)
    console.print(f"  [green]{len(tasks)} tasks created from @{tag_name}[/green]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tags.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/tags.py tests/test_tags.py
git commit -m "feat: add tag analyze and execute commands"
```

---

### Task 4: Update `tags_cmd` to show stage info

**Files:**
- Modify: `src/bute/commands/views.py:158-190` (the existing `tags_cmd`)
- Test: `tests/test_tags.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tags.py`:

```python
def test_tags_list_shows_stage(runner, tmp_config, tmp_data):
    """bt tags should show stage column with colors."""
    _setup(tmp_config, tmp_data)
    _create_tagged_entries("home-reno")

    # Analyze the tag
    with _mock_llm("Theme A\n- items"):
        runner.invoke(main, ["@home-reno", "analyze"], input="y\n")

    result = runner.invoke(main, ["tags"])
    assert result.exit_code == 0
    assert "home-reno" in result.output
    assert "analyzed" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tags.py::test_tags_list_shows_stage -v`
Expected: FAIL — current `tags_cmd` doesn't show stage

- [ ] **Step 3: Update `tags_cmd` in `views.py`**

Replace the `tags_cmd` function in `src/bute/commands/views.py` (lines 158-190):

```python
@click.command("tags")
@click.pass_context
def tags_cmd(ctx):
    """List all tags with entry counts and processing stage."""
    from bute.db import get_all_tag_stages

    config = ctx.obj.get("config")

    entries = query_and_load(config, has_tags=True)

    counts: dict[str, int] = {}
    for entry in entries:
        for tag in entry.tags:
            counts[tag] = counts.get(tag, 0) + 1

    if not counts:
        console.print("  [dim]No tags found.[/dim]")
        return

    # Load stage info
    stages = {s["tag"]: s["stage"] for s in get_all_tag_stages(config)}
    stage_colors = {"raw": "dim", "analyzed": "yellow", "executed": "green"}

    table = Table(
        title="Tags",
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Tag", ratio=1)
    table.add_column("Stage")
    table.add_column("#", justify="right", width=5)

    for tag, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        stage = stages.get(tag, "raw")
        color = stage_colors.get(stage, "dim")
        table.add_row(f"@{tag}", f"[{color}]{stage}[/{color}]", str(count))

    console.print()
    console.print(table)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tags.py::test_tags_list_shows_stage -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/views.py tests/test_tags.py
git commit -m "feat: show tag stage in bt tags list"
```

---

### Task 5: Update CLI routing — extend `@tag`, remove `+collection`

**Files:**
- Modify: `src/bute/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_tag_analyze_routing(runner, tmp_config, tmp_data):
    """bt @tag analyze should route to analyze_tag command."""
    from bute.cli import main
    # Just verify routing works (no entries, should print message)
    result = runner.invoke(main, ["@test-tag", "analyze"])
    assert result.exit_code == 0
    assert "no entries" in result.output.lower()


def test_tag_execute_routing(runner, tmp_config, tmp_data):
    """bt @tag execute should route to execute_tag command."""
    from bute.cli import main
    result = runner.invoke(main, ["@test-tag", "execute"])
    assert result.exit_code == 0
    assert "no entries" in result.output.lower()


def test_plus_syntax_removed(runner, tmp_config, tmp_data):
    """bt +name should no longer route to collections."""
    from bute.cli import main
    result = runner.invoke(main, ["+old-collection"])
    # Should get a Click error (no such command), not a collection view
    assert result.exit_code != 0 or "no such command" in result.output.lower() or "error" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_tag_analyze_routing tests/test_cli.py::test_tag_execute_routing tests/test_cli.py::test_plus_syntax_removed -v`
Expected: FAIL — analyze/execute routing doesn't exist, `+` still routes to collections

- [ ] **Step 3: Update `cli.py`**

In `src/bute/cli.py`:

**3a. Replace the `@tag` routing block (lines 111-115) with sub-command detection:**

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

**3b. Remove the entire `+collection` block (lines 117-133):**

Delete:
```python
        # 6. Collection — +name [subcommand]
        if first.startswith("+") and len(first) > 1:
            collection_name = first[1:]
            subcommand = rest[0] if rest else None

            if subcommand == "analyze":
                cmd = self.get_command(ctx, "analyze_collection")
                if cmd is not None:
                    return "analyze_collection", cmd, [collection_name]
            elif subcommand == "execute":
                cmd = self.get_command(ctx, "execute_collection")
                if cmd is not None:
                    return "execute_collection", cmd, [collection_name]
            else:
                cmd = self.get_command(ctx, "view_collection")
                if cmd is not None:
                    return "view_collection", cmd, [collection_name]
```

**3c. Remove the collections number-select branch (lines 141-149):**

Delete:
```python
                # Collections view — number selects a collection to view
                if state.get("view") == "collections":
                    entries_list = state.get("entries", [])
                    num = int(first)
                    if 1 <= num <= len(entries_list):
                        collection_name = entries_list[num - 1]
                        cmd = self.get_command(ctx, "view_collection")
                        if cmd is not None:
                            return "view_collection", cmd, [collection_name]
```

**3d. Replace collection imports and registrations (lines 360-401):**

Replace:
```python
from bute.commands.collections import (  # noqa: E402
    analyze_collection_cmd,
    collections_list_cmd,
    execute_collection_cmd,
    view_collection_cmd,
)
```

With:
```python
from bute.commands.tags import analyze_tag_cmd, execute_tag_cmd  # noqa: E402
```

Replace:
```python
main.add_command(analyze_collection_cmd)
main.add_command(execute_collection_cmd)
main.add_command(view_collection_cmd)
main.add_command(collections_list_cmd)
```

With:
```python
main.add_command(analyze_tag_cmd)
main.add_command(execute_tag_cmd)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::test_tag_analyze_routing tests/test_cli.py::test_tag_execute_routing tests/test_cli.py::test_plus_syntax_removed -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/cli.py tests/test_cli.py
git commit -m "feat: extend @tag routing with analyze/execute, remove + syntax"
```

---

### Task 6: Remove collection capture path from parser and capture

**Files:**
- Modify: `src/bute/parser.py:23,52,101,109-113,130`
- Modify: `src/bute/commands/capture.py:53-81`
- Test: `tests/test_capture.py`, `tests/test_parser.py`

- [ ] **Step 1: Write a test to verify `+token` becomes body text**

Add to `tests/test_parser.py`:

```python
def test_plus_token_becomes_body_text():
    """After collection removal, +token should be treated as body text."""
    from bute.parser import parse_capture_tokens
    parsed = parse_capture_tokens(["/t", "fix", "faucet", "+home-reno"])
    assert "+home-reno" in parsed.body
    assert parsed.collection is None
```

Add to `tests/test_capture.py`:

```python
def test_capture_plus_token_creates_entry(runner, tmp_config, tmp_data):
    """bt t fix faucet +home-reno should create an entry (not redirect to collection)."""
    result = runner.invoke(main, ["t", "fix", "faucet", "+home-reno"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    assert len(entries) == 1
    content = entries[0].read_text()
    assert "fix faucet +home-reno" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_parser.py::test_plus_token_becomes_body_text tests/test_capture.py::test_capture_plus_token_creates_entry -v`
Expected: FAIL — `+home-reno` still parsed as collection

- [ ] **Step 3: Remove collection from parser**

In `src/bute/parser.py`:

Remove line 23:
```python
COLLECTION_RE = re.compile(r"^\+([a-zA-Z0-9_-]+)$")
```

Remove `collection` field from `ParsedInput` (line 52):
```python
    collection: str | None = None
```

Remove `collection` variable initialization (line 101):
```python
    collection = None
```

Remove the collection match block (lines 109-113):
```python
        collection_match = COLLECTION_RE.match(token)
        if collection_match:
            if collection is None:
                collection = collection_match.group(1)
            continue
```

Remove `collection=collection` from the return (line 130):
```python
        collection=collection,
```

- [ ] **Step 4: Remove collection capture path from capture.py**

In `src/bute/commands/capture.py`:

Remove lines 53-81 (the entire collection capture block):
```python
    # Collection capture — add to collection, no entry created
    if parsed.collection:
        from bute.collection_storage import append_to_collection, load_collection
        from rich.console import Console

        console = Console()

        # Map signifier to BuJo bullet
        bullet_map = {"/t": ".", "/n": "-", "/j": "=", "/c": "o"}
        bullet = bullet_map.get(parsed.signifier, ".")

        # Reconstruct raw line: bullet + body + tags + metadata
        parts = [bullet, parsed.body]
        for tag in parsed.tags:
            parts.append(f"@{tag}")
        for key, value in parsed.metadata.items():
            parts.append(f"{key}:{value}")
        raw_line = " ".join(parts)

        config = ctx.obj.get("config")
        result = append_to_collection(parsed.collection, [f"- {raw_line}"], config=config)
        if result is None:
            console.print(f"  [red]Cannot add to +{parsed.collection} — already processed.[/red]")
            return

        coll = load_collection(parsed.collection, config=config)
        count = coll["item_count"] if coll else 0
        console.print(f"  [green]Added to +{parsed.collection} ({count} items)[/green]")
        return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_parser.py::test_plus_token_becomes_body_text tests/test_capture.py::test_capture_plus_token_creates_entry -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/bute/parser.py src/bute/commands/capture.py tests/test_parser.py tests/test_capture.py
git commit -m "feat: remove +collection from parser and capture path"
```

---

### Task 7: Remove collection modules and display references

**Files:**
- Delete: `src/bute/collection_storage.py`
- Delete: `src/bute/commands/collections.py`
- Modify: `src/bute/display.py:98-105`
- Delete: `tests/test_collections.py`

- [ ] **Step 1: Remove `+collection` display logic from `display.py`**

In `src/bute/display.py`, replace lines 93-106 (the meta_parts block in `_build_entry_row`):

```python
    meta_parts = []
    if entry.due:
        meta_parts.append(f"due:{entry.due}")
    if entry.scheduled_time:
        meta_parts.append(format_time_display(entry.scheduled_time))
    if entry.tags:
        meta_parts.extend(f"@{t}" for t in entry.tags)
    meta = " ".join(meta_parts)
```

This removes the `+collection` display and the logic that hid the collection tag from `@tags`.

- [ ] **Step 2: Delete collection modules**

```bash
rm src/bute/collection_storage.py
rm src/bute/commands/collections.py
rm tests/test_collections.py
```

- [ ] **Step 3: Run the full test suite to verify nothing is broken**

Run: `uv run pytest -v`
Expected: All tests pass (collection tests are deleted, remaining tests don't depend on collection modules)

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "refactor: remove collection_storage.py, commands/collections.py, and +collection display"
```

---

### Task 8: Update AI prompts for structured entry input

**Files:**
- Modify: `src/bute/ai/prompts.py:108-138`

- [ ] **Step 1: Update `analyze_prompt()`**

In `src/bute/ai/prompts.py`, replace the `analyze_prompt()` function:

```python
def analyze_prompt() -> str:
    return f"""{SYSTEM_BASE}

The user has tagged entries for a topic. Each entry has a type indicator and status:
  . = task (action or intention)
  - = note (reference or fact)
  = = journal (reflection or feeling)
  o = calendar (event or commitment)
  [done] = completed, [dropped] = consciously removed, [active] = still open
  ! = important

Cluster these entries into coherent themes. For each theme:
- Give it a clear, concise name
- List the entries that belong to it
- Briefly note connections or tensions between entries

Be faithful to the original entries — don't add, remove, or rephrase.
Organize what's there. Use the entry types and statuses as context (done tasks show progress, journals reveal feelings, notes are facts, active tasks are intentions)."""
```

- [ ] **Step 2: Update `execute_prompt()`**

In `src/bute/ai/prompts.py`, replace the `execute_prompt()` function:

```python
def execute_prompt() -> str:
    return f"""{SYSTEM_BASE}

The user has an analyzed set of tagged entries — clustered into themes. Generate a sequenced list of concrete, actionable tasks that would implement or address these themes.

Requirements:
- Each task starts with a verb
- Tasks are specific enough to act on in a single session
- Tasks are ordered sequentially — each builds on the previous
- Number each task (1, 2, 3...)
- Keep the total manageable (aim for 5-15 tasks)
- Account for already-done tasks — don't regenerate work that's complete

Output only the numbered task list, nothing else."""
```

- [ ] **Step 3: Run prompt tests**

Run: `uv run pytest tests/test_tags.py -v`
Expected: PASS (existing tag tests use these prompts)

- [ ] **Step 4: Commit**

```bash
git add src/bute/ai/prompts.py
git commit -m "refactor: update analyze/execute prompts for structured entry input"
```

---

### Task 9: Update help text and CLI grammar

**Files:**
- Modify: `src/bute/cli.py` (help text in `_print_help()`)

- [ ] **Step 1: Update `_print_help()` in `cli.py`**

Replace the Collections section (lines 272-279) with:

```python
    # Tag Processing
    console.print("  [bold cyan]Tag Processing[/bold cyan] — ideas to action")
    console.print("    [bold]bt @[/bold]<name> [bold]analyze[/bold]     AI clusters and organizes tagged entries")
    console.print("    [bold]bt @[/bold]<name> [bold]execute[/bold]     AI generates sequenced tasks from analysis")
    console.print()
```

Also remove line 206 (the `+collection` capture hint):
```python
    console.print("    Add [bold]+collection[/bold] to collect: [dim]bt t fix faucet +home-reno[/dim]")
```

- [ ] **Step 2: Verify help renders correctly**

Run: `uv run bt --help`
Expected: Shows "Tag Processing" section with `@name analyze` and `@name execute`. No mention of `+collection` or `collections`.

- [ ] **Step 3: Commit**

```bash
git add src/bute/cli.py
git commit -m "docs: update help text — replace collections with tag processing"
```

---

### Task 10: Update CLAUDE.md and delete demo collection

**Files:**
- Modify: `CLAUDE.md`
- Delete: demo collection file

- [ ] **Step 1: Delete the demo collection file**

```bash
rm -rf ~/bute/collections/
```

- [ ] **Step 2: Update CLAUDE.md**

In `CLAUDE.md`:

Replace the Collections section in CLI Grammar:

```markdown
**Tag Processing** — ideas to action:
```
bt @home-reno analyze             # AI clusters and organizes tagged entries
bt @home-reno execute             # AI generates sequenced tasks from analysis
```
```

Remove all references to `+collection` syntax throughout the file. Update:
- The Architecture section's CLI Dispatch description (remove collection from the routing layers)
- The Key Modules table (remove `collection_storage.py` and `commands/collections.py`)
- The Data Flow section (remove collection references)
- The Design Decisions section (update collection references)
- The Backlog section (update/remove collection items)

Renumber the routing layers in `resolve_command()` description:
1. Named commands
2. Letter shortcut
3. Signifiers
4. Important filter
5. Tag filter (with analyze/execute sub-commands)
6. Number-action
7. Fallback

- [ ] **Step 3: Run the full test suite one final time**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md — tags absorb collections"
```

---

### Task 11: Final verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass, no import errors, no references to deleted modules

- [ ] **Step 2: Manual smoke test**

```bash
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall
bt t fix faucet @home-reno
bt n kitchen is 12x15 @home-reno
bt @home-reno
bt tags
bt --help
```

Expected:
- Entries created with `@home-reno` tag
- `bt @home-reno` shows both entries
- `bt tags` shows `home-reno` with stage `raw` and count `2`
- Help shows Tag Processing section, no mention of `+` or collections

- [ ] **Step 3: Commit any remaining fixes**

If any issues found, fix and commit.
