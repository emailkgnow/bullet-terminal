"""Rich terminal display for bute."""

import json as _json

import click
from rich.align import Align
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape as escape_markup
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from bute.models import Entry, EntryType, SYSTEM_TAGS, TaskStatus
from bute.parser import format_time_display

console = Console()

_JSON_MODE = False


def set_json_mode(enabled: bool) -> None:
    """Switch every list renderer to emit JSON instead of Rich tables."""
    global _JSON_MODE
    _JSON_MODE = enabled


def json_mode() -> bool:
    return _JSON_MODE


def entry_to_dict(n: int, entry: Entry, **extra) -> dict:
    """Serialize one entry for --json output. n is its 1-based display number."""
    d = {
        "n": n,
        "id": entry.id,
        "type": entry.type.value,
        "body": entry.body,
        "status": entry.status.value if entry.status else None,
        "important": entry.important,
        "due": entry.due.isoformat() if entry.due else None,
        "date": entry.scheduled_date.isoformat() if entry.scheduled_date else None,
        "time": entry.scheduled_time,
        "repeat": entry.repeat,
        "tags": list(entry.tags),
        "focus_date": entry.focus_date.isoformat() if entry.focus_date else None,
        "week_date": entry.week_date.isoformat() if entry.week_date else None,
        "created": entry.created.isoformat(),
        "extra": dict(entry.extra_meta),
    }
    d.update(extra)
    return d


def emit_json(view: str, entries: list[Entry], extra_per_entry: list[dict] | None = None) -> None:
    """Print {"view": ..., "entries": [...]} as one JSON document."""
    rows = []
    for i, entry in enumerate(entries, 1):
        extra = extra_per_entry[i - 1] if extra_per_entry else {}
        rows.append(entry_to_dict(i, entry, **extra))
    click.echo(_json.dumps({"view": view, "entries": rows}))


_MAX_WIDTH = 100
_ZEBRA_STYLE = "on #1a1a2e"  # subtle background for alternating rows

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
    meta_parts.extend(_extra_meta_parts(entry))
    visible_tags = [t for t in entry.tags if t not in SYSTEM_TAGS]
    if visible_tags:
        meta_parts.append(" ".join(f"@{t}" for t in visible_tags))

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


def _preview(text: str) -> str:
    """Topic sentence with > indicator if entry has more content."""
    preview = _first_sentence(text)
    if len(preview) < len(text.strip()):
        return preview + " >"
    return preview


def _extra_meta_parts(entry: Entry) -> list[str]:
    """Render custom key:value frontmatter as 'key:value' strings, sorted by key."""
    return [f"{k}:{v}" for k, v in sorted(entry.extra_meta.items())]


def _build_entry_row(
    i: int,
    entry: Entry,
    hide_tags: set | None = None,
    terms: list[str] | None = None,
) -> tuple[str, Text, Text, str]:
    """Build the common columns for an entry row: (#, icon, body, meta).

    When `terms` is given, every word containing a search term is colored.
    """
    style = TYPE_STYLE[entry.type]

    icon = Text()
    if entry.important:
        icon.append("!", style="bold red")
    else:
        icon.append(" ")
    icon.append(style["icon"], style=style["color"])

    preview = _preview(entry.body)

    body = Text()
    if entry.status == TaskStatus.DONE:
        body.append(preview, style="strike dim")
    elif entry.status == TaskStatus.DROPPED:
        body.append(preview, style="dim")
    else:
        body.append(preview)

    for start, end in _term_spans(preview, terms or []):
        body.stylize(_MATCH_STYLE, start, end)

    meta_parts = []
    if entry.due:
        meta_parts.append(f"due:{entry.due}")
    if entry.scheduled_time:
        meta_parts.append(format_time_display(entry.scheduled_time))
    # Escape extra_meta values to prevent Rich markup interpretation in table cells
    meta_parts.extend(escape_markup(part) for part in _extra_meta_parts(entry))
    hidden = hide_tags or set()
    visible_tags = [t for t in entry.tags if t not in SYSTEM_TAGS and t not in hidden]
    if visible_tags:
        meta_parts.append(" ".join(f"@{t}" for t in visible_tags))
    meta = " ".join(meta_parts)

    return str(i), icon, body, meta


