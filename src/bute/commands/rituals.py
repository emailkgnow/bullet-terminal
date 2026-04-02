"""Ritual commands for bute (dp/dailyplan, wp/weeklyplan, review)."""

from datetime import date

import click
from rich.console import Console

from bute.display import (
    confirm_capture,
    display_action_confirmation,
    display_entry_list,
    display_ritual_header,
)
from bute.models import Entry, TaskStatus
from bute.ritual_ops import (
    clear_weekly_selection,
    get_all_active_tasks,
    get_today_schedule,
    get_weekly_active_tasks,
    get_yesterday_unresolved,
    process_dump_line,
    set_weekly_selection,
)
from bute.state import save_state
from bute.storage import update_entry

console = Console()


# --- Daily Plan (Morning Ritual) ---


@click.command("dp")
@click.option("-y", "--non-interactive", is_flag=True, help="Skip prompts.")
@click.pass_context
def dp_cmd(ctx, non_interactive):
    """Morning ritual — Dump, Yesterday, Tasks, Schedule."""
    config = ctx.obj.get("config")

    # --- D: Dump ---
    display_ritual_header("D · Dump", "Get everything out of your head")

    if non_interactive:
        console.print("  [dim]Skipped (non-interactive)[/dim]")
    else:
        console.print("  [dim]What's on your mind? Tasks, thoughts, anything.[/dim]")
        console.print("  [dim]Prefix with[/dim] [cyan]t[/cyan] [yellow]n[/yellow] [magenta]j[/magenta] [green]c[/green] [dim]for type. No prefix = journal.[/dim]")
        console.print("  [dim]Blank line when done.[/dim]")
        dump_count = 0
        while True:
            try:
                line = click.prompt("", prompt_suffix="  > ", default="", show_default=False)
            except (EOFError, click.Abort):
                break
            if not line.strip():
                if dump_count == 0:
                    console.print("  [dim]Nothing to dump — clear head. Moving on.[/dim]")
                break
            entry = process_dump_line(line, config, auto_tags=["thisweek"])
            if entry:
                confirm_capture(entry)
                dump_count += 1

    # --- Y: Yesterday ---
    display_ritual_header("Y · Yesterday", "Unfinished from yesterday")

    yesterday = get_yesterday_unresolved(config)
    if not yesterday:
        console.print("  [dim]Nothing carried from yesterday.[/dim]")
    else:
        display_entry_list(yesterday, "")
        if not non_interactive:
            for i, entry in enumerate(yesterday, 1):
                choice = click.prompt(
                    f"  {i}. {entry.body}",
                    type=click.Choice(["k", "d", "x", "l"], case_sensitive=False),
                    prompt_suffix=" [k]eep [d]rop [x]done [l]ater > ",
                    default="k",
                    show_choices=False,
                )
                if choice == "k":
                    if "today" not in entry.tags:
                        entry.tags.append("today")
                    update_entry(entry, config)
                    display_action_confirmation(entry, "keep → today")
                elif choice == "d":
                    entry.status = TaskStatus.DROPPED
                    update_entry(entry, config)
                    display_action_confirmation(entry, "drop")
                elif choice == "x":
                    entry.status = TaskStatus.DONE
                    update_entry(entry, config)
                    display_action_confirmation(entry, "done")
                elif choice == "l":
                    if "today" in entry.tags:
                        entry.tags.remove("today")
                        update_entry(entry, config)
                    display_action_confirmation(entry, "later")


    # --- T: Task log ---
    display_ritual_header("T · Tasks", "Pick your focus for today")

    active = get_weekly_active_tasks(config)
    if not active:
        console.print("  [dim]No active tasks.[/dim]")
        if not non_interactive:
            console.print("  [dim]Capture some with[/dim] [cyan]bt t <task>[/cyan] [dim]or add them now:[/dim]")
            while True:
                try:
                    line = click.prompt("", prompt_suffix="  t > ", default="", show_default=False)
                except (EOFError, click.Abort):
                    break
                if not line.strip():
                    break
                entry = process_dump_line(f"t {line}", config, auto_tags=["thisweek"])
                if entry:
                    confirm_capture(entry)
            active = get_weekly_active_tasks(config)
    else:
        display_entry_list(active, "")
        save_state("dyts_tasks", [e.id for e in active], config)

        if non_interactive:
            console.print("  [dim]Skipped selection (non-interactive)[/dim]")
        else:
            try:
                import questionary

                choices = [
                    questionary.Choice(
                        f"{e.body}" + (" [today]" if "today" in e.tags else ""),
                        value=e.id,
                        checked="today" in e.tags,
                    )
                    for e in active
                ]
                selected = questionary.checkbox(
                    "Select tasks for today:", choices=choices
                ).ask()
                if selected is not None:
                    from bute.storage import entry_path_from_id, load_entry

                    # Tag newly selected, untag deselected
                    selected_set = set(selected)
                    for e in active:
                        path = entry_path_from_id(e.id, config)
                        if not path:
                            continue
                        entry = load_entry(path)
                        if e.id in selected_set and "today" not in entry.tags:
                            entry.tags.append("today")
                            update_entry(entry, config)
                        elif e.id not in selected_set and "today" in entry.tags:
                            entry.tags.remove("today")
                            update_entry(entry, config)
                    console.print(f"  [green]{len(selected)} tasks tagged for today[/green]")
            except ImportError:
                console.print("  [dim]questionary not available — skipping selection[/dim]")

    # --- S: Schedule ---
    display_ritual_header("S · Schedule", "Today's events")

    schedule = get_today_schedule(config)
    if not schedule:
        console.print("  [dim]Nothing scheduled today.[/dim]")
    else:
        display_entry_list(schedule, "")
        if not non_interactive:
            # Let user pick which events to tag for today's log
            for i, entry in enumerate(schedule, 1):
                if "today" not in entry.tags:
                    choice = click.prompt(
                        f"  {i}. {entry.body}",
                        type=click.Choice(["y", "n"], case_sensitive=False),
                        prompt_suffix=" include in today's log? [y]es [n]o > ",
                        default="y",
                        show_choices=False,
                    )
                    if choice == "y":
                        entry.tags.append("today")
                        update_entry(entry, config)

    if not non_interactive:
        console.print("  [dim]Any new events? Blank to skip.[/dim]")
        while True:
            try:
                line = click.prompt("", prompt_suffix="  c > ", default="", show_default=False)
            except (EOFError, click.Abort):
                break
            if not line.strip():
                break
            entry = process_dump_line(f"c {line}", config)
            if entry:
                confirm_capture(entry)

    # --- H: Habits ---
    configured = []
    if config and "habits" in config and "list" in config["habits"]:
        configured = list(config["habits"]["list"])

    if configured:
        display_ritual_header("H · Habits", "Check in on your habits")

        from bute.habit_storage import get_habit_summary, save_habit

        habits = get_habit_summary(date.today(), configured, config)

        if non_interactive:
            from bute.display import display_habit_line
            display_habit_line(habits, configured)
        else:
            for name in configured:
                status = habits.get(name)
                if status is True:
                    console.print(f"  [green]●[/green] {name} [dim](done)[/dim]")
                    continue

                choice = click.prompt(
                    f"  ○ {name}",
                    type=click.Choice(["y", "s"], case_sensitive=False),
                    prompt_suffix=" [y]es [s]kip > ",
                    default="s",
                    show_choices=False,
                )
                if choice == "y":
                    save_habit(name, True, date.today(), config)
                    console.print(f"  [green]●[/green] {name}")

    from bute.state import mark_dyts_done
    mark_dyts_done(config)

    console.print(f"\n  [bold green]Ready. Go.[/bold green]")


