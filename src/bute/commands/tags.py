"""Tag processing commands — analyze and execute."""

import re

import click
from rich.console import Console

from bute.db import get_tag_stage, upsert_tag_stage

console = Console()


def _format_analysis_for_note(tag: str, response: str) -> str:
    """Convert THEME: structured response into clean markdown for storage."""
    lines = [f"@{tag} analysis"]
    current_theme = None

    for line in response.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("THEME:"):
            current_theme = stripped[6:].strip()
            lines.append(f"\n## {current_theme}")
        elif stripped and current_theme is not None:
            lines.append(f"  {stripped}")

    return "\n".join(lines)


def _load_tagged_entries(tag: str, config=None):
    """Load all entries with the given tag."""
    from bute.storage import query_and_load

    return query_and_load(config, tag=tag)


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
    from bute.display import display_analyze_tree
    display_analyze_tree(display_name, response)

    if click.confirm("\n  Accept this analysis?", default=True):
        if tag:
            upsert_tag_stage(tag, "analyzed", analysis=response, config=config)

        # Save analysis as a note for future reference
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

        # Offer mind map view
        if click.confirm("  View as mind map?", default=False):
            from bute.display import display_analyze_map
            display_analyze_map(display_name, response)

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


@click.command("map_tag", hidden=True)
@click.argument("tag_name")
@click.pass_context
def map_tag_cmd(ctx, tag_name):
    """Render a mind map for a tag — uses existing analysis or runs one on the fly."""
    from bute.display import display_analyze_map

    config = ctx.obj.get("config")

    # Check for existing analysis
    stage_row = get_tag_stage(tag_name, config=config)
    analysis = stage_row["analysis"] if stage_row else None

    if analysis:
        display_analyze_map(tag_name, analysis)
        return

    # No analysis — run one on the fly
    entries = _load_tagged_entries(tag_name, config)
    if not entries:
        console.print(f"  [dim]No entries found with @{tag_name}.[/dim]")
        return

    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send
    from bute.ai.prompts import analyze_prompt, format_entries

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    console.print(f"  [dim]Analyzing {len(entries)} entries for @{tag_name}...[/dim]")
    formatted = format_entries(entries)
    response = llm_send(analyze_prompt(), f"Tag: \"@{tag_name}\"\n\nEntries:\n{formatted}", config)

    display_analyze_map(tag_name, response)

    # Offer to save
    if click.confirm("\n  Save this analysis?", default=True):
        from bute.ai import embed_entry
        from bute.display import confirm_capture
        from bute.models import Entry, EntryType
        from bute.storage import save_entry

        upsert_tag_stage(tag_name, "analyzed", analysis=response, config=config)

        entry = Entry.create(
            entry_type=EntryType.NOTE,
            body=_format_analysis_for_note(tag_name, response),
            tags=[tag_name, "ai-analysis"],
        )
        save_entry(entry, config)
        embed_entry(entry.id, entry.body, config)
        confirm_capture(entry)
        console.print(f"  [green]@{tag_name} → analyzed[/green]")


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

    stage_row = get_tag_stage(tag_name, config=config)
    analysis_content = stage_row["analysis"] if stage_row else None

    if not analysis_content:
        console.print(f"  [dim]No analysis found. Running analysis first...[/dim]")
        analysis_content = _run_analyze(tag_name, entries, config)
        if analysis_content is None:
            return

    console.print(f"  [dim]Generating tasks...[/dim]")
    response = llm_send(execute_prompt(), f"Tag: \"@{tag_name}\"\n\nAnalysis:\n{analysis_content}", config)
    console.print(f"\n{response}")

    if not click.confirm("\n  Create these tasks?", default=True):
        console.print(f"  [dim]Task generation discarded. Analysis preserved. Run execute again when ready.[/dim]")
        return

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
