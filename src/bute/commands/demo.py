"""Demo mode — toggle isolated demo environment for presentations."""

import shutil

import click
from rich.console import Console

from bute.config import DEMO_DATA_DIR, DEMO_MARKER, is_demo_active

console = Console()


@click.command("demo")
@click.pass_context
def demo_cmd(ctx):
    """Toggle demo mode — isolated data for presentations."""
    if is_demo_active():
        _end_demo()
    else:
        _start_demo(ctx.obj.get("config"))


def _start_demo(config):
    """Enter demo mode: create marker, fresh data directory."""
    # Wipe any leftover demo data
    if DEMO_DATA_DIR.exists():
        shutil.rmtree(DEMO_DATA_DIR)

    # Close any existing DB connection before switching
    try:
        from bute.db import close
        close()
    except Exception:
        pass

    # Create marker
    DEMO_MARKER.parent.mkdir(parents=True, exist_ok=True)
    DEMO_MARKER.touch()

    # Set up fresh data dirs using demo path
    from bute.config import apply_demo_config, ensure_data_dirs
    config = apply_demo_config(config)
    ensure_data_dirs(config)

    console.print("\n  [bold green]Demo mode ON[/bold green]")
    console.print("  [dim]Using isolated data at ~/bute-demo/[/dim]")
    console.print("  [dim]Your real data is untouched. Run bt -d again to exit.[/dim]\n")


def _end_demo():
    """Exit demo mode: remove marker, delete demo data."""
    # Close DB connection to demo data
    try:
        from bute.db import close
        close()
    except Exception:
        pass

    # Remove demo data
    if DEMO_DATA_DIR.exists():
        shutil.rmtree(DEMO_DATA_DIR)

    # Remove marker
    if DEMO_MARKER.exists():
        DEMO_MARKER.unlink()

    console.print("\n  [bold green]Demo mode OFF[/bold green]")
    console.print("  [dim]Demo data deleted. Back to your real data.[/dim]\n")
