"""Trash commands — bt trash (list), bt trash purge (delete them all for good)."""

import click
from rich.console import Console

from bute.display import display_entry_list, emit_json, json_mode
from bute.state import save_state
from bute.storage import list_trash, trash_dir

console = Console()


@click.command("trash")
@click.argument("subcommand", required=False, default=None)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation for 'purge'.")
@click.pass_context
def trash_cmd(ctx, subcommand, yes):
    """Show trashed entries. 'bt trash purge' deletes them permanently."""
    config = ctx.obj.get("config")

    # `purge` names both forms — `bt trash purge` (all) and `bt <n> purge` (some)
    if subcommand == "empty":
        raise click.UsageError("'bt trash empty' is now 'bt trash purge' (one item: bt trash → bt <n> purge).")

    if subcommand == "purge":
        paths = list(trash_dir(config).glob("*.md")) if trash_dir(config).exists() else []
        if not paths:
            console.print("  [dim]Trash is empty.[/dim]")
            return
        if not yes and not click.confirm(f"  Permanently delete {len(paths)} trashed entries?", default=False):
            console.print("  [dim]Cancelled.[/dim]")
            return
        for p in paths:
            p.unlink()
        console.print(f"  [green]Purged trash ({len(paths)} entries).[/green]")
        return

    if subcommand is not None:
        raise click.UsageError(f"Unknown trash subcommand: {subcommand}. Use 'bt trash' or 'bt trash purge'.")

    entries = list_trash(config)
    if not entries:
        # Leave the previous view's number mapping intact — `bt trash` on an
        # empty trash must not break a pending `bt <n> done`.
        if json_mode():
            emit_json("Trash", [])
        else:
            console.print("  [dim]Trash is empty.[/dim]")
        return

    display_entry_list(entries, "Trash")
    save_state("trash", [e.id for e in entries], config)
