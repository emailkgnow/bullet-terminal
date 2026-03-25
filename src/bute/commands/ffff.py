"""FFFF pipeline commands — Find, Form, Focus, Finish."""

import click
from rich.console import Console

from bute.collection_storage import (
    append_to_collection,
    load_collection,
    save_collection,
)

console = Console()

_LLM_MSG = (
    "  [yellow]This FFFF stage requires AI.[/yellow]\n"
    "  Install: [bold]uv pip install 'bute\\[ai]'[/bold]"
)


@click.command("find")
@click.argument("collection")
@click.argument("items", nargs=-1)
@click.pass_context
def find_cmd(ctx, collection, items):
    """Gather raw material into a collection."""
    config = ctx.obj.get("config")

    if items:
        # Non-interactive: add items from args
        append_to_collection(collection, list(items), config)
        console.print(f"  [green]{len(items)} items added to '{collection}'[/green]")
    else:
        # Interactive: capture until blank line
        console.print(f"  [dim]Adding to '{collection}' (blank line to finish):[/dim]")
        new_items = []
        while True:
            try:
                line = click.prompt("", prompt_suffix="  > ", default="", show_default=False)
            except (EOFError, click.Abort):
                break
            if not line.strip():
                break
            new_items.append(line.strip())

        if new_items:
            append_to_collection(collection, new_items, config)
            console.print(f"  [green]{len(new_items)} items added to '{collection}'[/green]")
        else:
            console.print("  [dim]No items added.[/dim]")


@click.command("form")
@click.argument("collection")
@click.pass_context
def form_cmd(ctx, collection):
    """AI categorizes raw collection items (FFFF stage 2)."""
    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send

    config = ctx.obj.get("config")

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    coll = load_collection(collection, config)
    if coll is None:
        console.print(f"  [red]Collection '{collection}' not found.[/red]")
        return

    if coll["stage"] not in ("raw",):
        console.print(f"  [yellow]Collection is at stage '{coll['stage']}', expected 'raw'.[/yellow]")
        return

    from bute.ai.prompts import form_prompt

    items_text = "\n".join(f"- {item}" for item in coll["items"])
    console.print(f"  [dim]Categorizing {len(coll['items'])} items...[/dim]")

    response = llm_send(form_prompt(), f"Items to categorize:\n{items_text}", config)
    console.print(f"\n{response}")

    if click.confirm("\n  Accept these categories?", default=True):
        save_collection(collection, "formed", response, config)
        console.print(f"  [green]Collection '{collection}' → formed[/green]")


@click.command("focus")
@click.argument("collection")
@click.pass_context
def focus_cmd(ctx, collection):
    """AI identifies the vital 20% (FFFF stage 3)."""
    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send

    config = ctx.obj.get("config")

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    coll = load_collection(collection, config)
    if coll is None:
        console.print(f"  [red]Collection '{collection}' not found.[/red]")
        return

    if coll["stage"] not in ("formed",):
        console.print(f"  [yellow]Collection is at stage '{coll['stage']}', expected 'formed'.[/yellow]")
        return

    from bute.ai.prompts import focus_prompt

    console.print(f"  [dim]Focusing...[/dim]")
    response = llm_send(focus_prompt(), f"Categorized items:\n{coll['raw_content']}", config)
    console.print(f"\n{response}")

    if click.confirm("\n  Accept this focus?", default=True):
        save_collection(collection, "focused", response, config)
        console.print(f"  [green]Collection '{collection}' → focused[/green]")


@click.command("finish")
@click.argument("collection")
@click.pass_context
def finish_cmd(ctx, collection):
    """AI generates tasks from focused items (FFFF stage 4)."""
    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send

    config = ctx.obj.get("config")

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    coll = load_collection(collection, config)
    if coll is None:
        console.print(f"  [red]Collection '{collection}' not found.[/red]")
        return

    if coll["stage"] not in ("focused",):
        console.print(f"  [yellow]Collection is at stage '{coll['stage']}', expected 'focused'.[/yellow]")
        return

    from bute.ai.prompts import finish_prompt

    console.print(f"  [dim]Generating tasks...[/dim]")
    response = llm_send(finish_prompt(), f"Focused items:\n{coll['raw_content']}", config)
    console.print(f"\n{response}")

    if click.confirm("\n  Create these tasks?", default=True):
        # Parse tasks from response (lines starting with -)
        tasks = [
            line.lstrip("- ").strip()
            for line in response.split("\n")
            if line.strip().startswith("-")
        ]

        from bute.display import confirm_capture
        from bute.models import Entry, EntryType
        from bute.storage import save_entry

        safe_tag = collection.lower().replace(" ", "-")
        for task_text in tasks:
            entry = Entry.create(
                entry_type=EntryType.TASK,
                body=task_text,
                tags=[safe_tag],
            )
            save_entry(entry, config)
            from bute.ai import embed_entry

            embed_entry(entry.id, entry.body, config)
            confirm_capture(entry)

        save_collection(collection, "finished", response, config)
        console.print(f"  [green]{len(tasks)} tasks created from '{collection}'[/green]")
