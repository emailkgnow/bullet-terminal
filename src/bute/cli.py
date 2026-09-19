"""CLI entry point and custom command routing for bt."""

import re
import sys

import click

from bute import __version__

# Short signifier pattern: t, /t, t!, /t!, n, j, c, etc.
SIGNIFIER_PATTERN = re.compile(r"^/?[tnjc]!?$")
# Full word capture: task, note, journal, calendar (with optional !)
WORD_SIGNIFIER_PATTERN = re.compile(r"^(task|note|journal|calendar)!?$")
# Action selector: bare number or range like 1-4
ACTION_NUMBER_PATTERN = re.compile(r"^\d+(-\d+)?$")

# Short letter to view command mapping (when no text follows)
SHORT_TO_VIEW = {"t": "tasks", "n": "notes", "j": "journals", "c": "calendar", "b": "backlog"}
WORD_TO_VIEW = {"task": "tasks", "note": "notes", "journal": "journals", "calendar": "calendar"}


def _is_capture_like(args: list[str]) -> bool:
    """True if argv will route to capture / open_capture / a `mod` action.

    On those paths the remaining tokens become the entry body, so `--json`
    must be left alone — stripping it would silently edit the user's text.
    Mirrors the routing conditions in resolve_command, ignoring `--json`
    itself when deciding whether capture text follows a signifier.
    """
    if not args:
        return False
    first = args[0]
    rest = [a for a in args[1:] if a != "--json"]

    if SIGNIFIER_PATTERN.match(first) or WORD_SIGNIFIER_PATTERN.match(first):
        view_flags = {"-a", "--all"}
        # Only @tags / view flags after the signifier → it's a view, not capture.
        return bool(rest) and not all(r.startswith("@") or r in view_flags for r in rest)

    # Number-action with a `mod` verb — the tail is replacement body text.
    if ACTION_NUMBER_PATTERN.match(first):
        return any(tok in ("mod", "modify") for tok in rest)

    return False


class DwnGroup(click.Group):
    """Custom group that dispatches signifiers and number-actions."""

    def format_help(self, ctx, formatter):
        """Override default help to show our custom Rich help."""
        _print_help()

    def shell_complete(self, ctx, incomplete):
        """Complete @tags at the first position (bt @ba<TAB>); otherwise command names."""
        if incomplete.startswith("@"):
            from bute.completion import complete_tags
            return complete_tags(ctx, None, incomplete)
        return super().shell_complete(ctx, incomplete)

    def parse_args(self, ctx, args):
        """Prevent Click from treating -@tag as an option flag; hoist --json to the front."""
        args = list(args)
        # Never hoist out of capture text — `bt n add --json flag to api` must
        # store the literal word, not silently lose it (see _is_capture_like).
        has_json = "--json" in args and not _is_capture_like(args)
        if has_json:
            args = [a for a in args if a != "--json"]
        if args and args[0].startswith("-@"):
            args = ["--"] + args
        if has_json:
            args = ["--json"] + args
        return super().parse_args(ctx, args)

    def resolve_command(self, ctx, args):
        if not args:
            return super().resolve_command(ctx, args)

        first = args[0]
        rest = args[1:]

        # 1. Word signifier with text → capture (before named command check,
        #    so "bt calendar meet mom" routes to capture, not the calendar view)
        if rest and WORD_SIGNIFIER_PATTERN.match(first):
            view_flags = {"-a", "--all"}
            if not all(r.startswith("@") or r in view_flags for r in rest):
                if rest == ("open",) or rest == ["open"]:
                    cmd = self.get_command(ctx, "open_capture")
                    if cmd is not None:
                        return "open_capture", cmd, [first]
                cmd = self.get_command(ctx, "capture")
                if cmd is not None:
                    return "capture", cmd, args

        # 2. Named command — delegate to normal Click routing
        # Alias: bt overdue → bt due overdue
        if first == "overdue":
            cmd = self.get_command(ctx, "due")
            if cmd is not None:
                return "due", cmd, ["overdue"] + list(rest)

        cmd = self.get_command(ctx, first)
        if cmd is not None:
            return cmd.name, cmd, rest

        # 2. Single letter shortcuts
        if first == "b":
            cmd = self.get_command(ctx, "backlog")
            if cmd is not None:
                return "backlog", cmd, rest

        # 3. Signifier (short: t, /t | word: task, note, journal, calendar)
        is_short = SIGNIFIER_PATTERN.match(first)
        is_word = WORD_SIGNIFIER_PATTERN.match(first)

        if is_short or is_word:
            # Check if rest is only view flags/options (not capture text)
            view_flags = {"-a", "--all"}
            is_view_args = rest and all(
                r.startswith("@") or r in view_flags for r in rest
            )

            # Text follows (and not just @tag or view flags) → capture
            has_text = rest and not is_view_args
            if has_text:
                # Signifier + "open" → open $EDITOR for long-form capture
                if rest == ("open",) or rest == ["open"]:
                    cmd = self.get_command(ctx, "open_capture")
                    if cmd is not None:
                        return "open_capture", cmd, [first]

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

        # 6. Number-action — first token is a digit or range (e.g. 1-4)
        # (+collection routing was here — removed in tags-absorb-collections)
        if ACTION_NUMBER_PATTERN.match(first):
            # Bare number/range (no action) — default to edit
            if all(ACTION_NUMBER_PATTERN.match(tok) for tok in args):
                args = list(args) + ["edit"]

            cmd = self.get_command(ctx, "action")
            if cmd is not None:
                return "action", cmd, args

        # 7. Unknown — let Click produce the error
        return super().resolve_command(ctx, args)