def _display_sort_key(e: Entry) -> tuple[bool, bool]:
    """Sort key: important active → regular active → done/dropped."""
    is_resolved = e.status in (TaskStatus.DONE, TaskStatus.DROPPED)
    return (is_resolved, not e.important)


_SNIPPET_WIDTH = 72
_SNIPPET_LEAD = 24


def match_snippet(body: str, terms: list[str], width: int = _SNIPPET_WIDTH) -> str | None:
    """Return the line of `body` where a search term hit, or None.

    Returns None when the match is already visible in the title the list view
    renders — which is `_preview()`, i.e. the first *sentence*, not the whole
    first line — or when no term matches at all. Long lines are windowed around
    the match with ellipses.
    """
    terms = [t.lower() for t in terms if t]
    if not terms or not body:
        return None

    lines = body.splitlines()
    if not lines:
        return None

    title = _preview(body).lower()
    if any(t in title for t in terms):
        return None

    for line in lines:
        low = line.lower()
        hits = [low.find(t) for t in terms if t in low]
        if not hits:
            continue
        pos = min(hits)
        start = max(0, pos - _SNIPPET_LEAD)
        end = start + width
        snippet = line[start:end].strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(line):
            snippet = snippet + "…"
        return snippet

    return None


_MATCH_STYLE = "bold yellow"
_SNIPPET_MATCH_STYLE = "not dim bold yellow"

# A "word" for highlighting purposes: letters, digits, underscore, apostrophe
# and hyphen, so `find dent` lights up the whole of "dentist" and `find oauth`
# the whole of "OAuth-2".
_WORD_RE = re.compile(r"[\w'-]+")


def _term_spans(text: str, terms: list[str]) -> list[tuple[int, int]]:
    """Return merged (start, end) spans of whole words matching any of `terms`.

    A term matches a word when it appears anywhere inside it, so both `dent`
    and `ntist` select the full word "dentist".
    """
    wanted = [t.lower() for t in terms if t]
    if not wanted or not text:
        return []

    spans: list[list[int]] = []
    for m in _WORD_RE.finditer(text):
        word = m.group().lower()
        if any(t in word for t in wanted):
            spans.append([m.start(), m.end()])

    if not spans:
        return []

    merged = [spans[0]]
    for span in spans[1:]:
        if span[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], span[1])
        else:
            merged.append(span)
    return [(a, b) for a, b in merged]


def _highlight_terms(text: str, terms: list[str], style: str = _MATCH_STYLE) -> str:
    """Escape `text` for Rich and color every whole word matching `terms`."""
    spans = _term_spans(text, terms)
    if not spans:
        return escape_markup(text)

    out = []
    prev = 0
    for start, end in spans:
        out.append(escape_markup(text[prev:start]))
        out.append(f"[{style}]{escape_markup(text[start:end])}[/{style}]")
        prev = end
    out.append(escape_markup(text[prev:]))
    return "".join(out)


