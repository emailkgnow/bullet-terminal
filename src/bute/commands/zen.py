"""Zen command — the philosophy of bt in three lines."""

import click
from rich.console import Console

console = Console()


@click.command("this")
def this_cmd():
    """The Zen of Bullet-Terminal."""
    console.print()
    console.print("  [bold]The Zen of Bullet-Terminal[/bold]")
    console.print()
    console.print("  [dim]1.[/dim] If you're typing more than [cyan]bt t buy milk[/cyan], the grammar failed.")
    console.print("  [dim]2.[/dim] Local is a feature, not a limitation.")
    console.print("  [dim]3.[/dim] Bring your own AI.")
    console.print()
