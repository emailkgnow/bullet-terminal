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
SHORT_TO_VIEW = {"t": "tasks", "n": "notes", "j": "journals", "c": "calendar", "b": "backlog", "d": "daily", "w": "week", "m": "monthly"}
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

        if first == "d":
            cmd = self.get_command(ctx, "daily")
            if cmd is not None:
                return "daily", cmd, rest

        if first == "m":
            cmd = self.get_command(ctx, "monthly")
            if cmd is not None:
                return "monthly", cmd, rest

        if first == "w":
            cmd = self.get_command(ctx, "week")
            if cmd is not None:
                return "week", cmd, rest

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

        # 5. Tag filter — @tag [@tag2] [-@excluded]
        if first.startswith("@") and len(first) > 1:
            tag_name = first[1:]

            # Collect all @tag and -@tag tokens
            include_tags = [tag_name]
            exclude_tags = []
            for r in rest:
                if r.startswith("@") and len(r) > 1:
                    include_tags.append(r[1:])
                elif r.startswith("-@") and len(r) > 2:
                    exclude_tags.append(r[2:])

            cmd = self.get_command(ctx, "tag_filter")
            if cmd is not None:
                filter_args = include_tags
                for ex in exclude_tags:
                    filter_args.extend(["--exclude", ex])
                return "tag_filter", cmd, filter_args

        # Also handle -@tag as first token (exclude-only filter)
        if first.startswith("-@") and len(first) > 2:
            exclude_tags = [first[2:]]
            include_tags = []
            for r in rest:
                if r.startswith("@") and len(r) > 1:
                    include_tags.append(r[1:])
                elif r.startswith("-@") and len(r) > 2:
                    exclude_tags.append(r[2:])

            cmd = self.get_command(ctx, "tag_filter")
            if cmd is not None:
                filter_args = include_tags if include_tags else ["--all"]
                for ex in exclude_tags:
                    filter_args.extend(["--exclude", ex])
                return "tag_filter", cmd, filter_args

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


def _show_random_journal(config, offset: int = 0) -> str | None:
    """Show a random old journal entry at the bottom of the daily log. Returns entry ID."""
    from bute.config import CONFIG_DIR

    if (CONFIG_DIR / ".no-journal").exists():
        return None

    import random
    from datetime import date

    from bute.display import _preview
    from bute.storage import query_and_load

    today = date.today()
    journals = query_and_load(config, type="journal")
    old = [e for e in journals if e.created.date() < today]
    if not old:
        return None

    entry = random.choice(old)
    entry_date = entry.created.date().strftime("%b %d, %Y")
    num = offset + 1

    from rich.console import Console
    console = Console()
    console.print()
    console.print(f"  [dim]{num:>3}  = {_preview(entry.body)}[/dim]")
    console.print(f"  [dim]     {entry_date} · bt -j to toggle[/dim]")
    return entry.id


