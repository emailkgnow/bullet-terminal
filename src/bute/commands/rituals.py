"""Ritual commands for bute (dp/dailyplan, wp/weeklyplan, recap)."""

from datetime import date

import click
from rich.console import Console

from bute.display import (
    confirm_capture,
    display_entry_list,
    display_ritual_header,
)
from bute.ritual_ops import (
    clear_weekly_selection,
    get_all_active_tasks,
    get_weekly_active_tasks,
    get_yesterday_unresolved,
    process_dump_line,
    set_weekly_selection,
)
from bute.storage import update_entry

console = Console()


# --- Daily Plan (Morning Ritual) ---


@click.command("dp")
@click.option("-y", "--non-interactive", is_flag=True, help="Skip prompts.")
@click.pass_context
def dp_cmd(ctx, non_interactive):
    """Morning ritual — pick today's tasks from weekly focus."""
    config = ctx.obj.get("config")

    display_ritual_header("Daily Plan", "Pick your focus for today")

    # 1. Gather yesterday's unresolved tasks
    yesterday = get_yesterday_unresolved(config)
    yesterday_ids = {e.id for e in yesterday}

    # 2. Gather weekly/backlog pool (excluding yesterday dupes)
    pool = get_weekly_active_tasks(config)
    pool = [e for e in pool if e.id not in yesterday_ids]

    all_tasks = yesterday + pool

    if not all_tasks:
        console.print("  [dim]No active tasks.[/dim]")
    else:
        if non_interactive:
            display_entry_list(all_tasks, "")
        else:
            try:
                import questionary

                choices = []
                for e in yesterday:
                    label = f"\u21a9 {e.body}"
                    choices.append(questionary.Choice(
                        label, value=e.id, checked="today" in e.tags,
                    ))
                for e in pool:
                    choices.append(questionary.Choice(
                        e.body, value=e.id, checked="today" in e.tags,
                    ))

                selected = questionary.checkbox(
                    "Select tasks for today:", choices=choices
                ).ask()

                if selected is not None:
                    from bute.storage import entry_path_from_id, load_entry

                    selected_set = set(selected)
                    for e in all_tasks:
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
                display_entry_list(all_tasks, "")

    from bute.state import mark_dp_done
    mark_dp_done(config)

    console.print(f"\n  [bold green]Ready. Go.[/bold green]")


# --- Monthly Log ---


def _build_month_data(target: date, config) -> dict[int, list[str]]:
    """Build a month's log data — dict of day_num → list of entry strings."""
    import calendar

    from bute.display import _preview
    from bute.parser import format_time_display

    from bute.models import EntryType
    from bute.storage import load_entries_by_date, query_and_load

    _, last_day = calendar.monthrange(target.year, target.month)
    today = date.today()

    lines_by_day: dict[int, list[str]] = {}

    # Journal, note, and calendar entries created on each day of the month
    for day_num in range(1, last_day + 1):
        d = date(target.year, target.month, day_num)
        if d > today:
            break
        entries = load_entries_by_date(d, config)
        for e in entries:
            if e.type == EntryType.TASK:
                from bute.models import TaskStatus
                preview = _preview(e.body)
                if e.status == TaskStatus.DONE:
                    lines_by_day.setdefault(day_num, []).append(f"[strike dim][cyan].[/cyan] {preview}[/strike dim]")
                elif e.status == TaskStatus.DROPPED:
                    lines_by_day.setdefault(day_num, []).append(f"[dim][cyan].[/cyan] {preview}[/dim]")
                else:
                    lines_by_day.setdefault(day_num, []).append(f"[cyan].[/cyan] {preview}")
            elif e.type == EntryType.JOURNAL:
                lines_by_day.setdefault(day_num, []).append(f"[magenta]=[/magenta] {_preview(e.body)}")
            elif e.type == EntryType.NOTE:
                lines_by_day.setdefault(day_num, []).append(f"[yellow]-[/yellow] {_preview(e.body)}")
            elif e.type == EntryType.CALENDAR:
                # Calendar events appear on their scheduled date, or creation date if no date set
                event_day = e.scheduled_date.day if e.scheduled_date else day_num
                if e.scheduled_date and (e.scheduled_date.year != target.year or e.scheduled_date.month != target.month):
                    continue  # scheduled for a different month
                time_str = f" {format_time_display(e.scheduled_time)}" if e.scheduled_time else ""
                lines_by_day.setdefault(event_day, []).append(f"[green]o[/green][dim]{time_str}[/dim] {_preview(e.body)}")

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
        lines_by_day.setdefault(day_num, []).append(f"[green]o[/green][dim]{time_str}[/dim] {_preview(e.body)}")

    return lines_by_day


