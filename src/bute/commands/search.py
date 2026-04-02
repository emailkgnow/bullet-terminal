"""Search commands for bute — semantic search, similar, rebuild."""

import click
from rich.console import Console

from bute.display import display_search_results
from bute.state import save_state

console = Console()

_INSTALL_MSG = (
    "  [yellow]Semantic search requires embeddings.[/yellow]\n"
    "  Install with: [bold]uv pip install 'bute[embeddings]'[/bold]"
)


@click.command("search")
@click.argument("query", nargs=-1, required=True)
@click.option("-n", "--limit", default=10, help="Max results.")
@click.pass_context
def search_cmd(ctx, query, limit):
    """Search entries by meaning."""
    from bute.ai import is_embedding_available, search_similar

    if not is_embedding_available():
        console.print(_INSTALL_MSG)
        return

    config = ctx.obj.get("config")
    query_text = " ".join(query)

    results = search_similar(query_text, limit, config)
    if not results:
        console.print("  [dim]No results found.[/dim]")
        return

    from bute.storage import entry_path_from_id, load_entry

    entries = []
    distances = []
    for entry_id, distance in results:
        path = entry_path_from_id(entry_id, config)
        if path is not None:
            entries.append(load_entry(path))
            distances.append(distance)

    display_search_results(entries, distances, query_text)
    save_state("search", [e.id for e in entries], config)


@click.command("similar")
@click.argument("number", type=int)
@click.option("-n", "--limit", default=5, help="Max results.")
@click.pass_context
def similar_cmd(ctx, number, limit):
    """Show entries similar to a numbered entry from the last view."""
    from bute.ai import is_embedding_available

    if not is_embedding_available():
        console.print(_INSTALL_MSG)
        return

    config = ctx.obj.get("config")

    from bute.state import resolve_numbers

    entry_ids = resolve_numbers([number], config)
    entry_id = entry_ids[0]

    from bute.storage import entry_path_from_id, load_entry

    path = entry_path_from_id(entry_id, config)
    if path is None:
        console.print("  [red]Entry not found.[/red]")
        return

    source_entry = load_entry(path)

    from bute.ai.embeddings import embed_text
    from bute.ai.vectors import search

    query_vector = embed_text(source_entry.body)
    results = search(query_vector, limit + 1, config)

    # Filter out the source entry
    entries = []
    distances = []
    for rid, distance in results:
        if rid == entry_id:
            continue
        p = entry_path_from_id(rid, config)
        if p is not None:
            entries.append(load_entry(p))
            distances.append(distance)

    entries = entries[:limit]
    distances = distances[:limit]

    console.print(f"\n  [bold]Similar to:[/bold] {source_entry.body}")
    display_search_results(entries, distances)
    save_state("similar", [e.id for e in entries], config)


@click.command("find")
@click.argument("query", nargs=-1, required=True)
@click.option("-t", "type_filter", flag_value="task", help="Tasks only.")
@click.option("-n", "type_filter", flag_value="note", help="Notes only.")
@click.option("-j", "type_filter", flag_value="journal", help="Journals only.")
@click.option("-c", "type_filter", flag_value="calendar", help="Calendar only.")
@click.option("--limit", default=50, help="Max results.")
@click.pass_context
def find_cmd(ctx, query, type_filter, limit):
    """Find entries by keyword in body text and tags."""
    from bute.db import query_entries, search_text
    from bute.storage import entry_path_from_id, load_entry

    config = ctx.obj.get("config")
    query_text = " ".join(query)

    # FTS5 body search
    body_results = search_text(query_text, type=type_filter, limit=limit, config=config)
    # Tag search — match entries where any tag contains the query
    tag_kwargs = {"tag": query_text.lower()}
    if type_filter:
        tag_kwargs["type"] = type_filter
    tag_results = query_entries(config=config, **tag_kwargs)

    # Deduplicate, body matches first
    seen = set()
    entries = []
    for entry_id, _ in body_results:
        if entry_id not in seen:
            seen.add(entry_id)
            path = entry_path_from_id(entry_id, config)
            if path:
                entries.append(load_entry(path))
    for entry_id, _ in tag_results:
        if entry_id not in seen:
            seen.add(entry_id)
            path = entry_path_from_id(entry_id, config)
            if path:
                entries.append(load_entry(path))

    entries = entries[:limit]

    if not entries:
        console.print(f'  [dim]No entries found for "{query_text}".[/dim]')
        return

    from bute.display import display_entry_list
    display_entry_list(entries, f'Find: "{query_text}"')
    save_state("find", [e.id for e in entries], config)


@click.command("rebuild")
@click.pass_context
def rebuild_cmd(ctx):
    """Rebuild the search index from Markdown files."""
    from bute.ai import is_embedding_available
    from bute.db import rebuild_from_files

    config = ctx.obj.get("config")
    include_vectors = is_embedding_available()

    console.print("  [dim]Your entries are safe — all data lives in your .md files.[/dim]")
    console.print("  [dim]Rebuilding search index...[/dim]")

    count = rebuild_from_files(config, include_vectors=include_vectors)

    if count == 0:
        console.print("  [dim]No entries found to index.[/dim]")
    else:
        vec_msg = f", {count} vectors embedded" if include_vectors else " (vectors skipped — embeddings not installed)"
        console.print(f"  [green]Rebuilt index: {count} entries indexed{vec_msg}.[/green]")
        console.print("  [dim]Your .md files are untouched — they're always the source of truth.[/dim]")
