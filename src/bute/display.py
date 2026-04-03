"""Rich terminal display for bute."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

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

    # Title: optional ! + icon + type label
    title = Text()
    title.append(" ", style=f"bold {color}")
    if entry.important:
        title.append("!", style="bold red")
    title.append(f"{style['icon']} ", style=f"bold {color}")
    title.append(style["label"], style=f"bold {color}")
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


import re

def _first_sentence(text: str) -> str:
    """Extract the first sentence from text (up to first period, !, or ?)."""
    first_line = text.split("\n", 1)[0].strip()
    m = re.search(r'[.!?]', first_line)
    if m:
        return first_line[:m.end()].strip()
    # No sentence-ending punctuation — return the full first line, capped
    if len(first_line) > 80:
        return first_line[:77] + "..."
    return first_line


def _build_entry_row(i: int, entry: Entry) -> tuple[str, Text, Text, str]:
    """Build the common columns for an entry row: (#, icon, body, meta)."""
    style = TYPE_STYLE[entry.type]

    icon = Text()
    if entry.important:
        icon.append("!", style="bold red")
    else:
        icon.append(" ")
    icon.append(style["icon"], style=style["color"])

    # List views show first sentence only — ">" signals more content follows
    preview = _first_sentence(entry.body)
    has_more = len(preview) < len(entry.body.strip())
    if has_more:
        preview = preview + " >"

    body = Text()
    if entry.status == TaskStatus.DONE:
        body.append(preview, style="strike dim")
    elif entry.status == TaskStatus.DROPPED:
        body.append(preview, style="dim")
    else:
        body.append(preview)

    meta_parts = []
    if entry.due:
        meta_parts.append(f"due:{entry.due}")
    if entry.scheduled_time:
        meta_parts.append(format_time_display(entry.scheduled_time))
    if entry.tags:
        meta_parts.extend(f"@{t}" for t in entry.tags)
    meta = " ".join(meta_parts)

    return str(i), icon, body, meta


def display_entry_list(entries: list[Entry], title: str = "") -> None:
    """Render a numbered list of entries as a Rich Table."""
    if not entries:
        console.print(f"  [dim]No entries found.[/dim]")
        return

    table = Table(
        title=title or None,
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("#", style="bold dim", width=3, justify="right")
    table.add_column("", width=2)  # type icon (e.g. .!)
    table.add_column("Entry", ratio=1, overflow="fold")
    table.add_column("Meta", style="dim")

    for i, entry in enumerate(entries, 1):
        table.add_row(*_build_entry_row(i, entry))

    console.print()
    console.print(table)


def display_entry_list_grouped(entries: list[Entry], title: str = "") -> None:
    """Render a numbered list of entries grouped by date in a single table."""
    if not entries:
        console.print(f"  [dim]No entries found.[/dim]")
        return

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

    table = Table(
        title=title or None,
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Date", style="bold", width=10)
    table.add_column("#", style="bold dim", width=3, justify="right")
    table.add_column("", width=2)  # type icon (e.g. .!)
    table.add_column("Entry", ratio=1, overflow="fold")
    table.add_column("Meta", style="dim")

    for group_idx, (date_label, items) in enumerate(grouped.items()):
        for row_idx, (i, entry) in enumerate(items):
            num, icon, body, meta = _build_entry_row(i, entry)
            date_col = date_label if row_idx == 0 else ""
            table.add_row(date_col, num, icon, body, meta)
        table.add_section()

    console.print()
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
        else:
            icon = "[dim]○[/dim]"
        console.print(f"  {icon} {name}")


def display_habit_line(
    habits: dict[str, bool | None], configured: list[str], start_num: int = 0
) -> None:
    """Display numbered habit rows below entries.

    start_num: first habit's display number (0 = unnumbered compact line).
    """
    if not configured:
        return

    console.print(f"  [dim]{'─' * 50}[/dim]")

    if start_num == 0:
        # Compact one-line (used in non-interactive/fallback)
        parts = []
        for name in configured:
            status = habits.get(name)
            if status is True:
                parts.append(f"[green]●[/green] {name}")
            else:
                parts.append(f"[dim]○[/dim] {name}")
        console.print(f"  [bold dim]Habits[/bold dim]   {'   '.join(parts)}")
    else:
        # Numbered rows (used in daily log)
        table = Table(
            show_header=False,
            show_edge=False,
            pad_edge=False,
            box=None,
            padding=(0, 1),
        )
        table.add_column("#", style="bold dim", width=4, justify="right")
        table.add_column("", width=1)
        table.add_column("", ratio=1)

        for i, name in enumerate(configured):
            status = habits.get(name)
            if status is True:
                icon = Text("●", style="green")
            else:
                icon = Text("○", style="dim")
            table.add_row(str(start_num + i), icon, name)

        console.print(table)


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
    table.add_column("", width=2)  # type icon (e.g. .!)
    table.add_column("", ratio=1)  # body
    table.add_column("", style="dim")  # relevance + tags

    for i, (entry, dist) in enumerate(zip(entries, distances), 1):
        style = TYPE_STYLE[entry.type]
        icon = Text()
        if entry.important:
            icon.append("!", style="bold red")
        else:
            icon.append(" ")
        icon.append(style["icon"], style=style["color"])

        body = Text()
        body.append(entry.body)

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


# Rotating colors for analyze tree branches
_BRANCH_COLORS = ["cyan", "green", "magenta", "blue", "red"]

# Map BuJo signifiers to their type names
_SIG_TYPES = {".": "task", "-": "note", "=": "journal", "o": "event"}

PAD = "  "  # second-level guide padding


def display_analyze_tree(tag: str, response: str) -> None:
    """Render an analysis response as a colored Rich Tree with BuJo signifiers."""
    tree = Tree(f"[bold]@{tag}[/bold]")

    # Parse THEME: blocks from the response
    themes = []
    current_theme = None
    current_items = []

    for line in response.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("THEME:"):
            if current_theme is not None:
                themes.append((current_theme, current_items))
            current_theme = stripped[6:].strip()
            current_items = []
        elif stripped and current_theme is not None:
            current_items.append(stripped)

    if current_theme is not None:
        themes.append((current_theme, current_items))

    # If parsing found no THEME: blocks, fall back to raw display
    if not themes:
        console.print(f"\n{response}")
        return

    # Count total entries (excluding tensions)
    total = sum(len(items) for name, items in themes if "tension" not in name.lower() and "gap" not in name.lower())

    console.print()
    console.print(f"  [bold]@{tag}[/bold] — {total} entries across {len(themes)} themes")

    for i, (theme_name, items) in enumerate(themes):
        is_tensions = "tension" in theme_name.lower() or "gap" in theme_name.lower()
        is_complete = "[complete]" in theme_name.lower() or "[done]" in theme_name.lower()

        if is_tensions:
            color = "yellow"
        elif is_complete:
            color = "dim"
        else:
            color = _BRANCH_COLORS[i % len(_BRANCH_COLORS)]

        # Count types for summary
        type_counts = {}
        for item in items:
            sig = item[0] if item and item[0] in _SIG_TYPES else None
            if sig:
                tname = _SIG_TYPES[sig]
                type_counts[tname] = type_counts.get(tname, 0) + 1

        summary = ", ".join(f"{c} {t}{'s' if c > 1 else ''}" for t, c in type_counts.items())
        if is_complete:
            label = f"[dim]{theme_name}  {summary}[/dim]"
        elif is_tensions:
            label = f"[bold {color}]{theme_name}[/bold {color}]"
        else:
            label = f"[bold {color}]{theme_name}[/bold {color}]  [dim]{summary}[/dim]"

        branch = Tree(label, guide_style=color)

        for item in items:
            if is_complete:
                branch.add(f"[dim]{PAD}{item}[/dim]", guide_style="dim")
            else:
                branch.add(f"[{color}]{PAD}{item}[/{color}]", guide_style=color)

        console.print()
        console.print(branch)

    console.print()


def display_ai_response(text: str) -> None:
    """Render an AI response with colored section titles and formatted bullets."""
    console.print()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            console.print()
        elif stripped.startswith("- "):
            console.print(f"  [dim]  -[/dim] {stripped[2:]}")
        elif not stripped.startswith(("-", "*", "#")) and len(stripped) < 60 and not stripped.endswith("."):
            # Likely a section title — short, no punctuation, no bullet prefix
            console.print(f"  [bold cyan]{stripped}[/bold cyan]")
        else:
            console.print(f"  {stripped}")
    console.print()
