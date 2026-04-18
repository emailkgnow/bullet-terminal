"""Init command — first-run setup for bt."""

import click
from rich.console import Console

from bute.config import (
    default_config,
    ensure_data_dirs,
    get_config_path,
    save_config,
)

console = Console()


@click.command("init")
@click.pass_context
def init_cmd(ctx):
    """Initialize bt — create config and data directories."""
    config_path = get_config_path()

    if config_path.exists():
        if not click.confirm("Config already exists. Reinitialize?", default=False):
            return

    doc = default_config()
    save_config(doc)
    data_dir = ensure_data_dirs(doc)
    console.print(f"\n  [green]Config saved to {config_path}[/green]")
    console.print(f"  [green]Data directory at {data_dir}[/green]")
    console.print("  [dim]Run[/dim] [bold]bt start[/bold] [dim]for a quick tour.[/dim]")
