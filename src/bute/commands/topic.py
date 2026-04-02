"""Topic command — cross-dimension AI synthesis."""

import click
from rich.console import Console

from bute.state import save_state

console = Console()


@click.command("topic")
@click.argument("name", nargs=-1, required=True)
@click.pass_context
def topic_cmd(ctx, name):
    """Synthesize everything about a topic across all dimensions."""
    from bute.ai import (
        _LLM_INSTALL_MSG,
        is_embedding_available,
        is_llm_available,
        llm_send_with_entries,
        search_similar,
    )
    from bute.ai.prompts import topic_prompt

    config = ctx.obj.get("config")
    topic_name = " ".join(name)

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    from bute.storage import entry_path_from_id, query_and_load, load_entry

    # Gather entries: by tag + semantic search
    seen_ids = set()
    entries = []

    # Tag matches
    tag_entries = query_and_load(config, tag=topic_name.lower())
    for e in tag_entries:
        if e.id not in seen_ids:
            entries.append(e)
            seen_ids.add(e.id)

    # Semantic search (if embeddings available)
    if is_embedding_available():
        results = search_similar(topic_name, limit=10, config=config)
        for entry_id, _distance in results:
            if entry_id not in seen_ids:
                path = entry_path_from_id(entry_id, config)
                if path:
                    entries.append(load_entry(path))
                    seen_ids.add(entry_id)

    if not entries:
        console.print(f"  [dim]No entries found for '{topic_name}'.[/dim]")
        return

    # Truncate to avoid token limits
    entries = entries[:50]

    console.print(f"  [dim]Synthesizing {len(entries)} entries about '{topic_name}'...[/dim]")
    response = llm_send_with_entries(
        topic_prompt(topic_name),
        entries,
        f"Synthesize everything about: {topic_name}",
        config,
    )
    console.print(f"\n{response}")

    save_state("topic", [e.id for e in entries], config)