def _print_help():
    """Print the full bute help using Rich."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print()
    console.print("  [bold]bt[/bold] (Bullet-Terminal) — AI-powered life management CLI")

    # --- Capture ---
    t = Table(title="Capture — type what's on your mind", title_style="bold cyan",
              box=None, pad_edge=False, padding=(0, 2), show_header=True, header_style="bold dim", expand=True)
    t.add_column("Command", style="bold", no_wrap=True)
    t.add_column("What")
    t.add_column("Example", style="dim")
    t.add_row("[cyan]bt t[/cyan] <text>", "Task", "bt t call dentist due:friday")
    t.add_row("[cyan]bt t -l[/cyan] <text>", "Backlog task (skip focus)", "bt t -l research flights")
    t.add_row("[yellow]bt n[/yellow] <text>", "Note / idea", "bt n OAuth2 tokens expire in 30 days")
    t.add_row("[magenta]bt j[/magenta] <text>", "Journal", "bt j rough morning, couldn't focus")
    t.add_row("[green]bt c[/green] <text>", "Calendar event", "bt c standup t:9")
    console.print()
    console.print(t)
    console.print()
    console.print("    [dim]Also:[/dim] bt task, bt note, bt journal, bt calendar [dim]or BuJo bullets:[/dim] bt . - = o")
    console.print("    [dim]Modifiers:[/dim] [bold red]![/bold red] important  [bold]@tag[/bold]  [bold]d:[/bold]date  [bold]t:[/bold]time  [bold]due:[/bold]deadline  [bold]r:[/bold]recur")

    # --- Views ---
    t = Table(title="Views — same letters, no text = view", title_style="bold cyan",
              box=None, pad_edge=False, padding=(0, 2), show_header=True, header_style="bold dim", expand=True)
    t.add_column("Command", style="bold", no_wrap=True)
    t.add_column("Shows")
    t.add_column("Notes", style="dim")
    t.add_row("bt", "Today's log", "Daily plan if not done today")
    t.add_row("bt t", "Tasks — this week's focus", "-a for done/dropped")
    t.add_row("bt b", "Task Backlog — all active tasks", "")
    t.add_row("bt n", "Notes", "Grouped by date")
    t.add_row("bt j", "Journals", "Grouped by date")
    t.add_row("bt c", "Events", "Grouped by date")
    t.add_row("bt h", "Habits", "Today's status")
    t.add_row("bt d [dim][date]", "Daily Log — everything for a day", "bt d yesterday, bt d 4.3")
    t.add_row("bt w [dim][last|N]", "Weekly Log — Mon to Sun", "bt w last, bt w 14")
    t.add_row("bt m [dim][month|YYYY]", "Monthly Log", "bt m jan, bt m 2026-03, bt m 2026")
    t.add_row("bt due", "Tasks by deadline", "bt due all for everything")
    t.add_row("bt goals", "Goals with task progress", "")
    t.add_row("bt streak", "Habit streaks and 30-day stats", "")
    t.add_row("bt tags", "All tags with counts and stage", "")
    t.add_row("bt !", "Important entries", "bt t! for tasks only")
    t.add_row("bt @tag [@tag2] [-@ex]", "Filter by tags (AND + exclude)", "bt @backend -@done")
    t.add_row("bt find <text>", "Keyword search", "-t -n -j -c to filter")
    console.print()
    console.print(t)

    # --- Actions ---
    t = Table(title="Actions — act on numbered entries from last view", title_style="bold cyan",
              box=None, pad_edge=False, padding=(0, 2), show_header=True, header_style="bold dim", expand=True)
    t.add_column("Command", style="bold", no_wrap=True)
    t.add_column("What it does")
    t.add_column("Example", style="dim")
    t.add_row("bt <n> done", "Mark task(s) complete", "bt 1 done")
    t.add_row("bt <n> drop", "Consciously delete", "bt 2 3 drop")
    t.add_row("bt <n> !", "Toggle important flag", "bt 1 !")
    t.add_row("bt <n> later", "Defer — remove from today's log", "bt 3 later")
    t.add_row("bt <n> open", "Open in $EDITOR", "bt 1 open")
    t.add_row("bt <n> mod <text>", "Replace entry text", "bt 1 mod new text here")
    t.add_row("bt <n> @tag", "Add a tag", "bt 1 @backend")
    t.add_row("bt <n> untag @tag", "Remove a tag", "bt 1 untag @backend")
    t.add_row("bt <n> delete", "Permanently remove from disk", "bt 1 delete")
    t.add_row("bt undo", "Undo last action", "bt undo")
    console.print()
    console.print(t)
    console.print()
    console.print("    [dim]Tip: most actions accept multiple entries — bt 1 2 3 done[/dim]")

    # --- Commands ---
    t = Table(title="Commands", title_style="bold cyan",
              box=None, pad_edge=False, padding=(0, 2), show_header=True, header_style="bold dim", expand=True)
    t.add_column("Command", style="bold", no_wrap=True)
    t.add_column("What it does")
    t.add_column("Notes", style="dim")
    t.add_row("bt dp", "Daily plan — morning ritual", "-y for non-interactive")
    t.add_row("bt wp", "Weekly plan — select tasks for the week", "-y for non-interactive")
    t.add_row("bt dump", "Rapid-fire tasks into Backlog", "")
    t.add_row("bt recap <period>", "AI analysis of a period", "bt recap week/month/year")
    t.add_row("bt export", "Export all data as zip", "-o path")
    t.add_row("bt init", "First-run setup (pick AI provider)", "")
    t.add_row("bt start", "Quick start guide", "")
    t.add_row("bt rebuild", "Rebuild search index", "")
    t.add_row("bt -i", "Interactive REPL", "No quoting needed")
    t.add_row("bt -d", "Toggle demo mode", "Isolated data")
    t.add_row("bt -j", "Toggle random journal in daily log", "")
    console.print()
    console.print(t)

    # --- AI ---
    t = Table(title="AI — requires bt init", title_style="bold cyan",
              box=None, pad_edge=False, padding=(0, 2), show_header=True, header_style="bold dim", expand=True)
    t.add_column("Command", style="bold", no_wrap=True)
    t.add_column("What it does")
    t.add_column("Example", style="dim")
    t.add_section()
    t.add_row("[dim]actions[/dim]", "", "")
    t.add_row("bt <n> chat", "Think through entries with AI", "bt 1 2 chat")
    t.add_row("bt <n> title", "AI-generate a topic sentence", "bt 3 title")
    t.add_row("bt <n> map", "Mind map an @ai-analysis note", "bt 1 map")
    t.add_section()
    t.add_row("[dim]commands[/dim]", "", "")
    t.add_row("bt analyze @tag [-@ex]", "AI clusters tagged entries", "bt analyze @bt @ai")
    t.add_row("bt map @tag [-@ex]", "Mind map of tag analysis", "bt map @backend")
    t.add_row("bt topic <name>", "Cross-dimension synthesis", "bt topic productivity")
    t.add_row("bt nudges", "Actionable suggestions", "")
    t.add_row("bt recap <period>", "AI analysis of a period", "bt recap week")
    t.add_row("bt search <query>", "Semantic search", "bt search diet plans")
    t.add_row("bt similar <n>", "Entries similar to #n", "bt similar 3")
    console.print()
    console.print(t)
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
@click.option("-j", "toggle_journal", is_flag=True, help="Toggle random journal in daily log")
@click.pass_context
def main(ctx, interactive, demo, toggle_journal):
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

    # Handle -j flag — toggle random journal
    if toggle_journal:
        from bute.config import CONFIG_DIR
        marker = CONFIG_DIR / ".no-journal"
        if marker.exists():
            marker.unlink()
            click.echo("  Random journal enabled in daily log.")
        else:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            marker.touch()
            click.echo("  Random journal disabled in daily log.")
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

            # Random old journal whisper (numbered after entries + habits)
            journal_id = _show_random_journal(config, len(entries) + len(habit_names))

            save_state("ls", [e.id for e in entries], config, habits=habit_names, extra_entries=[journal_id] if journal_id else None)

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
    daily_log_cmd,
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
main.add_command(daily_log_cmd)
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
