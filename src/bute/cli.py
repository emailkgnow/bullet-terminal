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

        # 2. Single letter shortcuts
        if first == "l":
            cmd = self.get_command(ctx, "linelog")
            if cmd is not None:
                return "linelog", cmd, rest

        if first in ("h", "habit"):
            cmd = self.get_command(ctx, "habits")
            if cmd is not None:
                return "habits", cmd, rest

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
            try:
                from bute.state import load_state
                state = load_state()

                # Pure habits view — all numbers are habits
                if state.get("view") == "habits":
                    cmd = self.get_command(ctx, "habits")
                    if cmd is not None:
                        return "habits", cmd, args

                # Mixed view (ls) — check if number falls in habit range
                habits = state.get("habits", [])
                if habits:
                    entry_count = len(state.get("entries", []))
                    num = int(first)
                    if num > entry_count:
                        # Remap to habit-relative numbers for the habits command
                        remapped = []
                        for tok in args:
                            if tok.isdigit() and int(tok) > entry_count:
                                remapped.append(str(int(tok) - entry_count))
                            else:
                                remapped.append(tok)
                        cmd = self.get_command(ctx, "habits")
                        if cmd is not None:
                            return "habits", cmd, remapped
            except Exception:
                pass
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
    console.print("  [bold]bt[/bold] (Bullet-Terminal) — AI-powered life management CLI")
    console.print()

    # Capture
    console.print("  [bold cyan]Capture[/bold cyan] — type what's on your mind")
    console.print("    [cyan]bt t[/cyan] <text>      Task            [dim]bt t call dentist due:friday[/dim]")
    console.print("    [cyan]bt t -l[/cyan] <text>   Backlog task     [dim]bt t -l research flights (not in focus)[/dim]")
    console.print("    [yellow]bt n[/yellow] <text>      Note / idea     [dim]bt n OAuth2 tokens expire in 30 days[/dim]")
    console.print("    [magenta]bt j[/magenta] <text>      Journal         [dim]bt j rough morning, couldn't focus[/dim]")
    console.print("    [green]bt c[/green] <text>      Calendar event  [dim]bt c standup t:0900[/dim]")
    console.print("    Full words work too: [dim]bt task, bt note, bt journal, bt cal[/dim]")
    console.print("    BuJo bullets work too: [dim]bt . (task)  bt - (note)  bt = (journal)  bt o (event)[/dim]")
    console.print("    Add [bold red]![/bold red] for important: [dim]bt t! fix prod bug[/dim]")
    console.print("    Add [bold]@tag[/bold] and [bold]key:value[/bold]: [dim]bt t fix bug @backend due:tomorrow[/dim]")
    console.print("    Calendar keys: [dim]t:HHMM (time)  d:MMDD (date)  — bt c meeting t:1430 d:0330[/dim]")
    console.print("    Just the signifier, no text: [dim]bt t → interactive prompt (no shell quoting)[/dim]")
    console.print("    [dim]Tasks auto-get @thisweek (focus). Use -l/--later for backlog only.[/dim]")
    console.print()

    # Views
    console.print("  [bold cyan]Views[/bold cyan] — same letters, no text = view")
    console.print("    [bold]bt[/bold]                 Daily plan if not done today, else today's log")
    console.print("    [bold]bt ls[/bold]              Today's log (always)")
    console.print("    [bold]bt t[/bold] [@tag]        Active tasks (--all for done/dropped)")
    console.print("    [bold]bt n[/bold] [@tag]        All notes")
    console.print("    [bold]bt j[/bold] [@tag]        All journal entries")
    console.print("    [bold]bt c[/bold] [@tag]        All events")
    console.print("    [bold]bt l[/bold]               Line log (monthly overview)")
    console.print("    [bold]bt active[/bold]          This week's selected tasks")
    console.print("    [bold]bt @tagname[/bold]        Filter by tag across all dimensions")
    console.print("    [bold]bt search[/bold] <query>  Semantic search")
    console.print("    [bold]bt similar[/bold] <n>     Entries similar to #n")
    console.print()

    # Actions
    console.print("  [bold cyan]Actions[/bold cyan] — act on numbered entries from last view")
    console.print("    [bold]bt <n> done[/bold]              Mark task(s) complete")
    console.print("    [bold]bt <n> drop[/bold]              Consciously delete")
    console.print("    [bold]bt <n> delete[/bold]            Permanently remove from disk")
    console.print("    [bold]bt <n> ![/bold]                 Toggle important flag")
    console.print("    [bold]bt <n> mod[/bold] <text>        Replace entry text")
    console.print("    [bold]bt <n> later[/bold]             Defer — remove from today's log")
    console.print("    [bold]bt <n> edit[/bold]              Open in $EDITOR")
    console.print("    [bold]bt <n> @tag[/bold]              Add a tag")
    console.print("    [bold]bt <n> untag @tag[/bold]        Remove a tag")
    console.print("    [bold]bt <n> undo[/bold]              Undo last action on entry")
    console.print("    [bold]bt undo[/bold]                  Undo last action globally")
    console.print("    [dim]Multiple entries:[/dim] [bold]bt 1 2 3 done[/bold]")
    console.print()

    # Habits
    console.print("  [bold cyan]Habits[/bold cyan] — daily tracking")
    console.print("    [bold]bt h[/bold]                  List habits with today's status")
    console.print("    [bold]bt h[/bold] <name>           Add a new habit")
    console.print("    [bold]bt h <n> done[/bold]         Mark habit done today")
    console.print("    [bold]bt h <n> undo[/bold]         Clear today's entry")
    console.print("    [bold]bt h <n> delete[/bold]       Remove habit permanently")
    console.print()

    # Rituals
    console.print("  [bold cyan]Rituals[/bold cyan] — guided BuJo workflows")
    console.print("    [bold]bt dp[/bold]              Daily plan — morning ritual")
    console.print("    [bold]bt wp[/bold]              Weekly plan — select tasks for the week")
    console.print()

    # AI
    console.print("  [bold cyan]AI Features[/bold cyan] — requires configured provider (bt init)")
    console.print("    [bold]bt review[/bold] [period]   AI summary (day/week/month)")
    console.print("    [bold]bt topic[/bold] <name>      Cross-dimension synthesis")
    console.print("    [bold]bt nudges[/bold]            AI-generated actionable suggestions")
    console.print()

    # FFFF
    console.print("  [bold cyan]FFFF Pipeline[/bold cyan] — ideas to action")
    console.print("    [bold]bt find[/bold] <collection>    Gather raw material")
    console.print("    [bold]bt form[/bold] <collection>    AI categorizes → user confirms")
    console.print("    [bold]bt focus[/bold] <collection>   AI cuts to 20% → user confirms")
    console.print("    [bold]bt finish[/bold] <collection>  AI generates tasks → user confirms")
    console.print()

    # System
    console.print("  [bold cyan]System[/bold cyan]")
    console.print("    [bold]bt start[/bold]           Quick start guide — the bt way")
    console.print("    [bold]bt init[/bold]            First-run setup (pick AI provider)")
    console.print("    [bold]bt rebuild[/bold]         Re-embed all entries for semantic search")
    console.print("    [bold]bt --version[/bold]       Show version")
    console.print()


