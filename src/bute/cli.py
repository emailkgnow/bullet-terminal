"""CLI entry point and custom command routing for bute."""

import re
import sys

import click

from bute import __version__

# Short signifier pattern: t, /t, t!, /t!, n, j, c, etc.
SIGNIFIER_PATTERN = re.compile(r"^/?[tnjc]!?$")
# Bullet signifier pattern: . = - o (with optional !)
BULLET_PATTERN = re.compile(r"^[.=\-o]!?$")
# Full word capture: task, note, journal, calendar (with optional !)
WORD_SIGNIFIER_PATTERN = re.compile(r"^(task|note|journal|calendar)!?$")

# Short letter to view command mapping (when no text follows)
SHORT_TO_VIEW = {"t": "tasks", "n": "notes", "j": "journals", "c": "calendar", "b": "backlog", "m": "monthly"}
BULLET_TO_VIEW = {".": "tasks", "=": "journals", "-": "notes", "o": "calendar"}
WORD_TO_VIEW = {"task": "tasks", "note": "notes", "journal": "journals", "calendar": "calendar"}


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
        if first == "b":
            cmd = self.get_command(ctx, "backlog")
            if cmd is not None:
                return "backlog", cmd, rest

        if first == "m":
            cmd = self.get_command(ctx, "monthly")
            if cmd is not None:
                return "monthly", cmd, rest

        if first in ("h", "habit"):
            cmd = self.get_command(ctx, "habits")
            if cmd is not None:
                return "habits", cmd, rest

        # 3. Signifier (short: t, /t | bullet: . = - o | word: task, note, journal, cal)
        is_short = SIGNIFIER_PATTERN.match(first)
        is_bullet = BULLET_PATTERN.match(first)
        is_word = WORD_SIGNIFIER_PATTERN.match(first)

        if is_short or is_bullet or is_word:
            # Check if rest is only view flags/options (not capture text)
            view_flags = {"-a", "--all"}
            is_view_args = rest and all(
                r.startswith("@") or r in view_flags for r in rest
            )

            # Text follows (and not just @tag or view flags) → capture
            has_text = rest and not is_view_args
            if has_text:
                cmd = self.get_command(ctx, "capture")
                if cmd is not None:
                    return "capture", cmd, args

            # No text (or only @tag / view flags) → view
            has_bang = first.endswith("!") or (first.startswith("/") and first.endswith("!"))
            stripped = first.rstrip("!").lstrip("/")

            # Signifier with ! and no text → important filtered view
            if has_bang and not has_text:
                cmd = self.get_command(ctx, "important")
                if cmd is not None:
                    view_args = [stripped]
                    for r in rest:
                        if r in view_flags:
                            view_args.append(r)
                    return "important", cmd, view_args

            if is_word:
                view_name = WORD_TO_VIEW.get(stripped)
            elif is_bullet:
                view_name = BULLET_TO_VIEW.get(stripped)
            else:
                view_name = SHORT_TO_VIEW.get(stripped)

            if view_name:
                cmd = self.get_command(ctx, view_name)
                if cmd is not None:
                    # Pass remaining args (strip @ from tags)
                    view_args = []
                    for r in rest:
                        if r.startswith("@"):
                            view_args.append(r[1:])
                        elif r in view_flags:
                            view_args.append(r)
                    return view_name, cmd, view_args

        # 4. Important filter — ! alone
        if first == "!":
            cmd = self.get_command(ctx, "important")
            if cmd is not None:
                return "important", cmd, rest

        # 5. Tag filter — @tagname [subcommand]
        if first.startswith("@") and len(first) > 1:
            tag_name = first[1:]
            subcommand = rest[0] if rest else None

            if subcommand == "analyze":
                cmd = self.get_command(ctx, "analyze_tag")
                if cmd is not None:
                    return "analyze_tag", cmd, [tag_name]
            elif subcommand == "map":
                cmd = self.get_command(ctx, "map_tag")
                if cmd is not None:
                    return "map_tag", cmd, [tag_name]
            else:
                cmd = self.get_command(ctx, "tag_filter")
                if cmd is not None:
                    return "tag_filter", cmd, [tag_name]

        # 6. Number-action — first token is a digit
        # (+collection routing was here — removed in tags-absorb-collections)
        if first.isdigit():
            try:
                from bute.state import load_state
                state = load_state()

                # Pure habits view — all numbers are habits
                if state.get("view") == "habits":
                    cmd = self.get_command(ctx, "habits")
                    if cmd is not None:
                        return "habits", cmd, args

                # Goals view — number only (no action) drills into goal
                if state.get("view") == "goals" and len(args) == 1 and first.isdigit():
                    cmd = self.get_command(ctx, "goal_drill")
                    if cmd is not None:
                        return "goal_drill", cmd, args

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

            # Bare number (no action) — default to edit
            if all(tok.isdigit() for tok in args):
                args = list(args) + ["edit"]

            cmd = self.get_command(ctx, "action")
            if cmd is not None:
                return "action", cmd, args

        # 7. Unknown — let Click produce the error
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
    console.print("    [green]bt c[/green] <text>      Calendar event  [dim]bt c standup t:9[/dim]")
    console.print("    Full words work too: [dim]bt task, bt note, bt journal, bt calendar[/dim]")
    console.print("    BuJo bullets work too: [dim]bt . (task)  bt - (note)  bt = (journal)  bt o (event)[/dim]")
    console.print("    Add [bold red]![/bold red] for important: [dim]bt t! fix prod bug[/dim]")
    console.print("    Add [bold]@tag[/bold] and [bold]key:value[/bold]: [dim]bt t fix bug @backend due:tomorrow[/dim]")
    console.print("    [bold]d:[/bold] date — [dim]d:4.7  d:tom  d:fri  d:mar15[/dim]  (works on all types)")
    console.print("    [bold]t:[/bold] time — [dim]t:9  t:14.30[/dim]  (24h, for calendar events)")
    console.print("    [bold]r:[/bold] recur — [dim]r:daily  r:weekly  r:monthly  r:yearly[/dim]")
    console.print("    [dim]Tasks auto-get @thisweek (focus). Use -l/--later for backlog only.[/dim]")
    console.print("    [dim]Tip: first sentence = title in list views. Start entries with a clear topic sentence.[/dim]")
    console.print()

    # Views
    console.print("  [bold cyan]Views[/bold cyan] — same letters, no text = view")
    console.print("    [bold]bt[/bold]                 Daily plan if not done today, else today's log")
    console.print("    [bold]bt t[/bold] [@tag]        Tasks — this week's focus ([dim]-a/--all[/dim] for done/dropped)")
    console.print("    [bold]bt b[/bold] [@tag]        Task Backlog — all active tasks")
    console.print("    [bold]bt n[/bold] [@tag]        All notes")
    console.print("    [bold]bt j[/bold] [@tag]        All journal entries")
    console.print("    [bold]bt c[/bold] [@tag]        All events")
    console.print("    [bold]bt m[/bold] [period]      Monthly log ([dim]default: this month, YYYY-MM or YYYY[/dim])")
    console.print("    [bold]bt due[/bold]              Tasks by deadline — overdue, today, next 7 days ([dim]bt due all[/dim])")
    console.print("    [bold]bt week[/bold] [last]     Weekly spread — all entries Mon-Sun")
    console.print("    [bold]bt tags[/bold]            List all tags with entry counts and stage")
    console.print("    [bold]bt ![/bold]               All important entries")
    console.print("    [bold]bt t![/bold]              Important tasks ([dim]also: n!, j!, c!, task!, .![/dim])")
    console.print("    [bold]bt @tagname[/bold]        Filter by tag across all dimensions")
    console.print("    [bold]bt find[/bold] <keyword>  Keyword search in body and tags ([dim]-t -n -j -c[/dim])")
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
    console.print("    [bold]bt <n> open[/bold]              Open in $EDITOR [dim](also: edit)[/dim]")
    console.print("    [bold]bt <n> @tag[/bold]              Add a tag")
    console.print("    [bold]bt <n> untag @tag[/bold]        Remove a tag")
    console.print("    [bold]bt <n> undo[/bold]              Undo last action on entry")
    console.print("    [bold]bt undo[/bold]                  Undo last action globally")
    console.print("    [bold]bt <n> title[/bold]            AI-generate a topic sentence")
    console.print("    [bold]bt <n> map[/bold]              Mind map an @ai-analysis note")
    console.print("    [bold]bt <n> chat[/bold]             AI chat — think through an entry")
    console.print("    [dim]Multiple entries:[/dim] [bold]bt 1 2 3 done[/bold]")
    console.print()

    # Habits
    console.print("  [bold cyan]Habits[/bold cyan] — daily tracking (entries with @habit r:daily)")
    console.print("    [bold]bt h[/bold]                  List habits with today's status")
    console.print("    [bold]bt h[/bold] <name>           Add a new habit")
    console.print("    [bold]bt h <n> done[/bold]         Mark habit done today")
    console.print("    [bold]bt h <n> undo[/bold]         Clear today's entry")
    console.print("    [bold]bt h <n> delete[/bold]       Remove habit permanently")
    console.print("    [bold]bt streak[/bold]            Habit streaks, trends, and 30-day stats")
    console.print("    [bold]bt migrate-habits[/bold]    Migrate old config habits to entries")
    console.print()

    # Goals
    console.print("  [bold cyan]Goals[/bold cyan] — orient tasks toward outcomes")
    console.print("    [bold]bt goals[/bold]            Show goals with task progress")
    console.print()

    # Rituals
    console.print("  [bold cyan]Rituals[/bold cyan] — guided BuJo workflows")
    console.print("    [bold]bt dump[/bold]             Rapid-fire tasks → Backlog ([dim]add @today or @thisweek to focus[/dim])")
    console.print("    [bold]bt dp[/bold]              Daily plan — morning ritual ([dim]-y for non-interactive[/dim])")
    console.print("    [bold]bt wp[/bold]              Weekly plan — select tasks for the week ([dim]-y[/dim])")
    console.print("    [bold]bt recap[/bold]             End-of-day summary — done, open, dropped, captured")
    console.print("    [bold]bt recap[/bold] [period]    AI analysis of a period ([dim]day, week, month, year[/dim])")
    console.print()

    # AI
    console.print("  [bold cyan]AI Features[/bold cyan] — requires configured provider (bt init)")
    console.print("    [bold]bt <n> chat[/bold]           Think through an entry — suggests entries to create at exit")
    console.print("    [bold]bt topic[/bold] <name>      Cross-dimension synthesis")
    console.print("    [bold]bt nudges[/bold]            AI-generated actionable suggestions")
    console.print()

    # Tag Processing
    console.print("  [bold cyan]Tag Processing[/bold cyan] — ideas to action")
    console.print("    [bold]bt @[/bold]<name> [bold]analyze[/bold]     AI clusters and organizes tagged entries")
    console.print("    [bold]bt @[/bold]<name> [bold]map[/bold]         Mind map visualization of tag analysis")
    console.print()

    # System
    console.print("  [bold cyan]System[/bold cyan]")
    console.print("    [bold]bt start[/bold]           Quick start guide — the bt way")
    console.print("    [bold]bt init[/bold]            First-run setup (pick AI provider)")
    console.print("    [bold]bt rebuild[/bold]         Re-embed all entries for semantic search")
    console.print("    [bold]bt export[/bold]          Export all data as a zip file ([dim]-o path[/dim])")
    console.print("    [bold]bt -i[/bold]              Interactive REPL — no quoting needed")
    console.print("    [bold]bt -d[/bold]              Toggle demo mode — isolated data for presentations")
    console.print("    [bold]bt --version[/bold]       Show version")
    console.print()


