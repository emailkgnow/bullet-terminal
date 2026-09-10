"""Demo mode — isolated interactive session for presentations."""

import shutil

import click
from rich.console import Console

from bute.config import DEMO_DATA_DIR

console = Console()


@click.command("demo")
@click.pass_context
def demo_cmd(ctx):
    """Demo mode — isolated interactive session with auto-cleanup."""
    config = ctx.obj.get("config")

    # Close any existing DB connection before switching
    try:
        from bute.db import close
        close()
    except Exception:
        pass

    # Wipe any leftover demo data from a previous crash
    if DEMO_DATA_DIR.exists():
        shutil.rmtree(DEMO_DATA_DIR)

    # Set up fresh demo data directory
    from bute.config import _make_demo_config, ensure_data_dirs
    config = _make_demo_config(config)
    ensure_data_dirs(config)
    ctx.obj["config"] = config

    console.print("\n  [bold green]Demo session started[/bold green]")
    console.print("  [dim]Using isolated data — your real data is untouched.[/dim]\n")

    # Show new-user experience: clear any stale tour marker and run the tour.
    from bute.config import TOUR_DONE
    if TOUR_DONE.exists():
        TOUR_DONE.unlink()
    from bute.commands.tour import run_tour
    run_tour(ctx)

    # Run interactive REPL in demo context
    from bute.cli import _run_interactive
    _run_interactive(ctx)

    # Clean up on exit
    _cleanup_demo()


def _cleanup_demo():
    """Remove demo data, tour markers, and close connections."""
    try:
        from bute.db import close
        close()
    except Exception:
        pass

    if DEMO_DATA_DIR.exists():
        shutil.rmtree(DEMO_DATA_DIR)

    # Clean up tour marker so demo doesn't affect real first-run experience
    from bute.config import TOUR_DONE
    if TOUR_DONE.exists():
        TOUR_DONE.unlink()

    console.print("\n  [bold green]Demo session ended[/bold green]")
    console.print("  [dim]Demo data deleted. Back to your real data.[/dim]\n")