@click.group(cls=DwnGroup, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="bt")
@click.pass_context
def main(ctx):
    """bt (BuTe) — AI-powered life management CLI based on Bullet Journal."""
    ctx.ensure_object(dict)
    from bute.config import load_config

    ctx.obj["config"] = load_config()

    if not ctx.invoked_subcommand:
        from bute.state import is_dyts_done_today

        config = ctx.obj["config"]
        if is_dyts_done_today(config):
            # Daily plan already done — show daily log (focus view)
            from datetime import date
            from bute.display import display_entry_list
            from bute.ritual_ops import get_daily_log
            from bute.state import save_state

            entries = get_daily_log(config)
            display_entry_list(entries, f"Today — {date.today().strftime('%a %b %d')}")

            # Show habits
            from bute.commands.views import _show_habits
            habit_names = _show_habits(config, len(entries))

            save_state("ls", [e.id for e in entries], config, habits=habit_names)

            from rich.console import Console
            console = Console()
            console.print(f"\n  [dim]Daily plan done. Run[/dim] [bold]bt dp[/bold] [dim]to redo.[/dim]")
        else:
            ctx.invoke(dp_cmd)


# --- Register commands ---

from bute.commands.capture import capture_cmd  # noqa: E402
from bute.commands.action import action_cmd, undo_cmd  # noqa: E402
from bute.commands.init_cmd import init_cmd  # noqa: E402
from bute.commands.views import (  # noqa: E402
    active_cmd,
    calendar_cmd,
    journals_cmd,
    ls_cmd,
    notes_cmd,
    tag_filter_cmd,
    tags_cmd,
    tasks_cmd,
)
from bute.commands.rituals import (  # noqa: E402
    dp_cmd,
    linelog_cmd,
    recap_cmd,
    review_cmd,
    wp_cmd,
)
from bute.commands.habits import habits_cmd  # noqa: E402
from bute.commands.search import rebuild_cmd, search_cmd, similar_cmd  # noqa: E402
from bute.commands.topic import topic_cmd  # noqa: E402
from bute.commands.nudges import nudges_cmd  # noqa: E402
from bute.commands.ffff import find_cmd, form_cmd, focus_cmd, finish_cmd  # noqa: E402
from bute.commands.start import start_cmd  # noqa: E402

main.add_command(init_cmd)
main.add_command(start_cmd)
main.add_command(capture_cmd)
main.add_command(action_cmd)
main.add_command(undo_cmd)
main.add_command(ls_cmd)
main.add_command(tasks_cmd)
main.add_command(notes_cmd)
main.add_command(journals_cmd)
main.add_command(calendar_cmd)
main.add_command(active_cmd)
main.add_command(tag_filter_cmd)
main.add_command(tags_cmd)
main.add_command(dp_cmd)
main.add_command(habits_cmd)
main.add_command(linelog_cmd)
main.add_command(wp_cmd)
main.add_command(recap_cmd)
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
