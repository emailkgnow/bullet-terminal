"""Rich terminal display for bute."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bute.models import Entry, EntryType, TaskStatus
from bute.parser import format_time_display

console = Console()

# Type-to-style mapping
TYPE_STYLE = {
    EntryType.TASK:     {"icon": ".", "color": "cyan",    "label": "task"},
    EntryType.NOTE:     {"icon": "-", "color": "yellow",  "label": "note"},
    EntryType.JOURNAL:  {"icon": "=", "color": "magenta", "label": "journal"},
    EntryType.CALENDAR: {"icon": "o", "color": "green",   "label": "event"},
}


def confirm_capture(entry: Entry) -> None:
    """Display a rich confirmation after an entry is captured."""
    style = TYPE_STYLE[entry.type]
    color = style["color"]

    # Title: icon + type label + optional important flag
    title = Text()
    title.append(f" {style['icon']} ", style=f"bold {color}")
    title.append(style["label"], style=f"bold {color}")
    if entry.important:
        title.append(" !", style="bold red")
    title.append(" ")

    # Body
    body = Text(entry.body)

    # Subtitle: metadata + tags
    meta_parts = []
    if entry.due:
        meta_parts.append(f"due:{entry.due}")
    if entry.scheduled_date:
        meta_parts.append(f"date:{entry.scheduled_date}")
    if entry.scheduled_time:
        meta_parts.append(format_time_display(entry.scheduled_time))
    if entry.repeat:
        meta_parts.append(f"repeat:{entry.repeat}")
    if entry.tags:
        meta_parts.append(" ".join(f"@{t}" for t in entry.tags))

    subtitle = Text(f" {' | '.join(meta_parts)} ", style="dim") if meta_parts else None

    panel = Panel(
        body,
        title=title,
        subtitle=subtitle,
        border_style=color,
        padding=(0, 1),
    )
    console.print(panel)
    console.print(f"  [dim]{entry.id[:8]}[/dim]", highlight=False)


# Status icons for task display
STATUS_ICONS = {
    TaskStatus.ACTIVE: (".", "cyan"),
    TaskStatus.DONE: ("x", "green"),
    TaskStatus.DROPPED: ("-", "dim"),
    None: (" ", "dim"),  # non-task entries have no status
}


def display_entry_list(entries: list[Entry], title: str = "") -> None:
    """Render a numbered list of entries as a Rich Table."""
    if not entries:
        console.print(f"  [dim]No entries found.[/dim]")
        return

    table = Table(
        show_header=False,
        show_edge=False,
        pad_edge=False,
        box=None,
        padding=(0, 1),
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("", width=1)  # status/icon
    table.add_column("", ratio=1)  # body
    table.add_column("", style="dim")  # tags + metadata

    for i, entry in enumerate(entries, 1):
        style = TYPE_STYLE[entry.type]
        status_icon, status_color = STATUS_ICONS.get(entry.status, (" ", "dim"))

        # Icon column: type icon colored
        icon = Text(style["icon"], style=style["color"])

        # Body column
        body = Text()
        if entry.status == TaskStatus.DONE:
            body.append(entry.body, style="strike dim")
        elif entry.status == TaskStatus.DROPPED:
            body.append(entry.body, style="dim")
        else:
            body.append(entry.body)
        if entry.important:
            body.append(" !", style="bold red")

        # Meta column: tags + due
        meta_parts = []
        if entry.due:
            meta_parts.append(f"due:{entry.due}")
        if entry.scheduled_time:
            meta_parts.append(format_time_display(entry.scheduled_time))
        if entry.tags:
            meta_parts.extend(f"@{t}" for t in entry.tags)
        meta = " ".join(meta_parts)

        table.add_row(str(i), icon, body, meta)

    if title:
        console.print(f"\n  [bold]{title}[/bold]")
    console.print(table)


def display_entry_list_grouped(entries: list[Entry], title: str = "") -> None:
    """Render a numbered list of entries grouped by date."""
    if not entries:
        console.print(f"  [dim]No entries found.[/dim]")
        return

    if title:
        console.print(f"\n  [bold]{title}[/bold]")

    # Group entries by date (calendar events use scheduled_date if set)
    from collections import OrderedDict
    grouped: OrderedDict[str, list[tuple[int, Entry]]] = OrderedDict()
    for i, entry in enumerate(entries, 1):
        if entry.scheduled_date:
            date_key = entry.scheduled_date.strftime("%a %b %d")
        else:
            date_key = entry.created.strftime("%a %b %d")
        if date_key not in grouped:
            grouped[date_key] = []
        grouped[date_key].append((i, entry))

    for date_label, items in grouped.items():
        console.print(f"\n  [bold dim]{date_label}[/bold dim]")

        table = Table(
            show_header=False,
            show_edge=False,
            pad_edge=False,
            box=None,
            padding=(0, 1),
        )
        table.add_column("#", style="bold dim", width=4, justify="right")
        table.add_column("", width=1)  # icon
        table.add_column("", ratio=1)  # body
        table.add_column("", style="dim")  # tags + metadata

        for i, entry in items:
            style = TYPE_STYLE[entry.type]
            icon = Text(style["icon"], style=style["color"])

            body = Text()
            if entry.status == TaskStatus.DONE:
                body.append(entry.body, style="strike dim")
            elif entry.status == TaskStatus.DROPPED:
                body.append(entry.body, style="dim")
            else:
                body.append(entry.body)
            if entry.important:
                body.append(" !", style="bold red")

            meta_parts = []
            if entry.due:
                meta_parts.append(f"due:{entry.due}")
            if entry.scheduled_time:
                meta_parts.append(format_time_display(entry.scheduled_time))
            if entry.tags:
                meta_parts.extend(f"@{t}" for t in entry.tags)
            meta = " ".join(meta_parts)

            table.add_row(str(i), icon, body, meta)

        console.print(table)


def display_action_confirmation(entry: Entry, action: str) -> None:
    """Short one-line confirmation after an action."""
    style = TYPE_STYLE[entry.type]
    icon = style["icon"]
    color = style["color"]
    short_id = entry.id[:8]
    console.print(
        f"  [{color}]{icon}[/{color}] [bold]\\[{action}][/bold] "
        f"{entry.body} [dim]({short_id})[/dim]"
    )


def display_ritual_header(phase: str, description: str) -> None:
    """Display a ritual phase header."""
    console.print(f"\n  [bold cyan]{phase}[/bold cyan] [dim]{description}[/dim]")
    console.print(f"  [dim]{'─' * 50}[/dim]")


def display_habit_status(
    habits: dict[str, bool | None], configured: list[str]
) -> None:
    """Display today's habit status."""
    if not configured:
        console.print("  [dim]No habits configured.[/dim]")
        return

    for name in configured:
        status = habits.get(name)
        if status is True:
            icon = "[green]●[/green]"
        elif status is False:
            icon = "[red].[/red]"
        else:
            icon = "[dim]○[/dim]"
        console.print(f"  {icon} {name}")


def display_search_results(
    entries: list[Entry], distances: list[float], query: str = ""
) -> None:
    """Render search results with relevance scores."""
    if not entries:
        console.print("  [dim]No results found.[/dim]")
        return

    table = Table(
        show_header=False,
        show_edge=False,
        pad_edge=False,
        box=None,
        padding=(0, 1),
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("", width=1)  # type icon
    table.add_column("", ratio=1)  # body
    table.add_column("", style="dim")  # relevance + tags

    for i, (entry, dist) in enumerate(zip(entries, distances), 1):
        style = TYPE_STYLE[entry.type]
        icon = Text(style["icon"], style=style["color"])

        body = Text()
        body.append(entry.body)
        if entry.important:
            body.append(" !", style="bold red")

        # Relevance: lower distance = more similar
        relevance = max(0, 100 - int(dist * 50))
        meta_parts = [f"{relevance}%"]
        if entry.tags:
            meta_parts.extend(f"@{t}" for t in entry.tags)
        meta = " ".join(meta_parts)

        table.add_row(str(i), icon, body, meta)

    title = f'Search: "{query}"' if query else "Similar entries"
    console.print(f"\n  [bold]{title}[/bold]")
    console.print(table)
