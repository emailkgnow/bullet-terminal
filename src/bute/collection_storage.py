"""Collection storage for FFFF pipeline — Markdown with YAML frontmatter."""

from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from bute.config import get_data_dir


def _collection_path(name: str, config=None) -> Path:
    """Return path to ~/bute/collections/<name>.md"""
    data_dir = get_data_dir(config)
    safe_name = name.lower().replace(" ", "-")
    return data_dir / "collections" / f"{safe_name}.md"


def load_collection(name: str, config=None) -> dict | None:
    """Load a collection. Returns dict with 'name', 'stage', 'items', or None."""
    path = _collection_path(name, config)
    if not path.exists():
        return None
    post = frontmatter.load(str(path))
    items = [line.lstrip("- ").strip() for line in post.content.strip().split("\n") if line.strip()]
    return {
        "name": post.metadata.get("name", name),
        "stage": post.metadata.get("stage", "raw"),
        "created": post.metadata.get("created", ""),
        "items": items,
        "raw_content": post.content,
    }


def save_collection(
    name: str, stage: str, content: str, config=None
) -> Path:
    """Save a collection with stage and content."""
    path = _collection_path(name, config)
    path.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "name": name,
        "stage": stage,
        "created": datetime.now(timezone.utc).astimezone().isoformat(),
    }
    post = frontmatter.Post(content=content, **meta)
    path.write_text(frontmatter.dumps(post))
    return path


def append_to_collection(name: str, items: list[str], config=None) -> Path:
    """Append items to an existing or new collection."""
    existing = load_collection(name, config)
    if existing:
        new_content = existing["raw_content"].rstrip() + "\n"
        for item in items:
            new_content += f"- {item}\n"
        return save_collection(name, existing["stage"], new_content, config)
    else:
        content = "\n".join(f"- {item}" for item in items) + "\n"
        return save_collection(name, "raw", content, config)


def list_collections(config=None) -> list[str]:
    """List all collection names."""
    data_dir = get_data_dir(config)
    collections_dir = data_dir / "collections"
    if not collections_dir.exists():
        return []
    return [p.stem for p in sorted(collections_dir.glob("*.md"))]