def _show_random_journal(config, offset: int = 0) -> str | None:
    """Show a random old journal entry at the bottom of the Focus Log. Returns entry ID."""
    from bute.config import CONFIG_DIR

    if (CONFIG_DIR / ".no-journal").exists():
        return None

    import random
    from datetime import date

    from bute.display import _preview
    from bute.state import get_journal_history, record_journal_shown
    from bute.storage import query_and_load

    today = date.today()
    journals = query_and_load(config, type="journal")
    old = [e for e in journals if e.created.date() < today]
    if not old:
        return None

    # Skip the recently-shown ones. With a small collection every entry ends up
    # in the buffer — fall back to the full pool rather than showing nothing.
    recent = set(get_journal_history(config))
    pool = [e for e in old if e.id not in recent] or old

    entry = random.choice(pool)
    record_journal_shown(entry.id, config)
    entry_date = entry.created.date().strftime("%b %d, %Y")
    num = offset + 1

    from rich.console import Console
    console = Console()
    console.print()
    console.print(f"  [dim italic]{num:>3}  = {_preview(entry.body)}[/dim italic]", justify="right")
    console.print(f"  [dim italic]{entry_date}[/dim italic]", justify="right")
    return entry.id


def _print_help():
    """Print the full bt help using Rich."""
    from rich.align import Align
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    console = Console()
    console.print()
    console.print(Align.center(Text.from_markup("[bold]bt[/bold] (Bullet Terminal) — life management CLI")))

    # --- Capture ---
    t = Table(title="Capture — type what's on your mind", title_style="bold cyan",
              box=None, pad_edge=False, padding=(0, 2), show_header=True, header_style="bold dim", expand=True)
    t.add_column("Command", style="bold", no_wrap=True)
    t.add_column("What")
    t.add_column("Example", style="dim")
    t.add_row("[cyan]bt t[/cyan] <text>", "Task", "bt t call dentist due:friday")
    t.add_row("[cyan]bt t -l|--later[/cyan] <text>", "Task log (this week, not today)", "bt t --later research flights")
    t.add_row("[cyan]bt t -b|--backlog[/cyan] <text>", "Backlog task (no focus tags)", "bt t --backlog someday idea")
    t.add_row("[yellow]bt n[/yellow] <text>", "Note / idea", "bt n OAuth2 tokens expire in 30 days")
    t.add_row("[magenta]bt j[/magenta] <text>", "Journal", "bt j rough morning, couldn't focus")
    t.add_row("[green]bt c[/green] <text>", "Calendar event", "bt c standup t:9")
    t.add_row("[cyan]bt t[/cyan] <text> [bold]r:[/bold]<freq>", "Recurring task (habit)", "bt t meditate r:daily")
    t.add_row("bt t/n/j/c open", "Open $EDITOR for long-form capture", "bt j open")
    console.print()
    console.print(t)
    console.print()
    console.print("    [dim]Also:[/dim] bt task, bt note, bt journal, bt calendar")
    console.print("    [dim]Modifiers:[/dim] [bold red]![/bold red] important  [bold]@tag[/bold]  [bold]d:[/bold]date  [bold]t:[/bold]time  [bold]due:[/bold]deadline  [bold]r:[/bold]<daily|weekly|monthly|yearly>")
    console.print("    [dim]Tip:[/dim] dates like [bold]d:4.7[/bold], [bold]d:friday[/bold], [bold]d:next-friday[/bold] auto-resolve to the future. For past dates, use ISO: [bold]d:2026-03-15[/bold]")

    # --- Views ---
    t = Table(title="Views — same letters, no text = view", title_style="bold cyan",
              box=None, pad_edge=False, padding=(0, 2), show_header=True, header_style="bold dim", expand=True)
    t.add_column("Command", style="bold", no_wrap=True)
    t.add_column("Shows")
    t.add_column("Notes", style="dim")
    t.add_row("bt", "Focus Log", "wp → dp → Focus Log flow")
    t.add_row("bt -a", "Focus Log + hidden items", "dropped, non-focus captures, past events")
    t.add_row("bt t", "Tasks — this week's focus", "-a for done/dropped")
    t.add_row("bt b", "Task Backlog — all active tasks", "")
    t.add_row("bt n", "Notes", "Grouped by date")
    t.add_row("bt j", "Journals", "Grouped by date")
    t.add_row("bt c", "Events", "Grouped by date")
    t.add_row("bt due", "Tasks by deadline", "bt due all for everything")
    t.add_row("bt overdue", "Past-due tasks only", "")
    t.add_row("bt streak", "Recurring task streaks + 30-day rate", "")
    t.add_row("bt stats [dim][week|month]", "Momentum dashboard — streaks, trends", "bt stats week, bt stats month")
    t.add_row("bt tags", "All tags with counts", "")
    t.add_row("bt !", "Important entries", "bt t! for tasks only")
    t.add_row("bt @tag [@tag2] [-@ex]", "Filter by tags (AND + exclude)", "bt @backend -@done")
    t.add_row("bt find <text>", "Search full note contents — partial words", "bt find ntist finds dentist | -t -n -j -c")
    t.add_row("bt trash", "Trashed entries", "bt trash empty -y to purge")
    console.print()
    console.print(t)
    console.print()
    console.print("    [dim]Also:[/dim] [bold]bt task[/bold] / [bold]bt note[/bold] / [bold]bt journal[/bold] / [bold]bt calendar[/bold] — full words work everywhere [cyan]t[/cyan]/[yellow]n[/yellow]/[magenta]j[/magenta]/[green]c[/green] do")
    console.print("    [dim]Also:[/dim] [bold]bt backlog[/bold] — long form of [bold]b[/bold]")

    # --- Actions ---
    t = Table(title="Actions — act on numbered entries from last view", title_style="bold cyan",
              box=None, pad_edge=False, padding=(0, 2), show_header=True, header_style="bold dim", expand=True)
    t.add_column("Command", style="bold", no_wrap=True)
    t.add_column("What it does")
    t.add_column("Example", style="dim")
    t.add_row("bt <n> done", "Mark task(s) complete", "bt 1-4 done")
    t.add_row("bt <n> drop", "Consciously delete", "bt 2 3 drop")
    t.add_row("bt <n> !", "Toggle important flag", "bt 1 !")
    t.add_row("bt <n> later", "Defer to Task log (stays in this week)", "bt 3 later")
    t.add_row("bt <n> backlog", "Send to Backlog (remove all focus)", "bt 3 backlog")
    t.add_row("bt <n> show", "Read entry in leaf (q to quit), else Rich", "bt 1 view")
    t.add_row("bt <n> open", "Open in $EDITOR", "bt 1 open")
    t.add_row("bt <n> mod <text>", "Replace entry text", "bt 1 mod new text here")
    t.add_row("bt <n> @tag", "Add a tag", "bt 1-3 @backend")
    t.add_row("bt <n> due:<date>", "Set due date", "bt 1 due:friday")
    t.add_row("bt <n> d:<date>", "Set scheduled date", "bt 1 d:tomorrow")
    t.add_row("bt <n> t:<time>", "Set time", "bt 1 t:14.30")
    t.add_row("bt <n> clear <field>", "Remove @tag ! due d t repeat", "bt 1 clear @backend")
    t.add_row("bt <n> delete", "Move to trash (bt trash to see, restore to recover)", "bt 1 delete")
    t.add_row("bt <n> restore", "Restore from trash (after bt trash)", "bt trash → bt 1 restore")
    t.add_row("bt undo", "Undo last action", "bt undo")
    console.print()
    console.print(t)
    console.print()
    console.print("    [dim]<n> = entry number(s):[/dim] [bold]bt 1 done[/bold] · [bold]bt 1 2 3 done[/bold] (space) · [bold]bt 1-4 done[/bold] (range) · [bold]bt 1-3 7 done[/bold] (mix)")

    # --- Commands ---
    t = Table(title="Commands", title_style="bold cyan",
              box=None, pad_edge=False, padding=(0, 2), show_header=True, header_style="bold dim", expand=True)
    t.add_column("Command", style="bold", no_wrap=True)
    t.add_column("What it does")
    t.add_column("Notes", style="dim")
    t.add_row("bt dp [dim]| daily-plan", "Daily plan — pick today's tasks", "-y for non-interactive")
    t.add_row("bt wp [dim]| weekly-plan", "Weekly plan — select tasks for the week", "-y for non-interactive")
    t.add_row("bt export", "Export all data as zip", "-o path")
    t.add_row("bt init", "First-run setup (create data dirs)", "")
    t.add_row("bt rebuild", "Rebuild search index", "")
    t.add_row("bt completion [zsh|bash|fish]", "Print the shell line that enables @tag tab completion", "bt completion")
    t.add_row("bt -i [dim]| --interactive", "Interactive REPL", "No quoting needed")
    t.add_row("bt -d [dim]| --demo", "Demo session", "Isolated data, auto-cleanup")
    t.add_row("bt like <input>", "Find similar entries (semantic)", "bt like 3, bt like productivity")
    t.add_row("bt -j [dim]| --journal-whisper", "Toggle random journal whisper in Focus Log", "")
    t.add_row("bt <view> --json", "Emit numbered entry views as JSON", "bt b --json, bt @home --json")
    console.print()
    console.print(t)
    console.print()
    try:
        from bute.config import get_data_dir, load_config
        entries_hint = str(get_data_dir(load_config()) / "entries") + "/"
    except Exception:
        entries_hint = "your bt entries/ folder"
    console.print(f"  [bold]Bring your own AI.[/bold] [dim]Point any agent at[/dim] [bold]{entries_hint}[/bold] [dim]— bt auto-reconciles new .md files on next read. Schema: see README.md.[/dim]")
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
@click.option("-i", "--interactive", "interactive", is_flag=True, help="Interactive REPL mode")
@click.option("-d", "--demo", "demo", is_flag=True, help="Toggle demo mode")
@click.option("-j", "--journal-whisper", "toggle_journal", is_flag=True, help="Toggle random journal whisper in Focus Log")
@click.option("-a", "--all", "show_all", is_flag=True, help="Focus Log + hidden items (dropped, non-focus captures, past events)")
@click.option("--json", "as_json", is_flag=True, help="Emit views as JSON (for scripts and agents)")
@click.pass_context
def main(ctx, interactive, demo, toggle_journal, show_all, as_json):
    """bt (Bullet Terminal) — life management CLI based on Bullet Journal."""
    ctx.ensure_object(dict)

    from bute.display import set_json_mode
    set_json_mode(bool(as_json))

    # Reuse config from parent context (e.g. demo mode) or load from disk
    if "config" in ctx.obj:
        config = ctx.obj["config"]
    else:
        from bute.config import load_config
        config = load_config()
        ctx.obj["config"] = config

    # One-time migration: month-first → type-first storage layout
    if not ctx.obj.get("_migrated"):
        from bute.migration import needs_migration, migrate_entries
        if needs_migration(config):
            from rich.console import Console
            console = Console()
            result = migrate_entries(config)
            console.print(f"\n  [green]Migrated {result['total']} entries "
                          f"({result['task']} tasks, {result['note']} notes, "
                          f"{result['journal']} journals, {result['calendar']} calendar)[/green]")
            from bute.config import get_data_dir
            console.print(f"  [dim]Backup saved to {get_data_dir(config)}/entries-backup-*.zip[/dim]\n")
        ctx.obj["_migrated"] = True

    # Daily auto-backup — silent, idempotent, skipped in demo mode
    from bute.commands.backup import run_daily_backup_if_needed
    run_daily_backup_if_needed(config)

    # Handle -d flag — start isolated demo session
    if demo:
        from bute.commands.demo import demo_cmd
        ctx.invoke(demo_cmd)
        return

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
            click.echo("  Random journal enabled in Focus Log.")
        else:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            marker.touch()
            click.echo("  Random journal disabled in Focus Log.")
        return

    if not ctx.invoked_subcommand:
        config = ctx.obj["config"]

        if as_json:
            # Non-interactive callers always get the Focus Log — never the
            # first-run tour, the weekly plan, or the daily plan ritual,
            # none of which produce JSON and all of which have write
            # side effects (focus/week dates, completion markers).
            from datetime import date
            from bute.display import display_entry_list
            from bute.ritual_ops import get_daily_log
            from bute.state import save_state

            entries = get_daily_log(config, include_all=show_all)
            suffix = " (all)" if show_all else ""
            title = f"Focus Log — {date.today().strftime('%a %b %d')}{suffix}"
            display_entry_list(entries, title)
            save_state("ls", [e.id for e in entries], config)
            return

        # First-run onboarding — welcome → wp → dp → outro.
        from bute.commands.tour import run_tour, should_run_tour
        if should_run_tour(config):
            run_tour(ctx)
            return

        from datetime import date
        from bute.config import get_wp_day
        from bute.state import is_wp_done_this_week

        # Weekly plan trigger — on or after trigger day, if not done this week
        wp_day = get_wp_day(config)
        if date.today().weekday() >= wp_day and not is_wp_done_this_week(config):
            from bute.commands.rituals import wp_cmd as _wp_cmd
            ctx.invoke(_wp_cmd, non_interactive=False)

        from bute.state import is_dp_done_today, get_dp_history
        # First day — no dp history yet, show Focus Log so new users
        # see their entries instead of being thrown into daily plan.
        first_day = not get_dp_history(config)
        if is_dp_done_today(config) or first_day or show_all:
            # Daily plan already done (or first day, or -a) — show Focus Log
            from bute.display import display_entry_list
            from bute.ritual_ops import get_daily_log
            from bute.state import save_state

            entries = get_daily_log(config, include_all=show_all)
            from bute.models import EntryType as _ET, TaskStatus as _TS
            has_active_tasks = any(e.type == _ET.TASK and e.status == _TS.ACTIVE for e in entries)
            suffix = " (all)" if show_all else ""
            title = f"Focus Log — {date.today().strftime('%a %b %d')}{suffix}"
            if not has_active_tasks:
                title = f"[strike]{title}[/strike]"

            display_entry_list(entries, title)

            # Show recurring tasks — their IDs flow into the main entries list
            # for uniform numbering (bt <n> done works the same as for any entry)
            from bute.commands.views import _show_habits
            habit_ids = _show_habits(config, len(entries))

            entry_ids = [e.id for e in entries] + habit_ids

            # Random old journal whisper (numbered after entries + habits)
            journal_id = _show_random_journal(config, len(entry_ids))

            save_state("ls", entry_ids, config, extra_entries=[journal_id] if journal_id else None)

        else:
            ctx.invoke(dp_cmd)


