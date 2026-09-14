"""Trash commands — bt trash (list), bt trash empty (purge)."""

import click
from rich.console import Console

from bute.display import display_entry_list
from bute.state import save_state
from bute.storage import list_trash, trash_dir

console = Console()


@click.command("trash")
@click.argument("subcommand", required=False, default=None)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation for 'empty'.")
@click.pass_context
def trash_cmd(ctx, subcommand, yes):
    """Show trashed entries. 'bt trash empty' deletes them permanently."""
    config = ctx.obj.get("config")

    if subcommand == "empty":
        paths = list(trash_dir(config).glob("*.md")) if trash_dir(config).exists() else []
        if not paths:
            console.print("  [dim]Trash is empty.[/dim]")
            return
        if not yes and not click.confirm(f"  Permanently delete {len(paths)} trashed entries?", default=False):
            console.print("  [dim]Cancelled.[/dim]")
            return
        for p in paths:
            p.unlink()
        console.print(f"  [green]Emptied trash ({len(paths)} entries).[/green]")
        return

    if subcommand is not None:
        raise click.UsageError(f"Unknown trash subcommand: {subcommand}. Use 'bt trash' or 'bt trash empty'.")

    entries = list_trash(config)
    if not entries:
        console.print("  [dim]Trash is empty.[/dim]")
        save_state("trash", [], config)
        return

    display_entry_list(entries, "Trash")
    save_state("trash", [e.id for e in entries], config)
