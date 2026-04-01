"""Collection commands — view, analyze, execute, list."""

import re

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
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
        body.append("  \u25b8 INPUT", style="bold")
        body.append(f" \u2014 {coll['item_count']} entries\n", style="dim")
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
        body.append("  \u25b8 ANALYSIS\n", style="bold")
        for line in coll["analysis_content"].strip().split("\n"):
            body.append(f"    {line}\n")

    # Tasks section
    if coll["tasks_content"]:
        body.append("\n")
        body.append("  \u25b8 TASKS\n", style="bold")
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
