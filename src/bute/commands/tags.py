"""Tag processing commands — analyze."""

import click
from rich.console import Console

from bute.db import get_tag_stage, upsert_tag_stage

console = Console()


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


def _run_analyze(tag: str, entries, config, *, label: str | None = None) -> str | None:
    """Run the analyze stage. Returns analysis text or None if rejected.

    Args:
        tag: The tag name (used for tag_stages and note tagging).
             Pass empty string when using label override.
        entries: Pre-loaded entries to analyze.
        config: App config.
        label: Display label override. If set, used in display and note body
               instead of tag. tag_stages is skipped when label is set.
    """
    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send
    from bute.ai.prompts import analyze_prompt, format_entries

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return None

    display_name = label or tag
    console.print(f"  [dim]Analyzing {len(entries)} entries for @{display_name}...[/dim]")

    formatted = format_entries(entries)
    response = llm_send(analyze_prompt(), f"Tag: \"@{display_name}\"\n\nEntries:\n{formatted}", config)
    from bute.display import display_analyze_map
    display_analyze_map(display_name, response)

    if click.confirm("\n  Save this analysis?", default=True):
        if tag:
            upsert_tag_stage(tag, "analyzed", analysis=response, config=config)

        # Save analysis as a clean markdown note
        from bute.ai import embed_entry
        from bute.display import confirm_capture
        from bute.models import Entry, EntryType
        from bute.storage import save_entry

        note_tags = [tag, "ai-analysis"] if tag else [display_name, "ai-analysis"]
        entry = Entry.create(
            entry_type=EntryType.NOTE,
            body=_format_analysis_for_note(display_name, response),
            tags=note_tags,
        )
        save_entry(entry, config)
        embed_entry(entry.id, entry.body, config)
        confirm_capture(entry)

        console.print(f"  [green]@{display_name} → analyzed[/green]")

        return response
    else:
        console.print(f"  [dim]Analysis discarded. Run analyze again when ready.[/dim]")
        return None


@click.command("analyze_tag", hidden=True)
@click.argument("tags", nargs=-1)
@click.option("--exclude", "-x", multiple=True)
@click.pass_context
def analyze_tag_cmd(ctx, tags, exclude):
    """AI analyzes entries matching tag filters."""
    config = ctx.obj.get("config")
    include_tags = list(tags)
    exclude_tags = list(exclude)

    entries = _load_filtered_entries(include_tags, exclude_tags, config)
    label = " ".join(f"@{t}" for t in include_tags)
    if exclude_tags:
        label += " " + " ".join(f"-@{t}" for t in exclude_tags)

    if not entries:
        console.print(f"  [dim]No entries found with {label}.[/dim]")
        return

    tag_for_stage = include_tags[0] if len(include_tags) == 1 and not exclude_tags else ""
    _run_analyze(tag_for_stage, entries, config, label=label if not tag_for_stage else None)


@click.command("map_tag", hidden=True)
@click.argument("tags", nargs=-1)
@click.option("--exclude", "-x", multiple=True)
@click.pass_context
def map_tag_cmd(ctx, tags, exclude):
    """Render a mind map for a tag — uses existing analysis or runs one on the fly."""
    from bute.display import display_analyze_map

    config = ctx.obj.get("config")
    include_tags = list(tags)
    exclude_tags = list(exclude)

    label = " ".join(f"@{t}" for t in include_tags)
    if exclude_tags:
        label += " " + " ".join(f"-@{t}" for t in exclude_tags)

    # Check for existing analysis (only for single-tag, no excludes)
    if len(include_tags) == 1 and not exclude_tags:
        stage_row = get_tag_stage(include_tags[0], config=config)
        analysis = stage_row["analysis"] if stage_row else None
        if analysis:
            display_analyze_map(include_tags[0], analysis)
            return

    # No analysis — run one on the fly
    entries = _load_filtered_entries(include_tags, exclude_tags, config)
    if not entries:
        console.print(f"  [dim]No entries found with {label}.[/dim]")
        return

    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send
    from bute.ai.prompts import analyze_prompt, format_entries

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    console.print(f"  [dim]Analyzing {len(entries)} entries for {label}...[/dim]")
    formatted = format_entries(entries)
    response = llm_send(analyze_prompt(), f"Tag: \"{label}\"\n\nEntries:\n{formatted}", config)

    display_analyze_map(label, response)

    # Offer to save
    if click.confirm("\n  Save this analysis?", default=True):
        from bute.ai import embed_entry
        from bute.display import confirm_capture
        from bute.models import Entry, EntryType
        from bute.storage import save_entry

        tag_for_stage = include_tags[0] if len(include_tags) == 1 and not exclude_tags else None
        if tag_for_stage:
            upsert_tag_stage(tag_for_stage, "analyzed", analysis=response, config=config)

        note_tags = include_tags + ["ai-analysis"]
        entry = Entry.create(
            entry_type=EntryType.NOTE,
            body=_format_analysis_for_note(label, response),
            tags=note_tags,
        )
        save_entry(entry, config)
        embed_entry(entry.id, entry.body, config)
        confirm_capture(entry)
        console.print(f"  [green]{label} → analyzed[/green]")


