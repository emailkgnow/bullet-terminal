# Collections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the FFFF pipeline with a collections system — `+collection` capture syntax, `analyze`/`execute` AI processing, and `bt collections` list view.

**Architecture:** Collections are markdown files with YAML frontmatter and sectioned content (## Input, ## Analysis, ## Tasks). Items accumulate via `+name` in capture. Two AI commands (analyze, execute) replace four (find/form/focus/finish). Executed collections produce real task entries with `extra_meta["collection"]`.

**Tech Stack:** Click (CLI), Rich (display), python-frontmatter (storage), OpenAI-compatible LLM (AI stages)

---

### Task 1: Update Parser — `+collection` Token Recognition

**Files:**
- Modify: `src/bute/parser.py:22` (add regex), `src/bute/parser.py:42-50` (extend ParsedInput), `src/bute/parser.py:100-113` (match in loop)
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write failing tests for collection parsing**

```python
# Add to tests/test_parser.py

def test_parse_collection_token():
    result = parse_capture_tokens(["t", "fix", "faucet", "+home-reno"])
    assert result.collection == "home-reno"
    assert result.body == "fix faucet"
    assert result.signifier == "/t"


def test_parse_collection_with_tags():
    result = parse_capture_tokens(["t", "fix", "faucet", "+home-reno", "@plumbing"])
    assert result.collection == "home-reno"
    assert result.tags == ["plumbing"]
    assert result.body == "fix faucet"


def test_parse_collection_with_metadata():
    result = parse_capture_tokens(["t", "fix", "faucet", "+home-reno", "due:friday"])
    assert result.collection == "home-reno"
    assert result.metadata == {"due": "friday"}
    assert result.body == "fix faucet"


def test_parse_no_collection():
    result = parse_capture_tokens(["t", "fix", "faucet"])
    assert result.collection is None


def test_parse_multiple_collections_first_wins():
    result = parse_capture_tokens(["t", "fix", "+alpha", "+beta"])
    assert result.collection == "alpha"
    # second +beta becomes a body word
    assert "beta" not in result.body or "+beta" in result.body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_parser.py::test_parse_collection_token tests/test_parser.py::test_parse_collection_with_tags tests/test_parser.py::test_parse_collection_with_metadata tests/test_parser.py::test_parse_no_collection tests/test_parser.py::test_parse_multiple_collections_first_wins -v`
Expected: FAIL — `ParsedInput` has no `collection` attribute

- [ ] **Step 3: Add COLLECTION_RE and extend ParsedInput**

In `src/bute/parser.py`, add the regex after `TAG_RE` (line 22):

```python
TAG_RE = re.compile(r"^@([a-zA-Z0-9_-]+)$")
COLLECTION_RE = re.compile(r"^\+([a-zA-Z0-9_-]+)$")
```

Add `collection` field to `ParsedInput` (after `tags`):

```python
@dataclass
class ParsedInput:
    """Structured result of parsing capture tokens."""

    signifier: str
    important: bool
    body_words: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    collection: str | None = None
```

- [ ] **Step 4: Handle `+collection` tokens in parse_capture_tokens**

In `parse_capture_tokens()`, add collection matching in the token loop (after tag matching, before body_words fallback):

```python
    collection = None

    for token in tokens[1:]:
        tag_match = TAG_RE.match(token)
        if tag_match:
            tags.append(tag_match.group(1))
            continue

        collection_match = COLLECTION_RE.match(token)
        if collection_match:
            if collection is None:
                collection = collection_match.group(1)
            continue

        kv_match = KV_RE.match(token)
        if kv_match:
            key = kv_match.group(1).lower()
            value = kv_match.group(2)
            metadata[key] = value
            continue

        body_words.append(token)

    return ParsedInput(
        signifier=signifier,
        important=important,
        body_words=body_words,
        metadata=metadata,
        tags=tags,
        collection=collection,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_parser.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/bute/parser.py tests/test_parser.py
git commit -m "feat: add +collection token parsing to parser"
```

---

### Task 2: Update Collection Storage — Sectioned Model

**Files:**
- Modify: `src/bute/collection_storage.py` (rewrite)
- Test: `tests/test_collections.py` (new file, replaces test_ffff.py storage tests)

- [ ] **Step 1: Write failing tests for new storage model**

Create `tests/test_collections.py`:

```python
"""Tests for collections storage and commands."""

from bute.collection_storage import (
    append_to_collection,
    list_collections_with_meta,
    load_collection,
    save_collection,
)


# --- Storage tests ---


def test_save_and_load_raw_collection(tmp_data):
    save_collection("test", "raw", {"input": "- . item one\n- . item two\n"})
    coll = load_collection("test")
    assert coll is not None
    assert coll["stage"] == "raw"
    assert coll["input_content"] == "- . item one\n- . item two\n"
    assert coll["analysis_content"] is None
    assert coll["tasks_content"] is None


def test_save_analyzed_collection(tmp_data):
    sections = {
        "input": "- . item one\n",
        "analysis": "**Theme A**\n- item one\n",
    }
    save_collection("test", "analyzed", sections)
    coll = load_collection("test")
    assert coll["stage"] == "analyzed"
    assert coll["input_content"] == "- . item one\n"
    assert coll["analysis_content"] == "**Theme A**\n- item one\n"
    assert coll["tasks_content"] is None


def test_save_executed_collection(tmp_data):
    sections = {
        "input": "- . item one\n",
        "analysis": "**Theme A**\n- item one\n",
        "tasks": "1. Do the thing\n2. Do the other thing\n",
    }
    save_collection("test", "executed", sections)
    coll = load_collection("test")
    assert coll["stage"] == "executed"
    assert coll["input_content"] is not None
    assert coll["analysis_content"] is not None
    assert coll["tasks_content"] == "1. Do the thing\n2. Do the other thing\n"


def test_load_missing_collection(tmp_data):
    assert load_collection("nonexistent") is None


def test_append_to_raw_collection(tmp_data):
    save_collection("test", "raw", {"input": "- . existing item\n"})
    append_to_collection("test", ["- . new item"])
    coll = load_collection("test")
    assert "existing item" in coll["input_content"]
    assert "new item" in coll["input_content"]


def test_append_creates_new_collection(tmp_data):
    append_to_collection("fresh", ["- . first item"])
    coll = load_collection("fresh")
    assert coll is not None
    assert coll["stage"] == "raw"
    assert "first item" in coll["input_content"]


def test_append_rejects_analyzed_collection(tmp_data):
    sections = {
        "input": "- . item\n",
        "analysis": "**Theme**\n- item\n",
    }
    save_collection("test", "analyzed", sections)
    result = append_to_collection("test", ["- . new item"])
    assert result is None  # rejected


def test_list_collections_with_meta(tmp_data):
    save_collection("alpha", "raw", {"input": "- . a\n- . b\n"})
    save_collection("beta", "analyzed", {
        "input": "- . c\n",
        "analysis": "**Theme**\n- c\n",
    })
    meta = list_collections_with_meta()
    names = [m["name"] for m in meta]
    assert "alpha" in names
    assert "beta" in names
    alpha = next(m for m in meta if m["name"] == "alpha")
    assert alpha["stage"] == "raw"
    assert alpha["item_count"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_collections.py -v`
Expected: FAIL — functions don't exist or have wrong signatures

- [ ] **Step 3: Rewrite collection_storage.py**

Replace `src/bute/collection_storage.py`:

```python
"""Collection storage — Markdown with YAML frontmatter and sectioned content."""

import re
from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from bute.config import get_data_dir

# Section header pattern for parsing
_SECTION_RE = re.compile(r"^## (Input|Analysis|Tasks)\s*$", re.MULTILINE)


def _collection_path(name: str, config=None) -> Path:
    """Return path to ~/bute/collections/<name>.md"""
    data_dir = get_data_dir(config)
    safe_name = name.lower().replace(" ", "-")
    return data_dir / "collections" / f"{safe_name}.md"


def _parse_sections(content: str) -> dict[str, str | None]:
    """Split markdown content into named sections."""
    sections = {"input": None, "analysis": None, "tasks": None}
    matches = list(_SECTION_RE.finditer(content))

    for i, match in enumerate(matches):
        section_name = match.group(1).lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        if body:
            sections[section_name] = body + "\n"

    return sections


def _build_content(sections: dict[str, str | None]) -> str:
    """Build markdown content from section dict."""
    parts = []
    for key, header in [("input", "Input"), ("analysis", "Analysis"), ("tasks", "Tasks")]:
        value = sections.get(key)
        if value is not None:
            parts.append(f"## {header}\n\n{value.rstrip()}\n")
    return "\n".join(parts)


def load_collection(name: str, config=None) -> dict | None:
    """Load a collection. Returns dict with name, stage, timestamps, and section content."""
    path = _collection_path(name, config)
    if not path.exists():
        return None
    post = frontmatter.load(str(path))
    sections = _parse_sections(post.content)

    # Count input items (lines starting with -)
    input_content = sections.get("input") or ""
    item_count = sum(1 for line in input_content.split("\n") if line.strip().startswith("-"))

    return {
        "name": post.metadata.get("name", name),
        "stage": post.metadata.get("stage", "raw"),
        "created": post.metadata.get("created", ""),
        "analyzed_at": post.metadata.get("analyzed_at"),
        "executed_at": post.metadata.get("executed_at"),
        "input_content": sections["input"],
        "analysis_content": sections["analysis"],
        "tasks_content": sections["tasks"],
        "item_count": item_count,
        "raw_content": post.content,
    }


def save_collection(name: str, stage: str, sections: dict[str, str | None], config=None) -> Path:
    """Save a collection with stage and sectioned content."""
    path = _collection_path(name, config)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing metadata if file exists
    existing_meta = {}
    if path.exists():
        existing_post = frontmatter.load(str(path))
        existing_meta = dict(existing_post.metadata)

    now = datetime.now(timezone.utc).astimezone().isoformat()
    meta = {
        "name": name,
        "stage": stage,
        "created": existing_meta.get("created", now),
    }
    # Preserve and set timestamps
    if stage == "analyzed" or existing_meta.get("analyzed_at"):
        meta["analyzed_at"] = existing_meta.get("analyzed_at") or now
    if stage == "executed" or existing_meta.get("executed_at"):
        meta["executed_at"] = existing_meta.get("executed_at") or now
    # If transitioning to analyzed right now, set it
    if stage == "analyzed" and not existing_meta.get("analyzed_at"):
        meta["analyzed_at"] = now
    if stage == "executed" and not existing_meta.get("executed_at"):
        meta["executed_at"] = now

    content = _build_content(sections)
    post = frontmatter.Post(content=content, **meta)
    path.write_text(frontmatter.dumps(post))
    return path


def append_to_collection(name: str, items: list[str], config=None) -> Path | None:
    """Append items to the Input section. Only valid for 'raw' stage or new collections."""
    existing = load_collection(name, config)
    if existing and existing["stage"] != "raw":
        return None  # reject — collection is past raw stage

    if existing:
        input_content = (existing["input_content"] or "").rstrip() + "\n"
        for item in items:
            input_content += f"{item}\n"
        return save_collection(name, "raw", {"input": input_content}, config)
    else:
        input_content = "\n".join(items) + "\n"
        return save_collection(name, "raw", {"input": input_content}, config)


def list_collections(config=None) -> list[str]:
    """List all collection names (backwards compat)."""
    data_dir = get_data_dir(config)
    collections_dir = data_dir / "collections"
    if not collections_dir.exists():
        return []
    return [p.stem for p in sorted(collections_dir.glob("*.md"))]


def list_collections_with_meta(config=None) -> list[dict]:
    """List all collections with metadata: name, stage, item_count, created."""
    names = list_collections(config)
    result = []
    for name in names:
        coll = load_collection(name, config)
        if coll:
            result.append({
                "name": coll["name"],
                "stage": coll["stage"],
                "item_count": coll["item_count"],
                "created": coll["created"],
            })
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_collections.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/collection_storage.py tests/test_collections.py
git commit -m "feat: rewrite collection storage with sectioned model (Input/Analysis/Tasks)"
```

---

### Task 3: Update Capture — Route `+collection` to Collection Storage

**Files:**
- Modify: `src/bute/commands/capture.py:51-89`
- Test: `tests/test_collections.py` (add capture tests)

- [ ] **Step 1: Write failing tests for capture with collection**

Append to `tests/test_collections.py`:

```python
from bute.cli import main
from bute.config import default_config, save_config


def _setup(tmp_config, tmp_data):
    doc = default_config(provider="anthropic")
    doc["ai"]["api_key"] = "sk-test"
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


def test_capture_with_collection(runner, tmp_config, tmp_data):
    """bt t fix faucet +home-reno → adds to collection, no entry created."""
    _setup(tmp_config, tmp_data)
    result = runner.invoke(main, ["t", "fix", "faucet", "+home-reno"])
    assert result.exit_code == 0
    assert "+home-reno" in result.output

    coll = load_collection("home-reno")
    assert coll is not None
    assert "fix faucet" in coll["input_content"]

    # No entry should be created
    from bute.storage import load_entries_by_filter
    entries = load_entries_by_filter(lambda e: True)
    assert len(entries) == 0


def test_capture_with_collection_preserves_signifier(runner, tmp_config, tmp_data):
    """Signifier bullet is preserved in collection item."""
    _setup(tmp_config, tmp_data)
    runner.invoke(main, ["t", "fix", "faucet", "+test-coll"])
    runner.invoke(main, ["n", "kitchen", "is", "12x15", "+test-coll"])

    coll = load_collection("test-coll")
    assert ". fix faucet" in coll["input_content"]
    assert "- kitchen is 12x15" in coll["input_content"]


def test_capture_with_collection_preserves_tags_and_meta(runner, tmp_config, tmp_data):
    """Tags and metadata are preserved in the raw line."""
    _setup(tmp_config, tmp_data)
    runner.invoke(main, ["t", "fix", "faucet", "+test-coll", "@plumbing", "due:friday"])

    coll = load_collection("test-coll")
    content = coll["input_content"]
    assert "fix faucet" in content
    assert "@plumbing" in content
    assert "due:friday" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_collections.py::test_capture_with_collection tests/test_collections.py::test_capture_with_collection_preserves_signifier tests/test_collections.py::test_capture_with_collection_preserves_tags_and_meta -v`
Expected: FAIL — capture still creates entries regardless of `+collection`

- [ ] **Step 3: Add collection handling to capture_cmd**

Modify `src/bute/commands/capture.py`. After `parsed = parse_capture_tokens(tokens)` (line 51), add the collection branch:

```python
    parsed = parse_capture_tokens(tokens)

    # Collection capture — add to collection, no entry created
    if parsed.collection:
        from bute.collection_storage import append_to_collection
        from bute.models import SIGNIFIER_MAP
        from rich.console import Console

        console = Console()

        entry_type = SIGNIFIER_MAP[parsed.signifier]
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

        result = append_to_collection(parsed.collection, [f"- {raw_line}"], config=ctx.obj.get("config"))
        if result is None:
            console.print(f"  [red]Cannot add to +{parsed.collection} — already processed.[/red]")
            return

        coll = load_collection(parsed.collection, config=ctx.obj.get("config"))
        count = coll["item_count"] if coll else 0
        console.print(f"  [green]Added to +{parsed.collection} ({count} items)[/green]")
        return

    entry_type = SIGNIFIER_MAP[parsed.signifier]
```

Also add the import at the top of the file:

```python
from bute.collection_storage import append_to_collection, load_collection
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_collections.py::test_capture_with_collection tests/test_collections.py::test_capture_with_collection_preserves_signifier tests/test_collections.py::test_capture_with_collection_preserves_tags_and_meta -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest -v`
Expected: All PASS (existing tests unaffected since no existing tests use `+` tokens)

- [ ] **Step 6: Commit**

```bash
git add src/bute/commands/capture.py tests/test_collections.py
git commit -m "feat: route +collection captures to collection storage instead of creating entries"
```

---

### Task 4: AI Prompts — Analyze and Execute

**Files:**
- Modify: `src/bute/ai/prompts.py:65-109` (replace form/focus/finish with analyze/execute)
- Test: `tests/test_collections.py` (add prompt tests)

- [ ] **Step 1: Write failing tests for new prompts**

Append to `tests/test_collections.py`:

```python
from bute.ai.prompts import analyze_prompt, execute_prompt


def test_analyze_prompt_contains_signifier_key():
    prompt = analyze_prompt()
    assert ". = task" in prompt
    assert "- = note" in prompt
    assert "= = journal" in prompt
    assert "o = calendar" in prompt


def test_execute_prompt_contains_sequencing():
    prompt = execute_prompt()
    assert "sequen" in prompt.lower()
    assert "verb" in prompt.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_collections.py::test_analyze_prompt_contains_signifier_key tests/test_collections.py::test_execute_prompt_contains_sequencing -v`
Expected: FAIL — `analyze_prompt` and `execute_prompt` don't exist

- [ ] **Step 3: Replace form/focus/finish prompts with analyze/execute**

In `src/bute/ai/prompts.py`, replace the `form_prompt`, `focus_prompt`, and `finish_prompt` functions (lines 65-109) with:

```python
def analyze_prompt() -> str:
    return f"""{SYSTEM_BASE}

The user has gathered raw items for a collection. Each item has a signifier prefix indicating its type:
  . = task idea or intention
  - = note, reference, or fact
  = = journal reflection or feeling
  o = calendar event or commitment

Cluster these items into coherent themes. For each theme:
- Give it a clear, concise name
- List the items that belong to it
- Briefly note connections or tensions between items

Be faithful to the original items — don't add, remove, or rephrase.
Organize what's there. Use the item types as context (journals reveal feelings, notes are facts, tasks are intentions, events are commitments)."""


def execute_prompt() -> str:
    return f"""{SYSTEM_BASE}

The user has an analyzed collection — items clustered into themes. Generate a sequenced list of concrete, actionable tasks that would implement or address these themes.

Requirements:
- Each task starts with a verb
- Tasks are specific enough to act on in a single session
- Tasks are ordered sequentially — each builds on the previous
- Number each task (1, 2, 3...)
- Keep the total manageable (aim for 5-15 tasks)

Output only the numbered task list, nothing else."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_collections.py::test_analyze_prompt_contains_signifier_key tests/test_collections.py::test_execute_prompt_contains_sequencing -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/bute/ai/prompts.py tests/test_collections.py
git commit -m "feat: replace form/focus/finish prompts with analyze/execute"
```

---

### Task 5: Collection Commands — Analyze, Execute, View, List

**Files:**
- Create: `src/bute/commands/collections.py`
- Test: `tests/test_collections.py` (add command tests)

- [ ] **Step 1: Write failing tests for collection commands**

Append to `tests/test_collections.py`:

```python
from unittest.mock import MagicMock, patch


def _mock_llm(response="**Theme A**\n- item one\n- item two"):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = response
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    return patch("bute.ai.llm._get_client", return_value=mock_client)


def test_view_collection(runner, tmp_config, tmp_data):
    """bt +test-coll shows collection content."""
    _setup(tmp_config, tmp_data)
    save_collection("test-coll", "raw", {"input": "- . fix faucet\n- - measure kitchen\n"})

    result = runner.invoke(main, ["+test-coll"])
    assert result.exit_code == 0
    assert "test-coll" in result.output
    assert "fix faucet" in result.output


def test_view_missing_collection(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    result = runner.invoke(main, ["+nonexistent"])
    assert "not found" in result.output


def test_analyze_raw_collection(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    save_collection("test", "raw", {"input": "- . item one\n- . item two\n"})

    with _mock_llm("**Theme A**\n- item one\n- item two"):
        result = runner.invoke(main, ["+test", "analyze"], input="y\n")

    assert result.exit_code == 0
    coll = load_collection("test")
    assert coll["stage"] == "analyzed"
    assert coll["analysis_content"] is not None
    assert coll["input_content"] is not None  # preserved


def test_analyze_rejects_already_analyzed(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    save_collection("test", "analyzed", {
        "input": "- . item\n",
        "analysis": "**Theme**\n- item\n",
    })

    result = runner.invoke(main, ["+test", "analyze"])
    assert "already analyzed" in result.output.lower()


def test_execute_analyzed_collection(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    save_collection("test", "analyzed", {
        "input": "- . item one\n",
        "analysis": "**Theme A**\n- item one\n",
    })

    with _mock_llm("1. Create the landing page\n2. Write unit tests"):
        result = runner.invoke(main, ["+test", "execute"], input="y\n")

    assert result.exit_code == 0

    # Verify tasks were created
    from bute.models import EntryType
    from bute.storage import load_entries_by_filter
    tasks = load_entries_by_filter(lambda e: e.type == EntryType.TASK)
    task_bodies = [t.body for t in tasks]
    assert "Create the landing page" in task_bodies
    assert "Write unit tests" in task_bodies

    # Verify collection metadata
    for t in tasks:
        assert t.extra_meta.get("collection") == "test"
        assert "test" in t.tags

    # Verify collection stage
    coll = load_collection("test")
    assert coll["stage"] == "executed"
    assert coll["tasks_content"] is not None


def test_execute_raw_runs_analyze_first(runner, tmp_config, tmp_data):
    """Execute on raw collection should analyze first, then generate tasks."""
    _setup(tmp_config, tmp_data)
    save_collection("test", "raw", {"input": "- . item one\n"})

    # First call returns analysis, second returns tasks
    analyze_response = "**Theme A**\n- item one"
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
        result = runner.invoke(main, ["+test", "execute"], input="y\ny\n")

    assert result.exit_code == 0
    coll = load_collection("test")
    assert coll["stage"] == "executed"


def test_collections_list(runner, tmp_config, tmp_data):
    """bt collections shows all collections."""
    _setup(tmp_config, tmp_data)
    save_collection("alpha", "raw", {"input": "- . a\n- . b\n"})
    save_collection("beta", "analyzed", {
        "input": "- . c\n",
        "analysis": "**Theme**\n- c\n",
    })

    result = runner.invoke(main, ["collections"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_collections.py::test_view_collection tests/test_collections.py::test_analyze_raw_collection tests/test_collections.py::test_execute_analyzed_collection tests/test_collections.py::test_collections_list -v`
Expected: FAIL — commands don't exist

- [ ] **Step 3: Create `src/bute/commands/collections.py`**

```python
"""Collection commands — view, analyze, execute, list."""

import re

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from bute.collection_storage import (
    list_collections_with_meta,
    load_collection,
    save_collection,
)

console = Console()


def _run_analyze(collection_name: str, coll: dict, config) -> str | None:
    """Run the analyze stage. Returns analysis text or None if rejected."""
    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send
    from bute.ai.prompts import analyze_prompt

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return None

    input_content = coll["input_content"] or ""
    console.print(f"  [dim]Analyzing {coll['item_count']} items...[/dim]")

    response = llm_send(analyze_prompt(), f"Collection: \"{collection_name}\"\n\nItems:\n{input_content}", config)
    console.print(f"\n{response}")

    if click.confirm("\n  Accept this analysis?", default=True):
        sections = {
            "input": coll["input_content"],
            "analysis": response + "\n",
        }
        save_collection(collection_name, "analyzed", sections, config)
        console.print(f"  [green]Collection '{collection_name}' → analyzed[/green]")
        return response
    else:
        console.print(f"  [dim]Analysis discarded. Raw items preserved. Run analyze again when ready.[/dim]")
        return None


@click.command("view_collection", hidden=True)
@click.argument("collection_name")
@click.pass_context
def view_collection_cmd(ctx, collection_name):
    """View a collection's full trail."""
    config = ctx.obj.get("config")
    coll = load_collection(collection_name, config)
    if coll is None:
        console.print(f"  [red]Collection '{collection_name}' not found.[/red]")
        return

    display_collection(coll)


@click.command("analyze_collection", hidden=True)
@click.argument("collection_name")
@click.pass_context
def analyze_collection_cmd(ctx, collection_name):
    """AI analyzes and clusters raw collection items."""
    config = ctx.obj.get("config")
    coll = load_collection(collection_name, config)
    if coll is None:
        console.print(f"  [red]Collection '{collection_name}' not found.[/red]")
        return

    if coll["stage"] != "raw":
        console.print(f"  [yellow]Already analyzed. View with [bold]bt +{collection_name}[/bold][/yellow]")
        return

    _run_analyze(collection_name, coll, config)


@click.command("execute_collection", hidden=True)
@click.argument("collection_name")
@click.pass_context
def execute_collection_cmd(ctx, collection_name):
    """AI generates sequenced tasks from collection (analyzes first if needed)."""
    from bute.ai import _LLM_INSTALL_MSG, embed_entry, is_llm_available, llm_send
    from bute.ai.prompts import execute_prompt
    from bute.display import confirm_capture
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    config = ctx.obj.get("config")
    coll = load_collection(collection_name, config)
    if coll is None:
        console.print(f"  [red]Collection '{collection_name}' not found.[/red]")
        return

    if coll["stage"] == "executed":
        console.print(f"  [yellow]Already executed. View with [bold]bt +{collection_name}[/bold][/yellow]")
        return

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    # If raw, run analyze first
    analysis_content = coll.get("analysis_content")
    if coll["stage"] == "raw":
        console.print(f"  [dim]Collection is raw. Running analysis first...[/dim]")
        analysis_content = _run_analyze(collection_name, coll, config)
        if analysis_content is None:
            return  # user rejected analysis
        # Reload collection after analyze saved it
        coll = load_collection(collection_name, config)
        analysis_content = coll["analysis_content"]

    # Generate tasks
    console.print(f"  [dim]Generating tasks...[/dim]")
    response = llm_send(execute_prompt(), f"Collection: \"{collection_name}\"\n\nAnalysis:\n{analysis_content}", config)
    console.print(f"\n{response}")

    if not click.confirm("\n  Create these tasks?", default=True):
        console.print(f"  [dim]Task generation discarded. Analysis preserved. Run execute again when ready.[/dim]")
        return

    # Parse numbered tasks (lines starting with digit or -)
    tasks = []
    for line in response.split("\n"):
        stripped = line.strip()
        # Match "1. Task text" or "- Task text"
        numbered = re.match(r"^\d+\.\s+(.+)$", stripped)
        bulleted = re.match(r"^-\s+(.+)$", stripped)
        if numbered:
            tasks.append(numbered.group(1))
        elif bulleted:
            tasks.append(bulleted.group(1))

    safe_tag = collection_name.lower().replace(" ", "-")
    for task_text in tasks:
        entry = Entry.create(
            entry_type=EntryType.TASK,
            body=task_text,
            tags=[safe_tag],
            extra_meta={"collection": collection_name},
        )
        save_entry(entry, config)
        embed_entry(entry.id, entry.body, config)
        confirm_capture(entry)

    # Save collection as executed with all sections
    sections = {
        "input": coll["input_content"],
        "analysis": coll["analysis_content"],
        "tasks": response + "\n",
    }
    save_collection(collection_name, "executed", sections, config)
    console.print(f"  [green]{len(tasks)} tasks created from +{collection_name}[/green]")


@click.command("collections")
@click.pass_context
def collections_list_cmd(ctx):
    """List all collections."""
    from rich.table import Table

    from bute.state import save_state

    config = ctx.obj.get("config")
    meta = list_collections_with_meta(config)

    if not meta:
        console.print("  [dim]No collections found.[/dim]")
        return

    stage_colors = {"raw": "dim", "analyzed": "yellow", "executed": "green"}

    table = Table(
        title="Collections",
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
    )
    table.add_column("#", style="bold dim", width=3, justify="right")
    table.add_column("Name", style="bold")
    table.add_column("Stage")
    table.add_column("Items", justify="right")

    for i, m in enumerate(meta, 1):
        color = stage_colors.get(m["stage"], "dim")
        table.add_row(
            str(i),
            m["name"],
            f"[{color}]{m['stage']}[/{color}]",
            str(m["item_count"]),
        )

    console.print()
    console.print(table)

    # Save state so bt <n> can drill into a collection
    save_state("collections", [m["name"] for m in meta], config)


def display_collection(coll: dict) -> None:
    """Render a collection's full trail as a Rich Panel."""
    stage = coll["stage"]
    name = coll["name"]
    stage_colors = {"raw": "dim", "analyzed": "yellow", "executed": "green"}
    border_color = stage_colors.get(stage, "dim")

    body = Text()

    # Input section
    if coll["input_content"]:
        body.append("  ▸ INPUT", style="bold")
        body.append(f" — {coll['item_count']} entries\n", style="dim")
        for line in coll["input_content"].strip().split("\n"):
            stripped = line.strip()
            if stripped.startswith("- "):
                stripped = stripped[2:]
            # Color by signifier bullet
            if stripped.startswith(". "):
                body.append(f"    {stripped}\n", style="cyan")
            elif stripped.startswith("- "):
                body.append(f"    {stripped}\n", style="yellow")
            elif stripped.startswith("= "):
                body.append(f"    {stripped}\n", style="magenta")
            elif stripped.startswith("o "):
                body.append(f"    {stripped}\n", style="green")
            else:
                body.append(f"    {stripped}\n")

    # Analysis section
    if coll["analysis_content"]:
        body.append("\n")
        body.append("  ▸ ANALYSIS\n", style="bold")
        for line in coll["analysis_content"].strip().split("\n"):
            body.append(f"    {line}\n")

    # Tasks section
    if coll["tasks_content"]:
        body.append("\n")
        body.append("  ▸ TASKS\n", style="bold")
        for line in coll["tasks_content"].strip().split("\n"):
            body.append(f"    {line}\n")

    title = Text()
    title.append(f" {name} ", style="bold")
    title.append(f"({stage})", style=border_color)

    panel = Panel(
        body,
        title=title,
        border_style=border_color,
        padding=(0, 1),
    )
    console.print(panel)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_collections.py -v`
Expected: All PASS (except CLI dispatch tests — those need Task 6)

Note: The `test_view_collection`, `test_analyze_raw_collection`, `test_execute_analyzed_collection`, `test_execute_raw_runs_analyze_first`, and `test_collections_list` tests may fail until Task 6 (CLI dispatch) wires the commands. If so, proceed to Task 6 before re-running.

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/collections.py tests/test_collections.py
git commit -m "feat: add collection commands — view, analyze, execute, list"
```

---

### Task 6: CLI Dispatch — Wire `+collection` and Remove FFFF

**Files:**
- Modify: `src/bute/cli.py` (dispatch + registrations + help text)
- Test: `tests/test_collections.py` (already written in Task 5)

- [ ] **Step 1: Add `+collection` dispatch to resolve_command**

In `src/bute/cli.py`, add a new section in `resolve_command()` after section 4 (tag filter, line 94-97) and before section 5 (number-action, line 99):

```python
        # 4. Tag filter — @tagname
        if first.startswith("@") and len(first) > 1:
            cmd = self.get_command(ctx, "tag_filter")
            if cmd is not None:
                return "tag_filter", cmd, [first[1:]]

        # 5. Collection — +name [subcommand]
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

        # 6. Number-action — first token is a digit
        if first.isdigit():
```

- [ ] **Step 2: Handle collections view in number-action dispatch**

In `resolve_command()`, inside the number-action section, after the habits check, add a check for collections view state:

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

Add this right after the habits block (after line 128) and before the fallback to `action_cmd` (line 129).

- [ ] **Step 3: Handle `+collection` in signifier dispatch for capture**

In section 3 (signifier check), the `is_view_args` check needs to also account for `+collection` tokens so they don't prevent routing to capture. Currently line 61-62:

```python
            is_view_args = rest and all(
                r.startswith("@") or r in view_flags for r in rest
            )
```

Update to:

```python
            is_view_args = rest and all(
                r.startswith("@") or r in view_flags for r in rest
            )
```

No change needed here — `+collection` tokens don't start with `@` and aren't view flags, so `is_view_args` will be False when `+collection` is present, and `has_text` will be True. The capture command will fire and the parser handles the `+` token. This already works correctly.

- [ ] **Step 4: Update imports and command registration**

Replace the FFFF import and registration (lines 305, 336-339):

Remove:
```python
from bute.commands.ffff import find_cmd, form_cmd, focus_cmd, finish_cmd  # noqa: E402
```

```python
main.add_command(find_cmd)
main.add_command(form_cmd)
main.add_command(focus_cmd)
main.add_command(finish_cmd)
```

Add:
```python
from bute.commands.collections import (  # noqa: E402
    analyze_collection_cmd,
    collections_list_cmd,
    execute_collection_cmd,
    view_collection_cmd,
)
```

```python
main.add_command(analyze_collection_cmd)
main.add_command(execute_collection_cmd)
main.add_command(view_collection_cmd)
main.add_command(collections_list_cmd)
```

- [ ] **Step 5: Update help text**

In `_print_help()`, replace the FFFF section (lines 222-228) with:

```python
    # Collections
    console.print("  [bold cyan]Collections[/bold cyan] — ideas to action")
    console.print("    [bold]bt +[/bold]<name>                View collection (full trail)")
    console.print("    [bold]bt +[/bold]<name> [bold]analyze[/bold]     AI clusters and organizes")
    console.print("    [bold]bt +[/bold]<name> [bold]execute[/bold]     AI generates sequenced tasks")
    console.print("    [bold]bt collections[/bold]           List all collections")
    console.print("    Capture to collection: [dim]bt t fix faucet +home-reno[/dim]")
    console.print()
```

Also add a note in the Capture section (after line 158):

```python
    console.print("    Add [bold]+collection[/bold] to collect: [dim]bt t fix faucet +home-reno[/dim]")
```

- [ ] **Step 6: Run the collection command tests**

Run: `uv run pytest tests/test_collections.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -v`
Expected: May see failures in `tests/test_ffff.py` since FFFF commands are removed. This is expected and handled in Task 7.

- [ ] **Step 8: Commit**

```bash
git add src/bute/cli.py
git commit -m "feat: wire +collection dispatch in CLI, remove FFFF commands, update help"
```

---

### Task 7: Display `+collection` in Entry Meta and Clean Up

**Files:**
- Modify: `src/bute/display.py:89-96` (show `+collection` in meta)
- Delete: `src/bute/commands/ffff.py`
- Delete: `tests/test_ffff.py`
- Test: `tests/test_collections.py` (add display test)

- [ ] **Step 1: Write failing test for collection display in entry meta**

Append to `tests/test_collections.py`:

```python
from bute.display import _build_entry_row
from bute.models import Entry, EntryType


def test_entry_row_shows_collection_meta():
    entry = Entry.create(
        EntryType.TASK,
        "fix faucet",
        tags=["home-reno"],
        extra_meta={"collection": "home-reno"},
    )
    _num, _icon, _body, meta = _build_entry_row(1, entry)
    assert "+home-reno" in meta
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_collections.py::test_entry_row_shows_collection_meta -v`
Expected: FAIL — meta shows `@home-reno` not `+home-reno`

- [ ] **Step 3: Update `_build_entry_row` to show `+collection`**

In `src/bute/display.py`, modify `_build_entry_row` (lines 89-96). Replace the tags rendering:

```python
    meta_parts = []
    if entry.due:
        meta_parts.append(f"due:{entry.due}")
    if entry.scheduled_time:
        meta_parts.append(format_time_display(entry.scheduled_time))
    # Show +collection if present (before tags, to distinguish)
    collection = entry.extra_meta.get("collection")
    if collection:
        meta_parts.append(f"+{collection}")
    if entry.tags:
        # Skip the collection tag in @tags since it's shown as +collection
        collection_tag = collection.lower().replace(" ", "-") if collection else None
        meta_parts.extend(f"@{t}" for t in entry.tags if t != collection_tag)
    meta = " ".join(meta_parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_collections.py::test_entry_row_shows_collection_meta -v`
Expected: PASS

- [ ] **Step 5: Delete old FFFF files**

```bash
rm src/bute/commands/ffff.py
rm tests/test_ffff.py
```

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: show +collection in entry meta, remove old FFFF pipeline"
```

---

### Task 8: Manual Integration Test

**Files:** None (manual testing)

- [ ] **Step 1: Install globally for manual testing**

```bash
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall
```

- [ ] **Step 2: Test capture to collection**

```bash
bt t fix kitchen faucet +test-reno
bt n kitchen is 12x15 +test-reno
bt j feeling overwhelmed +test-reno
```

Verify: each prints `Added to +test-reno (N items)`

- [ ] **Step 3: Test collection view**

```bash
bt +test-reno
```

Verify: shows panel with INPUT section, 3 entries, signifier-colored items

- [ ] **Step 4: Test collections list**

```bash
bt collections
```

Verify: shows table with test-reno, stage=raw, items=3

- [ ] **Step 5: Test help text**

```bash
bt --help
```

Verify: Collections section shows `bt +<name>`, `bt +<name> analyze`, `bt +<name> execute`, `bt collections`. No FFFF section.

- [ ] **Step 6: Test analyze (requires AI config)**

```bash
bt +test-reno analyze
```

Verify: AI clusters items, prompts for confirmation, collection advances to analyzed

- [ ] **Step 7: Test execute (requires AI config)**

```bash
bt +test-reno execute
```

Verify: AI generates tasks, prompts for confirmation, tasks appear in `bt t`

- [ ] **Step 8: Verify tasks show +collection**

```bash
bt t
```

Verify: tasks from collection show `+test-reno` in meta column

- [ ] **Step 9: Clean up test collection**

```bash
rm ~/bute/collections/test-reno.md
```

- [ ] **Step 10: Commit all final changes (if any fixups needed)**

```bash
git add -A
git commit -m "fix: integration test fixups for collections"
```

---

### Task 9: Update CLAUDE.md Backlog and Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md**

In the CLI Grammar section, add collection syntax:

```
**Collections** — ideas to action:
```
bt t fix faucet +home-reno          # add task to collection
bt n kitchen is 12x15 +home-reno    # add note to collection
bt +home-reno                       # view collection (full trail)
bt +home-reno analyze               # AI clusters and organizes
bt +home-reno execute               # AI generates sequenced tasks
bt collections                      # list all collections
```
```

In the Key Modules table, update the ffff entry:

```
| `commands/collections.py` | Collection view, analyze, execute, list commands |
```

Replace FFFF references in the AI Architecture section and Data Flow section as appropriate.

In the Backlog, mark "Notes as reference layer" as partially addressed by collections. Remove any FFFF references.

In the Design Decisions section, add:

```
- **Collections replace FFFF** — `+collection` capture syntax, two AI stages (analyze, execute) instead of four (find/form/focus/finish). Collections are super notes (analyzed) or super tasks (executed).
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for collections — replace FFFF references"
```