def display_entry_list(
    entries: list[Entry],
    title: str = "",
    hide_tags: set | None = None,
    snippets: dict[str, str] | None = None,
    terms: list[str] | None = None,
) -> None:
    """Render a numbered list of entries as a Rich Table."""
    if not entries:
        if json_mode():
            emit_json(title, [])
            return
        if title:
            console.print(f"[bold]{title}[/bold]", justify="center")
        console.print(f"  [dim]No entries found.[/dim]")
        return

    # Stable sort: important first, done/dropped last
    entries.sort(key=_display_sort_key)

    if json_mode():
        emit_json(title, entries)
        return

    table = Table(
        title=title or None,
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
        width=min(console.width, _MAX_WIDTH),
    )
    table.add_column("#", style="bold dim", width=3, justify="right")
    table.add_column("", width=2)  # type icon (e.g. .!)
    table.add_column("Entry", ratio=3, overflow="fold")
    table.add_column("Meta", style="dim", ratio=1, overflow="fold")

    for i, entry in enumerate(entries, 1):
        row_style = _ZEBRA_STYLE if i % 2 == 0 else ""
        table.add_row(
            *_build_entry_row(i, entry, hide_tags=hide_tags, terms=terms),
            style=row_style,
        )
        snippet = (snippets or {}).get(entry.id)
        if snippet:
            highlighted = _highlight_terms(snippet, terms or [], _SNIPPET_MATCH_STYLE)
            table.add_row("", "", f"[dim]{highlighted}[/dim]", "", style=row_style)

    console.print()
    console.print(Align.center(table))


def display_entry_list_grouped(entries: list[Entry], title: str = "") -> None:
    """Render a numbered list of entries grouped by date in a single table."""
    if not entries:
        if json_mode():
            emit_json(title, [])
        else:
            console.print(f"  [dim]No entries found.[/dim]")
        return

    # Group entries by date (calendar events use scheduled_date if set)
    from datetime import date as _date_type
    grouped: dict[_date_type, list[Entry]] = {}
    for entry in entries:
        if entry.scheduled_date:
            date_key = entry.scheduled_date
        else:
            date_key = entry.created.date()
        if date_key not in grouped:
            grouped[date_key] = []
        grouped[date_key].append(entry)

    # Sort groups by date descending (newest first)
    sorted_dates = sorted(grouped.keys(), reverse=True)

    # Important first, done/dropped last within each date group (stable sort)
    for items in grouped.values():
        items.sort(key=_display_sort_key)

    # Rebuild entries list in display order so caller's state matches
    entries.clear()
    for d in sorted_dates:
        entries.extend(grouped[d])

    if json_mode():
        emit_json(title, entries)
        return

    table = Table(
        title=title or None,
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        box=None,
        pad_edge=False,
        padding=(0, 1),
        width=min(console.width, _MAX_WIDTH),
    )
    table.add_column("Date", style="bold", width=10)
    table.add_column("#", style="bold dim", width=3, justify="right")
    table.add_column("", width=2)  # type icon (e.g. .!)
    table.add_column("Entry", ratio=3, overflow="fold")
    table.add_column("Meta", style="dim", ratio=1, overflow="fold")

    counter = 1
    for d in sorted_dates:
        date_label = d.strftime("%a %b %d")
        items = grouped[d]
        for row_idx, entry in enumerate(items):
            num, icon, body, meta = _build_entry_row(counter, entry)
            date_col = date_label if row_idx == 0 else ""
            row_style = _ZEBRA_STYLE if counter % 2 == 0 else ""
            table.add_row(date_col, num, icon, body, meta, style=row_style)
            counter += 1
        table.add_section()

    console.print()
    console.print(Align.center(table))


def _truncate_body(body: str, max_len: int = 60) -> str:
    """Return first sentence or line of body, truncated to max_len."""
    # Take first line
    first_line = body.split("\n", 1)[0].strip()
    # Split on sentence-ending punctuation
    for sep in (". ", "! ", "? "):
        idx = first_line.find(sep)
        if idx != -1:
            first_line = first_line[: idx + 1]
            break
    if len(first_line) > max_len:
        return first_line[: max_len - 1] + "…"
    return first_line