# --- Line Log ---


def _build_month_data(target: date, config) -> dict[int, list[str]]:
    """Build a month's linelog data — dict of day_num → list of entry strings."""
    import calendar

    from bute.parser import format_time_display

    from bute.models import EntryType
    from bute.storage import load_entries_by_date, query_and_load

    _, last_day = calendar.monthrange(target.year, target.month)
    today = date.today()

    lines_by_day: dict[int, list[str]] = {}

    # Journal + calendar entries created on each day of the month
    for day_num in range(1, last_day + 1):
        d = date(target.year, target.month, day_num)
        if d > today:
            break
        entries = load_entries_by_date(d, config)
        for e in entries:
            if e.type == EntryType.JOURNAL:
                lines_by_day.setdefault(day_num, []).append(f"[magenta]=[/magenta] {e.body}")
            elif e.type == EntryType.CALENDAR:
                # Calendar events appear on their scheduled date, or creation date if no date set
                event_day = e.scheduled_date.day if e.scheduled_date else day_num
                if e.scheduled_date and (e.scheduled_date.year != target.year or e.scheduled_date.month != target.month):
                    continue  # scheduled for a different month
                time_str = f" {format_time_display(e.scheduled_time)}" if e.scheduled_time else ""
                lines_by_day.setdefault(event_day, []).append(f"[green]o[/green][dim]{time_str}[/dim] {e.body}")

    # Calendar events scheduled in this month but created in a different month
    from bute.storage import query_and_load
    scheduled_events = query_and_load(config, type="calendar")
    scheduled_events = [
        e for e in scheduled_events
        if (e.scheduled_date is not None
            and e.scheduled_date.year == target.year
            and e.scheduled_date.month == target.month
            and e.created.strftime("%Y-%m") != target.strftime("%Y-%m"))
    ]
    for e in scheduled_events:
        day_num = e.scheduled_date.day
        time_str = f" {format_time_display(e.scheduled_time)}" if e.scheduled_time else ""
        lines_by_day.setdefault(day_num, []).append(f"[green]o[/green][dim]{time_str}[/dim] {e.body}")

    return lines_by_day


