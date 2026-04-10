"""Stats command — bt stats momentum dashboard."""

from datetime import date, timedelta
from pathlib import Path

from rich.console import Console
from rich.text import Text

from bute.storage import entry_path, query_and_load

console = Console()


def get_done_per_day(
    config, start: date, end: date
) -> dict[date, int]:
    """Count tasks marked done per day (by file mtime) in [start, end]."""
    entries = query_and_load(config, type="task", status="done")
    counts: dict[date, int] = {}
    for entry in entries:
        path = entry_path(entry, config)
        if not path.exists():
            continue
        mtime_date = date.fromtimestamp(path.stat().st_mtime)
        if start <= mtime_date <= end:
            counts[mtime_date] = counts.get(mtime_date, 0) + 1
    return counts


def get_dropped_per_day(
    config, start: date, end: date
) -> dict[date, int]:
    """Count tasks marked dropped per day (by file mtime) in [start, end]."""
    entries = query_and_load(config, type="task", status="dropped")
    counts: dict[date, int] = {}
    for entry in entries:
        path = entry_path(entry, config)
        if not path.exists():
            continue
        mtime_date = date.fromtimestamp(path.stat().st_mtime)
        if start <= mtime_date <= end:
            counts[mtime_date] = counts.get(mtime_date, 0) + 1
    return counts


def calc_task_streak(done_per_day: dict[date, int], today: date) -> int:
    """Consecutive days with at least 1 task done, backward from today."""
    if done_per_day.get(today, 0) == 0:
        return 0
    streak = 1
    d = today - timedelta(days=1)
    while done_per_day.get(d, 0) > 0:
        streak += 1
        d -= timedelta(days=1)
    return streak


def calc_dp_streak(config, today: date) -> int:
    """Consecutive days with daily plan completed, backward from today."""
    from bute.state import get_dp_history

    history = get_dp_history(config)
    if today not in history:
        return 0
    streak = 1
    d = today - timedelta(days=1)
    while d in history:
        streak += 1
        d -= timedelta(days=1)
    return streak


_WEEKDAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"]
_BAR_CHARS = " ▁▂▃▄▅▆▇█"


def build_closure_chart(
    done_per_day: dict[date, int], days: list[date]
) -> tuple[list[str], list[str], list[str]]:
    """Build closure chart data for a list of days.

    Returns (day_labels, count_strings, bar_characters).
    """
    labels = [_WEEKDAY_LABELS[d.weekday()] for d in days]
    raw_counts = [done_per_day.get(d, 0) for d in days]
    max_count = max(raw_counts) if raw_counts else 0

    counts_row = [str(c) if c > 0 else "·" for c in raw_counts]

    bars = []
    for c in raw_counts:
        if max_count == 0 or c == 0:
            bars.append(" ")
        else:
            idx = max(1, round(c / max_count * 8))
            bars.append(_BAR_CHARS[idx])

    return labels, counts_row, bars


def get_period_ranges(
    view: str, today: date
) -> dict[str, tuple[date, date]]:
    """Compute date ranges for period comparisons.

    view: "default", "week", or "month".
    """
    # This week = Monday..today, last week = prev Mon..Sun
    monday = today - timedelta(days=today.weekday())
    last_monday = monday - timedelta(days=7)
    last_sunday = monday - timedelta(days=1)

    # This month = 1st..today, last month = full prev month
    first_of_month = today.replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    if view == "week":
        return {
            "this_week": (monday, today),
            "last_week": (last_monday, last_sunday),
        }
    elif view == "month":
        # Rolling 30-day windows
        period_start = today - timedelta(days=29)
        prev_end = period_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=29)
        return {
            "this_period": (period_start, today),
            "last_period": (prev_start, prev_end),
        }
    else:
        return {
            "this_week": (monday, today),
            "last_week": (last_monday, last_sunday),
            "this_month": (first_of_month, today),
            "last_month": (last_month_start, last_month_end),
        }


def _sum_range(per_day: dict[date, int], start: date, end: date) -> int:
    """Sum counts in a date range [start, end]."""
    return sum(v for k, v in per_day.items() if start <= k <= end)