# --- Register commands ---

from bute.commands.capture import capture_cmd, open_capture_cmd  # noqa: E402
from bute.commands.action import action_cmd, undo_cmd  # noqa: E402
from bute.commands.init_cmd import init_cmd  # noqa: E402
from bute.commands.views import (  # noqa: E402
    backlog_cmd,
    calendar_cmd,
    due_cmd,
    important_cmd,
    journals_cmd,
    notes_cmd,
    tag_filter_cmd,
    tags_cmd,
    tasks_cmd,
)
from bute.commands.rituals import (  # noqa: E402
    dp_cmd,
    wp_cmd,
)
from bute.commands.habits import streak_cmd  # noqa: E402
from bute.commands.stats import stats_cmd  # noqa: E402
from bute.commands.export import export_cmd  # noqa: E402
from bute.commands.search import find_cmd, like_cmd, rebuild_cmd, readme_cmd  # noqa: E402
from bute.commands.demo import demo_cmd  # noqa: E402
from bute.commands.zen import this_cmd  # noqa: E402
from bute.commands.trash import trash_cmd  # noqa: E402
from bute.completion import completion_cmd  # noqa: E402

main.add_command(init_cmd)
main.add_command(capture_cmd)
main.add_command(open_capture_cmd)
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
main.add_command(due_cmd)
main.add_command(dp_cmd)
main.add_command(dp_cmd, name="daily-plan")
main.add_command(streak_cmd)
main.add_command(wp_cmd)
main.add_command(wp_cmd, name="weekly-plan")
main.add_command(like_cmd)
main.add_command(find_cmd)
main.add_command(rebuild_cmd)
main.add_command(readme_cmd)
main.add_command(export_cmd)
main.add_command(demo_cmd)
main.add_command(stats_cmd)
main.add_command(this_cmd)
main.add_command(trash_cmd)
main.add_command(completion_cmd)
