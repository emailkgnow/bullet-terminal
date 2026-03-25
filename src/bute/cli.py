"""CLI entry point and custom command routing for bute."""

import re
import sys

import click

from bute import __version__

# Short signifier pattern: t, /t, t!, /t!, n, j, c, etc.
SIGNIFIER_PATTERN = re.compile(r"^/?[tnjc]!?$")
# Bullet signifier pattern: . = - o (with optional !)
BULLET_PATTERN = re.compile(r"^[.=\-o]!?$")
# Full word capture: task, note, journal, cal (with optional !)
WORD_SIGNIFIER_PATTERN = re.compile(r"^(task|note|journal|cal)!?$")

# Short letter to view command mapping (when no text follows)
SHORT_TO_VIEW = {"t": "tasks", "n": "notes", "j": "journals", "c": "calendar", "l": "linelog"}
BULLET_TO_VIEW = {".": "tasks", "=": "journals", "-": "notes", "o": "calendar"}
WORD_TO_VIEW = {"task": "tasks", "note": "notes", "journal": "journals", "cal": "calendar"}


class DwnGroup(click.Group):
    """Custom group that dispatches signifiers and number-actions."""

    def format_help(self, ctx, formatter):
        """Override default help to show our custom Rich help."""
        _print_help()

    def resolve_command(self, ctx, args):
        if not args:
            return super().resolve_command(ctx, args)

        first = args[0]
        rest = args[1:]

        # 1. Named command — delegate to normal Click routing
        cmd = self.get_command(ctx, first)
        if cmd is not None:
            return cmd.name, cmd, rest

        # 2. Single letter shortcut: l = linelog
        if first == "l":
            cmd = self.get_command(ctx, "linelog")
            if cmd is not None:
                return "linelog", cmd, rest

        # 3. Signifier (short: t, /t | bullet: . = - o | word: task, note, journal, cal)
        is_short = SIGNIFIER_PATTERN.match(first)
        is_bullet = BULLET_PATTERN.match(first)
        is_word = WORD_SIGNIFIER_PATTERN.match(first)

        if is_short or is_bullet or is_word:
            # Text follows → capture
            has_text = rest and not (len(rest) == 1 and rest[0].startswith("@"))
            if has_text:
                cmd = self.get_command(ctx, "capture")
                if cmd is not None:
                    return "capture", cmd, args

            # No text (or only @tag) → view
            stripped = first.rstrip("!").lstrip("/")
            if is_word:
                view_name = WORD_TO_VIEW.get(stripped)
            elif is_bullet:
                view_name = BULLET_TO_VIEW.get(stripped)
            else:
                view_name = SHORT_TO_VIEW.get(stripped)

            if view_name:
                cmd = self.get_command(ctx, view_name)
                if cmd is not None:
                    # Pass @tag as argument if present
                    tag_args = [rest[0][1:]] if rest and rest[0].startswith("@") else []
                    return view_name, cmd, tag_args

        # 4. Tag filter — @tagname
        if first.startswith("@") and len(first) > 1:
            cmd = self.get_command(ctx, "tag_filter")
            if cmd is not None:
                return "tag_filter", cmd, [first[1:]]

        # 5. Number-action — first token is a digit
        if first.isdigit():
            cmd = self.get_command(ctx, "action")
            if cmd is not None:
                return "action", cmd, args

        # 6. Unknown — let Click produce the error
        return super().resolve_command(ctx, args)


