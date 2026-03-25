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


@click.command("rebuild")
@click.pass_context
def rebuild_cmd(ctx):
    """Re-embed all entries. Rebuilds the vector database from Markdown files."""
    from bute.ai import is_embedding_available

    if not is_embedding_available():
        console.print(_INSTALL_MSG)
        return

    config = ctx.obj.get("config")

    from bute.ai.embeddings import embed_texts
    from bute.ai.vectors import clear, upsert
    from bute.config import get_data_dir
    from bute.storage import load_entry

    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"

    if not entries_dir.exists():
        console.print("  [dim]No entries to embed.[/dim]")
        return

    md_files = sorted(entries_dir.rglob("*.md"))
    if not md_files:
        console.print("  [dim]No entries found.[/dim]")
        return

    console.print(f"  [dim]Found {len(md_files)} entries. Embedding...[/dim]")

    entries = []
    for path in md_files:
        try:
            entries.append(load_entry(path))
        except Exception:
            console.print(f"  [yellow]Skipped {path.name} (parse error)[/yellow]")

    texts = [e.body for e in entries]
    vectors = embed_texts(texts)

    clear(config)
    for entry, vector in zip(entries, vectors):
        upsert(entry.id, vector, config)

    console.print(f"  [green]Embedded {len(entries)} entries.[/green]")