def _render_month_table(target: date, lines_by_day: dict[int, list[str]], title: str | None = None) -> "Table":
    """Render a month's linelog as a Rich Table."""
    from rich.table import Table
    from rich.text import Text

    WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    table = Table(
        title=title or f"Monthly Log — {target.strftime('%B %Y')}",
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

    display_ritual_header("Dump", "Get it out of your head — tasks go to Backlog")
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
        console.print(f"\n  [bold]{count}[/bold] [dim]task{'s' if count != 1 else ''} captured to Backlog.[/dim]")


@click.command("monthly")
@click.argument("period", required=False, default=None)
@click.pass_context
def monthly_cmd(ctx, period):
    """Monthly log. No args = this month. 'bt m jan', YYYY-MM, or YYYY."""
    config = ctx.obj.get("config")

    MONTH_NAMES = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }

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
                table = _render_month_table(target, data, title=f"Monthly Log — {target.strftime('%B %Y')}")
                console.print(table)
                console.print()
        if not found_any:
            console.print(f"  [dim]No entries for {year}.[/dim]")
    else:
        if period:
            # Try month name first (jan, february, etc.)
            month_num = MONTH_NAMES.get(period.lower())
            if month_num:
                target = date(date.today().year, month_num, 1)
            else:
                try:
                    target = date.fromisoformat(f"{period}-01")
                except ValueError:
                    console.print(f"  [red]Invalid period: {period}. Use month name (jan), YYYY-MM, or YYYY.[/red]")
                    return
        else:
            target = date.today()

        data = _build_month_data(target, config)
        if not data:
            console.print(f"  [dim]No entries for {target.strftime('%B %Y')}.[/dim]")
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

    display_ritual_header("Plan", "Review your backlog and select for this week")

    active = get_all_active_tasks(config)

    # Show current task log
    if active:
        display_entry_list(active, "Task Backlog")
    else:
        console.print("  [dim]Backlog is empty.[/dim]")

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
        from bute.state import mark_wp_done
        mark_wp_done(config)
        return

    if non_interactive:
        thisweek = [e for e in active if "thisweek" in e.tags]
        if thisweek:
            display_entry_list(thisweek, "This week's tasks")
        else:
            display_entry_list(active, "Task Backlog (none selected for week)")
        from bute.state import mark_wp_done
        mark_wp_done(config)
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

    from bute.state import mark_wp_done
    mark_wp_done(config)


# --- Recap ---


@click.command("recap")
@click.argument("period", required=True)
@click.pass_context
def recap_cmd(ctx, period):
    """AI analysis of a period (day, week, month, year). Use 'bt d' for daily log."""
    config = ctx.obj.get("config")
    _recap_period(period, config)


def _recap_daily(config):
    """Show today's structured recap: done, open, dropped, captured, habits."""
    from bute.commands.habits import _get_habit_entries
    from bute.ritual_ops import (
        get_tasks_done_today,
        get_tasks_dropped_today,
        get_today_captured,
    )
    from bute.state import mark_recap_done
    from bute.storage import query_and_load

    done = get_tasks_done_today(config)
    open_tasks = query_and_load(config, type="task", status="active", tag="today")
    dropped = get_tasks_dropped_today(config)
    captured = get_today_captured(config)

    habit_entries = _get_habit_entries(config)
    today = date.today()

    has_content = done or open_tasks or dropped or captured or habit_entries
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

    if habit_entries:
        from bute.display import display_habit_line_entries
        display_habit_line_entries(habit_entries, today)

    mark_recap_done(config)
    console.print()


def _recap_period(period: str, config):
    """AI-analyze all entries for the given period."""
    from datetime import timedelta

    today = date.today()
    if period == "day":
        start = today
        label = "today"
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        label = "this-week"
    elif period == "month":
        start = today.replace(day=1)
        label = "this-month"
    elif period == "year":
        start = today.replace(month=1, day=1)
        label = "this-year"
    else:
        console.print(f"  [red]Unknown period: {period}. Use day, week, month, or year.[/red]")
        return

    from bute.ai import _LLM_INSTALL_MSG, is_llm_available
    from bute.commands.tags import _run_analyze
    from bute.storage import query_and_load

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    entries = query_and_load(config, created_since=start.isoformat())

    if not entries:
        console.print(f"  [dim]No entries for {label.replace('-', ' ')}.[/dim]")
        return

    _run_analyze("", entries, config, label=label)