def _print_help():
    """Print the full bute help using Rich."""
    from rich.console import Console
    from rich.text import Text

    console = Console()
    console.print()
    console.print("  [bold]bute[/bold] (دوّن) — AI-powered life management CLI")
    console.print()

    # Capture
    console.print("  [bold cyan]Capture[/bold cyan] — type what's on your mind")
    console.print("    [cyan]bute t[/cyan] <text>      Task            [dim]bute t call dentist due:friday[/dim]")
    console.print("    [yellow]bute n[/yellow] <text>      Note / idea     [dim]bute n OAuth2 tokens expire in 30 days[/dim]")
    console.print("    [magenta]bute j[/magenta] <text>      Journal         [dim]bute j rough morning, couldn't focus[/dim]")
    console.print("    [green]bute c[/green] <text>      Calendar event  [dim]bute c standup t:0900[/dim]")
    console.print("    Full words work too: [dim]bute task, bute note, bute journal, bute cal[/dim]")
    console.print("    BuJo bullets work too: [dim]bute . (task)  bute - (note)  bute = (journal)  bute o (event)[/dim]")
    console.print("    Add [bold red]![/bold red] for important: [dim]bute t! fix prod bug[/dim]")
    console.print("    Add [bold]@tag[/bold] and [bold]key:value[/bold]: [dim]bute t fix bug @backend due:tomorrow[/dim]")
    console.print("    Calendar keys: [dim]t:HHMM (time)  d:MMDD (date)  — bute c meeting t:1430 d:0330[/dim]")
    console.print("    Just the signifier, no text: [dim]bute t → interactive prompt (no shell quoting)[/dim]")
    console.print()

    # Views
    console.print("  [bold cyan]Views[/bold cyan] — same letters, no text = view")
    console.print("    [bold]bute ls[/bold]              Today's log")
    console.print("    [bold]bute t[/bold] [@tag]        Active tasks (--all for done/dropped)")
    console.print("    [bold]bute n[/bold] [@tag]        All notes")
    console.print("    [bold]bute j[/bold] [@tag]        All journal entries")
    console.print("    [bold]bute c[/bold] [@tag]        All events")
    console.print("    [bold]bute l[/bold]               Line log (monthly overview)")
    console.print("    [bold]bute active[/bold]          This week's selected tasks")
    console.print("    [bold]bute @tagname[/bold]        Filter by tag across all dimensions")
    console.print("    [bold]bute search[/bold] <query>  Semantic search")
    console.print("    [bold]bute similar[/bold] <n>     Entries similar to #n")
    console.print()

    # Actions
    console.print("  [bold cyan]Actions[/bold cyan] — act on numbered entries from last view")
    console.print("    [bold]bute <n> done[/bold]              Mark task(s) complete")
    console.print("    [bold]bute <n> drop[/bold]              Consciously delete")
    console.print("    [bold]bute <n> delete[/bold]            Permanently remove from disk")
    console.print("    [bold]bute <n> ![/bold]                 Toggle important flag")
    console.print("    [bold]bute <n> @tag[/bold]              Add a tag")
    console.print("    [dim]Multiple entries:[/dim] [bold]bute 1 2 3 done[/bold]")
    console.print()

    # Rituals
    console.print("  [bold cyan]Rituals[/bold cyan] — guided BuJo workflows")
    console.print("    [bold]bute dyts[/bold]            Morning ritual (Dump, Yesterday, Tasks, Schedule)")
    console.print("    [bold]bute plan[/bold]            Weekly ritual (select tasks for the week)")
    console.print("    [bold]bute habit[/bold] [name]    Track habits (done by default, --no for not done)")
    console.print()

    # AI
    console.print("  [bold cyan]AI Features[/bold cyan] — requires configured provider (bute init)")
    console.print("    [bold]bute review[/bold] [period]   AI summary (day/week/month)")
    console.print("    [bold]bute topic[/bold] <name>      Cross-dimension synthesis")
    console.print("    [bold]bute nudges[/bold]            AI-generated actionable suggestions")
    console.print()

    # FFFF
    console.print("  [bold cyan]FFFF Pipeline[/bold cyan] — ideas to action")
    console.print("    [bold]bute find[/bold] <collection>    Gather raw material")
    console.print("    [bold]bute form[/bold] <collection>    AI categorizes → user confirms")
    console.print("    [bold]bute focus[/bold] <collection>   AI cuts to 20% → user confirms")
    console.print("    [bold]bute finish[/bold] <collection>  AI generates tasks → user confirms")
    console.print()

    # System
    console.print("  [bold cyan]System[/bold cyan]")
    console.print("    [bold]bute start[/bold]           Quick start guide — the bute way")
    console.print("    [bold]bute init[/bold]            First-run setup (pick AI provider)")
    console.print("    [bold]bute rebuild[/bold]         Re-embed all entries for semantic search")
    console.print("    [bold]bute --version[/bold]       Show version")
    console.print()


@click.group(cls=DwnGroup, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="bute")
@click.pass_context
def main(ctx):
    """bute (BuTe) — AI-powered life management CLI based on Bullet Journal."""
    ctx.ensure_object(dict)
    from bute.config import load_config

    ctx.obj["config"] = load_config()

    if not ctx.invoked_subcommand:
        from bute.state import is_dyts_done_today

        config = ctx.obj["config"]
        if is_dyts_done_today(config):
            # DYTS already done — show daily log (focus view)
            from datetime import date
            from bute.display import display_entry_list
            from bute.ritual_ops import get_daily_log
            from bute.state import save_state

            entries = get_daily_log(config)
            display_entry_list(entries, f"Today — {date.today().strftime('%a %b %d')}")
            save_state("ls", [e.id for e in entries], config)

            from rich.console import Console
            console = Console()
            console.print(f"\n  [dim]DYTS done. Run[/dim] [bold]bute dyts[/bold] [dim]to redo.[/dim]")
        else:
            ctx.invoke(dyts_cmd)


# --- Register commands ---

from bute.commands.capture import capture_cmd  # noqa: E402
from bute.commands.action import action_cmd  # noqa: E402
from bute.commands.init_cmd import init_cmd  # noqa: E402
from bute.commands.views import (  # noqa: E402
    active_cmd,
    calendar_cmd,
    journals_cmd,
    ls_cmd,
    notes_cmd,
    tag_filter_cmd,
    tasks_cmd,
)
from bute.commands.rituals import (  # noqa: E402
    dyts_cmd,
    habit_cmd,
    linelog_cmd,
    plan_cmd,
    review_cmd,
)
from bute.commands.search import rebuild_cmd, search_cmd, similar_cmd  # noqa: E402
from bute.commands.topic import topic_cmd  # noqa: E402
from bute.commands.nudges import nudges_cmd  # noqa: E402
from bute.commands.ffff import find_cmd, form_cmd, focus_cmd, finish_cmd  # noqa: E402
from bute.commands.start import start_cmd  # noqa: E402

main.add_command(init_cmd)
main.add_command(start_cmd)
main.add_command(capture_cmd)
main.add_command(action_cmd)
main.add_command(ls_cmd)
main.add_command(tasks_cmd)
main.add_command(notes_cmd)
main.add_command(journals_cmd)
main.add_command(calendar_cmd)
main.add_command(active_cmd)
main.add_command(tag_filter_cmd)
main.add_command(dyts_cmd)
main.add_command(habit_cmd)
main.add_command(linelog_cmd)
main.add_command(plan_cmd)
main.add_command(review_cmd)
main.add_command(search_cmd)
main.add_command(similar_cmd)
main.add_command(rebuild_cmd)
main.add_command(topic_cmd)
main.add_command(nudges_cmd)
main.add_command(find_cmd)
main.add_command(form_cmd)
main.add_command(focus_cmd)
main.add_command(finish_cmd)