def _render_month_table(target: date, lines_by_day: dict[int, list[str]], title: str | None = None) -> "Table":
    """Render a month's linelog as a Rich Table."""
    from rich.table import Table
    from rich.text import Text

    WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    table = Table(
        title=title or f"Line Log — {target.strftime('%B %Y')}",
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Day", style="bold", width=3, justify="right")
    table.add_column("", width=3)  # weekday
    table.add_column("Entry", ratio=1, overflow="fold")

    for day_num in sorted(lines_by_day):
        d = date(target.year, target.month, day_num)
        weekday = WEEKDAYS[d.weekday()]
        entries_text = "\n".join(lines_by_day[day_num])
        table.add_row(str(day_num), f"[dim]{weekday}[/dim]", entries_text)
        table.add_section()

    return table


@click.command("dump")
@click.pass_context
def dump_cmd(ctx):
    """Rapid-fire task capture into the backlog."""
    config = ctx.obj.get("config")

    display_ritual_header("Dump", "Get it out of your head — tasks go to Task Log")
    console.print("  [dim]Enter tasks, one per line. Add[/dim] [bold]@today[/bold] [dim]or[/dim] [bold]@thisweek[/bold] [dim]to pull into focus.[/dim]")
    console.print("  [dim]Blank line when done.[/dim]")

    count = 0
    while True:
        try:
            line = click.prompt("", prompt_suffix="  > ", default="", show_default=False)
        except (EOFError, click.Abort):
            break
        if not line.strip():
            break
        # Force task signifier — prepend t if no signifier given
        tokens = line.strip().split()
        first = tokens[0]
        from bute.parser import BULLET_RE, SIGNIFIER_RE, WORD_SIGNIFIER_RE
        if not (SIGNIFIER_RE.match(first) or BULLET_RE.match(first) or WORD_SIGNIFIER_RE.match(first)):
            line = "t " + line
        entry = process_dump_line(line, config, auto_tags=None)
        if entry:
            confirm_capture(entry)
            count += 1

    if count == 0:
        console.print("  [dim]Nothing to dump — clear head.[/dim]")
    else:
        console.print(f"\n  [bold]{count}[/bold] [dim]task{'s' if count != 1 else ''} captured to Task Log.[/dim]")


@click.command("linelog")
@click.argument("period", required=False, default=None)
@click.pass_context
def linelog_cmd(ctx, period):
    """Show the line log. No args = this month. YYYY-MM = month. YYYY = full year."""
    config = ctx.obj.get("config")

    if period and len(period) == 4 and period.isdigit():
        # Year mode — show all months
        year = int(period)
        found_any = False
        for m in range(1, 13):
            target = date(year, m, 1)
            data = _build_month_data(target, config)
            if data:
                if not found_any:
                    console.print()
                found_any = True
                table = _render_month_table(target, data, title=f"Line Log — {target.strftime('%B %Y')}")
                console.print(table)
                console.print()
        if not found_any:
            console.print(f"  [dim]No line log entries for {year}.[/dim]")
    else:
        if period:
            try:
                target = date.fromisoformat(f"{period}-01")
            except ValueError:
                console.print(f"  [red]Invalid format. Use YYYY-MM or YYYY.[/red]")
                return
        else:
            target = date.today()

        data = _build_month_data(target, config)
        if not data:
            console.print(f"  [dim]No line log entries for {target.strftime('%B %Y')}.[/dim]")
            return

        console.print()
        table = _render_month_table(target, data)
        console.print(table)
        console.print()


# --- Weekly Plan ---


@click.command("wp")
@click.option("-y", "--non-interactive", is_flag=True, help="Skip prompts.")
@click.pass_context
def wp_cmd(ctx, non_interactive):
    """Weekly ritual — dump tasks, then select for the week."""
    config = ctx.obj.get("config")

    display_ritual_header("Plan", "Review your task log and select for this week")

    active = get_all_active_tasks(config)

    # Show current task log
    if active:
        display_entry_list(active, "Task Log")
    else:
        console.print("  [dim]Task log is empty.[/dim]")

    # Dump phase — add new tasks
    if not non_interactive:
        console.print("\n  [dim]Add tasks? One per line, blank when done.[/dim]")
        added = 0
        while True:
            try:
                line = click.prompt("", prompt_suffix="  > ", default="", show_default=False)
            except (EOFError, click.Abort):
                break
            if not line.strip():
                break
            entry = process_dump_line(f"t {line}", config, auto_tags=["thisweek"])
            if entry:
                confirm_capture(entry)
                added += 1
        if added:
            console.print(f"  [green]{added} tasks added.[/green]")
            # Reload with new tasks
            active = get_all_active_tasks(config)

    if not active:
        console.print("  [dim]No tasks to plan. Capture some first.[/dim]")
        return

    if non_interactive:
        thisweek = [e for e in active if "thisweek" in e.tags]
        if thisweek:
            display_entry_list(thisweek, "This week's tasks")
        else:
            display_entry_list(active, "Task Log (none selected for week)")
        return

    # Selection phase
    try:
        import questionary

        choices = [
            questionary.Choice(
                f"{e.body}" + (" [thisweek]" if "thisweek" in e.tags else ""),
                value=e.id,
                checked="thisweek" in e.tags,
            )
            for e in active
        ]
        selected = questionary.checkbox(
            "Select tasks for this week:", choices=choices
        ).ask()

        if selected is None:
            return  # user cancelled

        cleared = clear_weekly_selection(config)
        tagged = set_weekly_selection(selected, config)
        console.print(f"\n  [green]{tagged} tasks selected for this week[/green]")

    except ImportError:
        console.print("  [dim]questionary not available — skipping selection[/dim]")


# --- Recap (End of Day) ---


@click.command("recap")
@click.option("-q", "--quiet", is_flag=True, help="Skip AI summary.")
@click.pass_context
def recap_cmd(ctx, quiet):
    """End-of-day summary — what you did, what's carrying, AI coaching."""
    from bute.habit_storage import get_habit_summary
    from bute.ritual_ops import (
        get_tasks_done_today,
        get_tasks_dropped_today,
        get_today_captured,
    )
    from bute.state import mark_recap_done
    from bute.storage import query_and_load
    from bute.models import EntryType, TaskStatus

    config = ctx.obj.get("config")

    done = get_tasks_done_today(config)
    open_tasks = query_and_load(config, type="task", status="active", tag="today")
    dropped = get_tasks_dropped_today(config)
    captured = get_today_captured(config)

    # Check habits
    configured_habits = []
    if config and "habits" in config and "list" in config["habits"]:
        configured_habits = list(config["habits"]["list"])
    habits = get_habit_summary(date.today(), configured_habits, config) if configured_habits else {}

    has_content = done or open_tasks or dropped or captured or any(v is not None for v in habits.values())
    if not has_content:
        console.print("  [dim]Nothing to recap — quiet day.[/dim]")
        mark_recap_done(config)
        return

    console.print()
    console.print("  [bold]Recap[/bold]")
    console.print(f"  [dim]{'─' * 50}[/dim]")

    if done:
        display_entry_list(done, "Done")

    if open_tasks:
        display_entry_list(list(open_tasks), "Open")

    if dropped:
        display_entry_list(dropped, "Dropped")

    if captured:
        display_entry_list(captured, "Captured")

    if configured_habits:
        from bute.display import display_habit_line
        display_habit_line(habits, configured_habits)

    # AI coaching narrative
    if not quiet:
        from bute.ai import is_llm_available, llm_send_with_entries
        from bute.ai.prompts import recap_prompt

        if is_llm_available(config):
            all_entries = done + list(open_tasks) + dropped + captured
            if all_entries:
                console.print()
                console.print("  [dim]Thinking...[/dim]")
                response = llm_send_with_entries(
                    recap_prompt(), all_entries, "Recap my day", config
                )
                from bute.display import display_ai_response
                display_ai_response(response)

    mark_recap_done(config)
    console.print()


# --- Review (Phase 5 stub) ---


@click.command("review")
@click.argument("period", required=False, default="week")
@click.pass_context
def review_cmd(ctx, period):
    """Review a period — AI synthesizes accomplishments, sentiment, lessons."""
    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send_with_entries
    from bute.ai.prompts import review_prompt

    config = ctx.obj.get("config")

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    from datetime import timedelta

    from bute.storage import query_and_load

    today = date.today()
    if period == "day":
        start = today
    elif period == "month":
        start = today.replace(day=1)
    else:  # week
        start = today - timedelta(days=today.weekday())

    entries = query_and_load(config, created_since=start.isoformat())

    if not entries:
        console.print(f"  [dim]No entries for this {period}.[/dim]")
        return

    console.print(f"  [dim]Reviewing {len(entries)} entries...[/dim]")
    response = llm_send_with_entries(
        review_prompt(period), entries, f"Review my {period}", config
    )
    from bute.display import display_ai_response
    display_ai_response(response)
