"""First-run onboarding — welcome → wp → dp → done."""

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

import bute.config as _config

_console = Console()


def is_tour_done() -> bool:
    return _config.TOUR_DONE.exists()


def mark_tour_done() -> None:
    _config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _config.TOUR_DONE.touch()


def _has_entries(config) -> bool:
    from bute.config import get_data_dir
    data_dir = get_data_dir(config)
    entries_dir = data_dir / "entries"
    if not entries_dir.exists():
        return False
    return any(entries_dir.rglob("*.md"))


def should_run_tour(config) -> bool:
    """Trigger first-run when no entries exist and no completion marker."""
    return not is_tour_done() and not _has_entries(config)


def _show_welcome() -> None:
    _console.print()
    welcome = Text.from_markup(
        "[bold]Welcome to bt.[/bold]\n"
        "\n"
        "A Bullet Journal in your terminal. Three steps to get you running:\n"
        "\n"
        "  [bold]1.[/bold] Dump what's on your mind — tasks, ideas, anything.\n"
        "      Don't try to be comprehensive. You can always add more later.\n"
        "  [bold]2.[/bold] Pick what matters this week.\n"
        "  [bold]3.[/bold] Pick what you'll do today.\n"
        "\n"
        "Then [bold cyan]bt[/bold cyan] shows your Focus Log."
    )
    _console.print(Panel(
        welcome,
        title=Text(" first run ", style="bold"),
        border_style="cyan",
        padding=(1, 2),
    ))


def _show_outro() -> None:
    _console.print()
    outro = Text.from_markup(
        "[bold]You're set.[/bold]\n"
        "\n"
        "  [bold cyan]bt[/bold cyan]        your Focus Log\n"
        "  [bold cyan]bt -h[/bold cyan]     full grammar — capture, view, act\n"
        "  [bold cyan]bt dp[/bold cyan]     start each day with this\n"
        "  [bold cyan]bt wp[/bold cyan]     start each week with this\n"
        "\n"
        "[dim]Capture: [bold]bt t call mom[/bold] · [bold]bt n idea[/bold] · "
        "[bold]bt c lunch t:12[/bold][/dim]"
    )
    _console.print(Panel(outro, border_style="green", padding=(1, 2)))
    _console.print()


def run_tour(ctx: click.Context) -> None:
    """First-run onboarding: welcome → wp → dp → outro."""
    from bute.config import ensure_data_dirs
    config = ctx.obj.get("config")
    ensure_data_dirs(config)

    # Pre-init DB so reconcile doesn't fire mid-tour (no .md files exist yet).
    from bute.db import get_connection
    get_connection(config)

    _show_welcome()

    from bute.commands.rituals import dp_cmd, wp_cmd
    try:
        ctx.invoke(wp_cmd, non_interactive=False)
        ctx.invoke(dp_cmd, non_interactive=False)
    except (click.Abort, EOFError, KeyboardInterrupt):
        mark_tour_done()
        _console.print()
        _console.print(
            "  [dim]Tour ended. Run [bold]bt[/bold] to see your Focus Log, "
            "[bold]bt -h[/bold] for help.[/dim]"
        )
        return

    mark_tour_done()
    _show_outro()
