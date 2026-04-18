"""Ritual commands for bute (dp/dailyplan, wp/weeklyplan)."""

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

                today = date.today()
                choices = []
                for e in yesterday:
                    label = f"\u21a9 {e.body}"
                    choices.append(questionary.Choice(
                        label, value=e.id, checked=e.focus_date == today,
                    ))
                for e in pool:
                    choices.append(questionary.Choice(
                        e.body, value=e.id, checked=e.focus_date == today,
                    ))

                selected = questionary.checkbox(
                    "Select tasks for today:", choices=choices
                ).ask()

                if selected is not None:
                    from bute.storage import entry_path_from_id, load_entry

                    today = date.today()
                    selected_set = set(selected)
                    for e in all_tasks:
                        path = entry_path_from_id(e.id, config)
                        if not path:
                            continue
                        entry = load_entry(path)
                        if e.id in selected_set and entry.focus_date != today:
                            entry.focus_date = today
                            update_entry(entry, config)
                        elif e.id not in selected_set and entry.focus_date is not None:
                            entry.focus_date = None
                            update_entry(entry, config)
                    console.print(f"  [green]{len(selected)} tasks tagged for today[/green]")
            except ImportError:
                console.print("  [dim]questionary not available — skipping selection[/dim]")
                display_entry_list(all_tasks, "")

    from bute.state import mark_dp_done
    mark_dp_done(config)

    console.print(f"\n  [bold green]Ready. Go.[/bold green]")


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
        from bute.parser import SIGNIFIER_RE, WORD_SIGNIFIER_RE
        if not (SIGNIFIER_RE.match(first) or WORD_SIGNIFIER_RE.match(first)):
            line = "t " + line
        entry = process_dump_line(line, config, auto_tags=None)
        if entry:
            confirm_capture(entry)
            count += 1

    if count == 0:
        console.print("  [dim]Nothing to dump — clear head.[/dim]")
    else:
        console.print(f"\n  [bold]{count}[/bold] [dim]task{'s' if count != 1 else ''} captured to Backlog.[/dim]")


# --- Weekly Plan ---


@click.command("wp")
@click.option("-y", "--non-interactive", is_flag=True, help="Skip prompts.")
@click.pass_context
def wp_cmd(ctx, non_interactive):
    """Weekly ritual — dump tasks, then select for the week."""
    config = ctx.obj.get("config")

    display_ritual_header("Plan", "Review your backlog and select for this week")

    # Separate carryover (tasks with week_date set) from fresh backlog
    active = get_all_active_tasks(config)
    carryover = [e for e in active if e.week_date is not None]
    carryover_ids = {e.id for e in carryover}
    backlog = [e for e in active if e.id not in carryover_ids]

    all_tasks = carryover + backlog

    if not all_tasks and not non_interactive:
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
            entry = process_dump_line(f"t {line}", config)
            if entry:
                confirm_capture(entry)
                added += 1
        if added:
            console.print(f"  [green]{added} tasks added.[/green]")
            # Reload with new tasks
            active = get_all_active_tasks(config)
            carryover = [e for e in active if e.week_date is not None]
            carryover_ids = {e.id for e in carryover}
            backlog = [e for e in active if e.id not in carryover_ids]
            all_tasks = carryover + backlog

    if not all_tasks:
        console.print("  [dim]No tasks to plan. Capture some first.[/dim]")
        from bute.state import mark_wp_done
        mark_wp_done(config)
        return

    if non_interactive:
        if carryover:
            display_entry_list(carryover, "This week's tasks")
        if backlog:
            display_entry_list(backlog, "Backlog")
        if not carryover and not backlog:
            console.print("  [dim]No tasks.[/dim]")
        from bute.state import mark_wp_done
        mark_wp_done(config)
        return

    # Selection phase
    try:
        import questionary

        choices = []
        for e in carryover:
            label = f"\u21a9 {e.body}"
            choices.append(questionary.Choice(
                label, value=e.id, checked=True,
            ))
        for e in backlog:
            choices.append(questionary.Choice(
                e.body, value=e.id, checked=False,
            ))

        selected = questionary.checkbox(
            "Select tasks for this week:", choices=choices
        ).ask()

        if selected is None:
            from bute.state import mark_wp_done
            mark_wp_done(config)
            return  # user cancelled

        cleared = clear_weekly_selection(config)
        tagged = set_weekly_selection(selected, config)
        console.print(f"\n  [green]{tagged} tasks selected for this week[/green]")

    except ImportError:
        console.print("  [dim]questionary not available — skipping selection[/dim]")

    from bute.state import mark_wp_done
    mark_wp_done(config)