def display_action_confirmation(entry: Entry, action: str) -> None:
    """Short one-line confirmation after an action."""
    style = TYPE_STYLE[entry.type]
    icon = style["icon"]
    color = style["color"]
    short_id = entry.id[:8]
    body = _truncate_body(entry.body)
    console.print(
        f"  [{color}]{icon}[/{color}] [bold]\\[{action}][/bold] "
        f"{body} [dim]({short_id})[/dim]"
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


def display_habit_line_entries(
    habits: list, target_date, start_num: int = 0
) -> None:
    """Display numbered habit rows from Entry objects."""
    if not habits:
        return

    console.print(f"  [dim]{'─' * 50}[/dim]")

    if start_num == 0:
        parts = []
        for entry in habits:
            completed = entry.is_completed_for_date(target_date)
            if completed:
                parts.append(f"[green]●[/green] {entry.body}")
            else:
                parts.append(f"[dim]○[/dim] {entry.body}")
        console.print(f"  [bold dim]Habits[/bold dim]   {'   '.join(parts)}")
    else:
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

        for i, entry in enumerate(habits):
            completed = entry.is_completed_for_date(target_date)
            icon = Text("●", style="green") if completed else Text("○", style="dim")
            table.add_row(str(start_num + i), icon, entry.body)

        console.print(table)


def display_search_results(
    entries: list[Entry], distances: list[float], query: str = ""
) -> None:
    """Render search results with relevance scores."""
    if not entries:
        if json_mode():
            emit_json(f'Like: "{query}"' if query else "Like", [])
        else:
            console.print("  [dim]No results found.[/dim]")
        return
    if json_mode():
        emit_json(
            f'Like: "{query}"' if query else "Like",
            entries,
            [{"distance": d} for d in distances],
        )
        return

    table = Table(
        show_header=False,
        show_edge=False,
        pad_edge=False,
        box=None,
        padding=(0, 1),
        width=min(console.width, _MAX_WIDTH),
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("", width=2)  # type icon
    table.add_column("", ratio=3)  # body
    table.add_column("", style="dim", ratio=1, overflow="fold")  # meta

    for i, entry in enumerate(entries, 1):
        num, icon, body, meta = _build_entry_row(i, entry)
        row_style = _ZEBRA_STYLE if i % 2 == 0 else ""
        table.add_row(num, icon, body, meta, style=row_style)

    title = f'Like: "{query}"' if query else "Like"
    console.print(f"\n  [bold]{title}[/bold]")
    console.print(Align.center(table))


def display_entry_full(entry: Entry) -> None:
    """Render an entry's body as formatted markdown with a clean header.

    Used by `bt <n> show` — strips frontmatter symbols and renders the body
    via Rich's Markdown (headings, bold, lists, code blocks, rules).
    """
    style = TYPE_STYLE[entry.type]
    color = style["color"]

    header = Text()
    header.append("  ")
    if entry.important:
        header.append("! ", style="bold red")
    header.append(style["icon"], style=f"bold {color}")
    header.append(f"  {style['label']}", style=f"bold {color}")
    if entry.status == TaskStatus.DONE:
        header.append("  · done", style="green")
    elif entry.status == TaskStatus.DROPPED:
        header.append("  · dropped", style="dim")

    meta_parts = []
    if entry.due:
        meta_parts.append(f"due {entry.due}")
    if entry.scheduled_date:
        meta_parts.append(f"on {entry.scheduled_date}")
    if entry.scheduled_time:
        meta_parts.append(format_time_display(entry.scheduled_time))
    if entry.repeat:
        meta_parts.append(f"repeat {entry.repeat}")
    # Escape extra_meta values to prevent Rich markup interpretation when printed
    meta_parts.extend(escape_markup(part) for part in _extra_meta_parts(entry))
    visible_tags = [t for t in entry.tags if t not in SYSTEM_TAGS]
    if visible_tags:
        meta_parts.append(" ".join(f"@{t}" for t in visible_tags))
    meta_parts.append(entry.id[:8])

    console.print()
    console.print(header)
    console.print(f"  [dim]{' · '.join(meta_parts)}[/dim]")
    console.print(Rule(style="dim"))
    console.print()
    console.print(Markdown(entry.body))
    console.print()

