"""Start command — onboarding and the bt way."""

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


@click.command("start")
@click.pass_context
def start_cmd(ctx):
    """Quick start guide — the bt way."""
    console.print()

    # Header
    title = Text()
    title.append(" bt ", style="bold")
    title.append("(BuTe)", style="dim")
    title.append(" — the bt way ", style="bold")

    intro = Text.from_markup(
        "[bold]One rule:[/bold] start your day with [bold cyan]bt dp[/bold cyan]\n"
        "\n"
        "Daily plan walks you through four phases every morning:\n"
        "\n"
        "  [bold cyan]D[/bold cyan] · Dump      Get everything out of your head\n"
        "  [bold cyan]Y[/bold cyan] · Yesterday  Deal with what you didn't finish\n"
        "  [bold cyan]T[/bold cyan] · Tasks      Pick 2-3 things to focus on today\n"
        "  [bold cyan]S[/bold cyan] · Schedule   See what's on the calendar\n"
        "\n"
        "That's it. The system guides you from there."
    )
    console.print(Panel(intro, title=title, border_style="cyan", padding=(1, 2)))

    # Capture
    console.print()
    console.print("  [bold]Capture[/bold] — throughout the day, get things in fast:")
    console.print()
    console.print("    [cyan]bt t[/cyan]  call dentist             [dim]task[/dim]")
    console.print("    [yellow]bt n[/yellow]  OAuth tokens expire 30d   [dim]note[/dim]")
    console.print("    [magenta]bt j[/magenta]  rough morning              [dim]journal[/dim]")
    console.print("    [green]bt c[/green]  standup time:10am          [dim]event[/dim]")
    console.print()
    console.print("    [dim]Tip: type just the signifier (bt j) to enter text[/dim]")
    console.print("    [dim]interactively — no shell quoting needed.[/dim]")

    # Act
    console.print()
    console.print("  [bold]Act[/bold] — use [bold]bt[/bold] to see today's log, then act by number:")
    console.print()
    console.print("    [bold]bt 1 done[/bold]       mark complete")
    console.print("    [bold]bt 2 drop[/bold]       consciously delete")
    console.print("    [bold]bt 3 ![/bold]          toggle important")
    console.print("    [bold]bt 1 @api[/bold]       add a tag")

    # The rhythm
    console.print()
    console.print(Panel(
        Text.from_markup(
            "  [bold cyan]morning[/bold cyan]   bt dp            [dim]— daily plan[/dim]\n"
            "  [bold]all day[/bold]   bt t / n / j / c  [dim]— capture fast[/dim]\n"
            "  [bold cyan]evening[/bold cyan]   bt               [dim]— check your day[/dim]\n"
            "  [bold cyan]weekly[/bold cyan]    bt wp            [dim]— weekly plan[/dim]"
        ),
        title=Text(" the rhythm ", style="bold"),
        border_style="dim",
        padding=(1, 2),
    ))

    console.print()
    console.print("  [dim]Run[/dim] [bold cyan]bt dp[/bold cyan] [dim]to begin.[/dim]")
    console.print()
