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
    title.append("(bullet-terminal)", style="dim")
    title.append(" — quick start ", style="bold")

    intro = Text.from_markup(
        "[bold]One rule:[/bold] start your day with [bold cyan]bt dp[/bold cyan]\n"
        "\n"
        "Daily plan walks you through planning your day:\n"
        "dump what's on your mind, review yesterday's unfinished\n"
        "items, pick tasks to focus on, and check your schedule.\n"
        "\n"
        "That's it. The system guides you from there."
    )
    console.print(Panel(intro, title=title, border_style="cyan", padding=(1, 2)))

    # Capture
    console.print()
    console.print("  [bold]Capture[/bold] — throughout the day, get things in fast:")
    console.print()
    console.print("    [cyan]bt t[/cyan]  call dentist              [dim]task[/dim]")
    console.print("    [yellow]bt n[/yellow]  OAuth tokens expire 30d    [dim]note[/dim]")
    console.print("    [magenta]bt j[/magenta]  rough morning               [dim]journal[/dim]")
    console.print("    [green]bt c[/green]  standup t:9                 [dim]calendar event at 9 AM[/dim]")
    console.print()

    # Metadata
    console.print("  [bold]Metadata[/bold] — add dates, times, deadlines, and tags inline:")
    console.print()
    console.print("    [bold]d:[/bold]   date       [dim]d:4.7  d:tomorrow  d:friday  d:mar15[/dim]")
    console.print("    [bold]t:[/bold]   time       [dim]t:9  t:14.30[/dim]  [dim](24h format)[/dim]")
    console.print("    [bold]due:[/bold] deadline   [dim]due:friday  due:4.15[/dim]")
    console.print("    [bold]@[/bold]    tag        [dim]@backend  @home  @thisweek[/dim]")
    console.print("    [bold red]![/bold red]    important  [dim]bt t! fix prod bug[/dim]")
    console.print()
    console.print("    [dim]Example: bt t fix auth bug due:friday @backend[/dim]")
    console.print("    [dim]Tip: type just the signifier (bt j) to enter text interactively.[/dim]")

    # Views
    console.print()
    console.print("  [bold]View[/bold] — same letters, no text = view:")
    console.print()
    console.print("    [bold]bt[/bold]              [dim]Focus Log (or daily plan if not done)[/dim]")
    console.print("    [bold]bt -a[/bold]           [dim]Focus Log + dropped/non-focus captures[/dim]")
    console.print("    [bold]bt t[/bold]             [dim]this week's tasks[/dim]")
    console.print("    [bold]bt b[/bold]             [dim]full task backlog[/dim]")
    console.print("    [bold]bt n / j / c[/bold]     [dim]notes / journals / calendar[/dim]")
    console.print("    [bold]bt due[/bold]           [dim]tasks by deadline[/dim]")
    console.print("    [bold]bt goals[/bold]         [dim]goals with task progress[/dim]")
    console.print("    [bold]bt @tag[/bold]          [dim]filter by tag[/dim]  [dim](bt @backend -@done)[/dim]")

    # Act
    console.print()
    console.print("  [bold]Act[/bold] — use [bold]bt[/bold] to see your Focus Log, then act by number:")
    console.print()
    console.print("    [bold]bt 1 done[/bold]        [dim]mark complete[/dim]")
    console.print("    [bold]bt 2 3 drop[/bold]      [dim]consciously delete[/dim]")
    console.print("    [bold]bt 5 ![/bold]           [dim]toggle important[/dim]")
    console.print("    [bold]bt 1 @api[/bold]        [dim]add a tag[/dim]")
    console.print("    [bold]bt 3 later[/bold]       [dim]defer to another day[/dim]")
    console.print("    [bold]bt 1[/bold]             [dim]open in editor[/dim]")

    # Tags
    console.print()
    console.print("  [bold]Tags[/bold] — organize, filter, and think with @tags:")
    console.print()
    console.print("    [bold]bt tags[/bold]           [dim]all tags with counts[/dim]")
    console.print("    [bold]bt @home[/bold]          [dim]view entries tagged @home[/dim]")
    console.print("    [dim]Goals are notes tagged @goal — bt goals shows progress.[/dim]")

    # Search
    console.print()
    console.print("  [bold]Search[/bold] — local, no API keys:")
    console.print()
    console.print("    [bold]bt find <keyword>[/bold]  [dim]keyword search (FTS5)[/dim]")
    console.print("    [bold]bt like <q>[/bold]        [dim]semantic search (local embeddings)[/dim]")

    # Bring Your Own AI
    console.print()
    console.print("  [bold]Bring your own AI[/bold] — no built-in LLM:")
    console.print()
    console.print("    [dim]Point any agent (Claude Desktop + filesystem MCP, Claude Code,[/dim]")
    console.print("    [dim]scripts) at[/dim] [bold]~/bullet-terminal/entries/[/bold][dim]. Write valid .md + YAML[/dim]")
    console.print("    [dim]frontmatter; bt reconciles them on next read. Schema: README.md.[/dim]")

    # Habits
    console.print()
    console.print("  [bold]Habits[/bold] — track daily habits:")
    console.print()
    console.print("    [bold]bt h[/bold]              [dim]today's habit checklist[/dim]")
    console.print("    [bold]bt streak[/bold]         [dim]streaks and 30-day stats[/dim]")

    # The rhythm
    console.print()
    console.print(Panel(
        Text.from_markup(
            "  [bold cyan]morning[/bold cyan]   bt dp            [dim]— daily plan[/dim]\n"
            "  [bold]all day[/bold]   bt t / n / j / c  [dim]— capture fast[/dim]\n"
            "  [bold cyan]evening[/bold cyan]   bt               [dim]— Focus Log[/dim]\n"
            "  [bold cyan]weekly[/bold cyan]    bt wp            [dim]— weekly plan[/dim]"
        ),
        title=Text(" the rhythm ", style="bold"),
        border_style="dim",
        padding=(1, 2),
    ))

    console.print()
    console.print("  [dim]Run[/dim] [bold cyan]bt dp[/bold cyan] [dim]to begin.[/dim]")
    console.print()
