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
