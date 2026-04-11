"""Tag processing commands — analyze."""


def _parse_tag_tokens(tokens: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Parse @tag and -@tag tokens into (include_tags, exclude_tags)."""
    include = []
    exclude = []
    for t in tokens:
        if t.startswith("-@") and len(t) > 2:
            exclude.append(t[2:])
        elif t.startswith("@") and len(t) > 1:
            include.append(t[1:])
        else:
            # Bare word — treat as tag name (for convenience)
            include.append(t)
    return include, exclude


def _format_analysis_for_note(tag: str, response: str) -> str:
    """Convert THEME: structured response into clean markdown with summaries and entries."""
    from bute.display import _parse_analyze_themes

    lines = [f"@{tag} analysis"]
    for theme_name, summary, items in _parse_analyze_themes(response):
        lines.append(f"\n## {theme_name}")
        if summary:
            lines.append(summary)
        for item in items:
            lines.append(f"  {item}")

    return "\n".join(lines)


def _load_tagged_entries(tag: str, config=None):
    """Load all entries with the given tag."""
    from bute.storage import query_and_load

    return query_and_load(config, tag=tag)


def _load_filtered_entries(include_tags: list[str], exclude_tags: list[str], config=None):
    """Load entries matching all include tags, excluding all exclude tags."""
    from bute.storage import query_and_load

    if not include_tags:
        return []
    entries = query_and_load(config, tag=include_tags[0])
    for tag in include_tags[1:]:
        entries = [e for e in entries if tag in e.tags]
    for tag in exclude_tags:
        entries = [e for e in entries if tag not in e.tags]
    return entries