def _run_interactive(ctx):
    """Run the interactive REPL — commands without 'bt' prefix."""
    from rich.console import Console
    console = Console()

    console.print("\n  [bold]bt interactive[/bold] — type commands without 'bt' prefix. /exit to quit.\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if user_input in ("/exit", "/done"):
            break

        # Strip leading 'bt' if user types it out of habit
        args = user_input.split()
        if args and args[0] == "bt":
            args = args[1:]
        try:
            main(args, standalone_mode=False, parent=ctx)
        except click.exceptions.UsageError as e:
            console.print(f"  [red]{e.format_message()}[/red]")
        except SystemExit:
            pass  # Click raises SystemExit on --help etc.
        except Exception as e:
            console.print(f"  [red]{e}[/red]")

    console.print("  [dim]Exited interactive mode.[/dim]")


@click.group(cls=DwnGroup, invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="bt")
@click.option("-i", "interactive", is_flag=True, help="Interactive REPL mode")
@click.option("-d", "demo", is_flag=True, help="Toggle demo mode")
@click.pass_context
def main(ctx, interactive, demo):
    """bt (BuTe) — AI-powered life management CLI based on Bullet Journal."""
    ctx.ensure_object(dict)
    from bute.config import apply_demo_config, load_config

    config = load_config()

    # Handle -d flag before applying demo config
    if demo:
        from bute.commands.demo import demo_cmd
        config = apply_demo_config(config)
        ctx.obj["config"] = config
        ctx.invoke(demo_cmd)
        return

    config = apply_demo_config(config)
    ctx.obj["config"] = config

    from bute.config import is_demo_active
    if is_demo_active():
        click.echo("  ▶ DEMO MODE — bt -d to exit")

    # Handle -i flag
    if interactive:
        _run_interactive(ctx)
        return

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
            display_entry_list(entries, f"Today — {date.today().strftime('%a %b %d')}", hide_tags={"today", "thisweek"})

            # Show habits
            from bute.commands.views import _show_habits
            habit_names = _show_habits(config, len(entries))

            save_state("ls", [e.id for e in entries], config, habits=habit_names)

            from rich.console import Console
            console = Console()
            console.print(f"\n  [dim]Daily plan done. Run [bold]bt dp[/bold] to redo.[/dim]")
        else:
            ctx.invoke(dp_cmd)


# --- Register commands ---

from bute.commands.capture import capture_cmd  # noqa: E402
from bute.commands.action import action_cmd, undo_cmd  # noqa: E402
from bute.commands.init_cmd import init_cmd  # noqa: E402
from bute.commands.views import (  # noqa: E402
    backlog_cmd,
    calendar_cmd,
    due_cmd,
    goal_drill_cmd,
    goals_cmd,
    important_cmd,
    journals_cmd,
    notes_cmd,
    tag_filter_cmd,
    tags_cmd,
    tasks_cmd,
    week_cmd,
)
from bute.commands.rituals import (  # noqa: E402
    dp_cmd,
    dump_cmd,
    monthly_cmd,
    recap_cmd,
    wp_cmd,
)
from bute.commands.habits import habits_cmd, migrate_habits_cmd, streak_cmd  # noqa: E402
from bute.commands.export import export_cmd  # noqa: E402
from bute.commands.search import find_cmd, rebuild_cmd, search_cmd, similar_cmd  # noqa: E402
from bute.commands.topic import topic_cmd  # noqa: E402
from bute.commands.nudges import nudges_cmd  # noqa: E402
from bute.commands.start import start_cmd  # noqa: E402
from bute.commands.tags import analyze_tag_cmd, map_tag_cmd  # noqa: E402
from bute.commands.demo import demo_cmd  # noqa: E402

main.add_command(init_cmd)
main.add_command(start_cmd)
main.add_command(capture_cmd)
main.add_command(action_cmd)
main.add_command(undo_cmd)
main.add_command(tasks_cmd)
main.add_command(backlog_cmd)
main.add_command(notes_cmd)
main.add_command(journals_cmd)
main.add_command(calendar_cmd)
main.add_command(tag_filter_cmd)
main.add_command(important_cmd)
main.add_command(tags_cmd)
main.add_command(week_cmd)
main.add_command(due_cmd)
main.add_command(goals_cmd)
main.add_command(goal_drill_cmd)
main.add_command(dp_cmd)
main.add_command(dump_cmd)
main.add_command(habits_cmd)
main.add_command(streak_cmd)
main.add_command(monthly_cmd)
main.add_command(wp_cmd)
main.add_command(recap_cmd)
main.add_command(search_cmd)
main.add_command(find_cmd)
main.add_command(similar_cmd)
main.add_command(rebuild_cmd)
main.add_command(export_cmd)
main.add_command(topic_cmd)
main.add_command(nudges_cmd)
main.add_command(analyze_tag_cmd)
main.add_command(map_tag_cmd)
main.add_command(demo_cmd)
main.add_command(migrate_habits_cmd)