def render_stats(view: str, config) -> None:
    """Render the full stats dashboard to the console."""
    today = date.today()
    ranges = get_period_ranges(view, today)

    # Determine chart window
    if view == "week":
        monday = today - timedelta(days=today.weekday())
        chart_days = [monday + timedelta(days=i) for i in range(7)]
        chart_label = "This week"
    elif view == "month":
        chart_days = [today - timedelta(days=29 - i) for i in range(30)]
        chart_label = "Last 30 days"
    else:
        chart_days = [today - timedelta(days=13 - i) for i in range(14)]
        chart_label = "Last 14 days"

    # Gather data — use widest date range needed
    all_dates = []
    for start, end in ranges.values():
        all_dates.extend([start, end])
    data_start = min(all_dates) if all_dates else today
    data_end = max(all_dates) if all_dates else today
    # Extend to cover chart days
    if chart_days:
        data_start = min(data_start, chart_days[0])

    done_per_day = get_done_per_day(config, data_start, data_end)
    dropped_per_day = get_dropped_per_day(config, data_start, data_end)

    task_streak = calc_task_streak(done_per_day, today)
    dp_streak = calc_dp_streak(config, today)
    labels, counts_row, bars = build_closure_chart(done_per_day, chart_days)

    # --- Render ---
    console.print()
    title = Text("── Momentum ──", style="bold")
    console.print(title, justify="center")
    console.print()

    # Streaks
    fire = "🔥" if task_streak > 0 else "  "
    plan = "📋" if dp_streak > 0 else "  "
    console.print(f"  {fire} Task Streak: [bold]{task_streak}[/bold] day{'s' if task_streak != 1 else ''}")
    console.print(f"  {plan} Plan Streak: [bold]{dp_streak}[/bold] day{'s' if dp_streak != 1 else ''}")
    console.print()

    # Chart
    console.print(f"  [dim]Daily closures ({chart_label}):[/dim]")
    label_line = "  " + "  ".join(f"{l:>2}" for l in labels)
    count_line = "  " + "  ".join(f"{c:>2}" for c in counts_row)
    bar_line = "  " + "  ".join(f"{b:>2}" for b in bars)
    console.print(f"[dim]{label_line}[/dim]")
    console.print(f"{count_line}")
    console.print(f"[cyan]{bar_line}[/cyan]")
    console.print()

    # Period comparisons
    if view == "week" or view == "default":
        tw = ranges["this_week"]
        lw = ranges["last_week"]
        tw_done = _sum_range(done_per_day, *tw)
        tw_drop = _sum_range(dropped_per_day, *tw)
        lw_done = _sum_range(done_per_day, *lw)
        lw_drop = _sum_range(dropped_per_day, *lw)
        console.print(f"  This week: [green]{tw_done}[/green] done · [dim]{tw_drop} dropped[/dim]")
        console.print(f"  Last week: [green]{lw_done}[/green] done · [dim]{lw_drop} dropped[/dim]")

    if view == "default":
        tm = ranges["this_month"]
        lm = ranges["last_month"]
        tm_done = _sum_range(done_per_day, *tm)
        tm_drop = _sum_range(dropped_per_day, *tm)
        lm_done = _sum_range(done_per_day, *lm)
        lm_drop = _sum_range(dropped_per_day, *lm)
        console.print(f"  This month: [green]{tm_done}[/green] done · [dim]{tm_drop} dropped[/dim]")
        console.print(f"  Last month: [green]{lm_done}[/green] done · [dim]{lm_drop} dropped[/dim]")

    if view == "month":
        tp = ranges["this_period"]
        lp = ranges["last_period"]
        tp_done = _sum_range(done_per_day, *tp)
        tp_drop = _sum_range(dropped_per_day, *tp)
        lp_done = _sum_range(done_per_day, *lp)
        lp_drop = _sum_range(dropped_per_day, *lp)
        console.print(f"  Last 30 days: [green]{tp_done}[/green] done · [dim]{tp_drop} dropped[/dim]")
        console.print(f"  Prior 30 days: [green]{lp_done}[/green] done · [dim]{lp_drop} dropped[/dim]")

    console.print()
