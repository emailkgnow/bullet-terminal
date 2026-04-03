"""Interactive AI chat sessions anchored to bt entries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bute.display import TYPE_STYLE

if TYPE_CHECKING:
    from bute.models import Entry

console = Console()


@dataclass
class ChatSession:
    """Holds state for an interactive chat session."""

    anchor: Entry
    config: dict
    context_entries: list[Entry] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)
    last_bt_results: list[Entry] = field(default_factory=list)

    @classmethod
    def start(cls, entry: Entry, config: dict) -> ChatSession:
        """Create a new chat session anchored to an entry."""
        from bute.ai.prompts import chat_prompt, format_entries

        session = cls(
            anchor=entry,
            config=config,
            context_entries=[entry],
            messages=[
                {"role": "system", "content": chat_prompt()},
                {
                    "role": "user",
                    "content": (
                        f"I want to think through this entry:\n\n"
                        f"{format_entries([entry])}\n\n"
                        f"Help me process it."
                    ),
                },
            ],
            proposals=[],
            last_bt_results=[],
        )
        return session

    def add_to_context(self, entries: list[Entry]) -> None:
        """Add entries to the chat context (skips duplicates)."""
        from bute.ai.prompts import format_entries

        existing_ids = {e.id for e in self.context_entries}
        new_entries = [e for e in entries if e.id not in existing_ids]
        if not new_entries:
            return
        self.context_entries.extend(new_entries)
        self.messages.append({
            "role": "user",
            "content": f"[Added to context]\n{format_entries(new_entries)}",
        })

    def add_user_message(self, text: str) -> None:
        """Add a user message to the history."""
        self.messages.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str) -> None:
        """Add an assistant response to the history."""
        self.messages.append({"role": "assistant", "content": text})


_BT_BLOCK_RE = re.compile(r"```bt\s*\n(.*?)```", re.DOTALL)

_SIGNIFIER_TO_TYPE = {".": "task", "-": "note", "=": "journal", "o": "calendar"}


def parse_proposals(response_text: str) -> list[dict]:
    """Extract proposed entries from ```bt code blocks in AI response.

    Returns list of dicts with keys: type, important, body, tags, metadata.
    """
    proposals = []
    for match in _BT_BLOCK_RE.finditer(response_text):
        block = match.group(1)
        for line in block.strip().splitlines():
            parsed = _parse_proposal_line(line.strip())
            if parsed:
                proposals.append(parsed)
    return proposals


def _parse_proposal_line(line: str) -> dict | None:
    """Parse a single proposal line like '. task text @tag due:date'."""
    if not line:
        return None

    tokens = line.split()
    if not tokens:
        return None

    first = tokens[0]
    signifier = first.rstrip("!")
    important = first.endswith("!") and len(first) > 1

    if signifier not in _SIGNIFIER_TO_TYPE:
        return None

    entry_type = _SIGNIFIER_TO_TYPE[signifier]

    body_parts = []
    tags = []
    metadata = {}

    for token in tokens[1:]:
        if re.match(r"^@[a-zA-Z0-9_-]+$", token):
            tags.append(token[1:])
        elif ":" in token and not token.startswith(":") and token.split(":")[0] in ("due", "d", "t"):
            key, value = token.split(":", 1)
            metadata[key] = value
        else:
            body_parts.append(token)

    if not body_parts:
        return None

    return {
        "type": entry_type,
        "important": important,
        "body": " ".join(body_parts),
        "tags": tags,
        "metadata": metadata,
    }


def execute_bt_view(args: list[str], config) -> list:
    """Execute a bt view command within chat and return matching entries."""
    from bute.storage import query_and_load

    if not args:
        return []

    first = args[0]

    sig_to_query = {
        "t": {"type": "task", "status": "active"},
        "n": {"type": "note"},
        "j": {"type": "journal"},
        "c": {"type": "calendar"},
    }

    # Signifier views: t, n, j, c (with optional @tag)
    if first in sig_to_query:
        kwargs = dict(sig_to_query[first])
        for arg in args[1:]:
            if arg.startswith("@") and len(arg) > 1:
                kwargs["tag"] = arg[1:]
        return query_and_load(config, **kwargs)

    # Important + type: t!, n!, etc.
    stripped = first.rstrip("!")
    if first.endswith("!") and stripped in sig_to_query:
        kwargs = dict(sig_to_query[stripped])
        kwargs["important"] = True
        return query_and_load(config, **kwargs)

    # Tag filter: @tagname
    if first.startswith("@") and len(first) > 1:
        return query_and_load(config, tag=first[1:])

    # Important filter: !
    if first == "!":
        return query_and_load(config, important=True)

    return []


def display_chat_header(session) -> None:
    """Display the chat session header with the anchor entry."""
    entry = session.anchor
    style = TYPE_STYLE[entry.type]

    parts = [entry.body]
    meta = []
    if entry.due:
        meta.append(f"due:{entry.due}")
    if entry.tags:
        meta.append(" ".join(f"@{t}" for t in entry.tags))
    if meta:
        parts.append(f"[dim]{'  '.join(meta)}[/dim]")

    icon = "!" if entry.important else ""
    title_text = f"[bold]Chat[/bold]  {icon}{style['icon']} {style['label']}"

    panel = Panel(
        "  ".join(parts),
        title=title_text,
        border_style=style["color"],
        padding=(0, 1),
    )
    console.print()
    console.print(panel)


def display_chat_context(session) -> None:
    """Show the current context entries."""
    console.print(f"\n  [bold dim]Context ({len(session.context_entries)} entries)[/bold dim]")
    for entry in session.context_entries:
        style = TYPE_STYLE[entry.type]
        bang = "!" if entry.important else " "
        tags = " ".join(f"@{t}" for t in entry.tags) if entry.tags else ""
        meta_parts = []
        if entry.due:
            meta_parts.append(f"due:{entry.due}")
        if tags:
            meta_parts.append(tags)
        meta = " ".join(meta_parts)
        console.print(
            f"  [dim]│[/dim] [{style['color']}]{bang}{style['icon']}[/{style['color']}] "
            f"{entry.body} [dim]{meta}[/dim]"
        )


def display_bt_results(entries: list, context_ids: set[str]) -> None:
    """Display bt query results with in-context markers."""
    if not entries:
        console.print("  [dim]No entries found.[/dim]")
        return

    table = Table(
        show_header=False, box=None, pad_edge=False,
        padding=(0, 1), expand=True,
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("", width=2)
    table.add_column("", ratio=1, overflow="fold")
    table.add_column("", style="dim")

    for i, entry in enumerate(entries, 1):
        style = TYPE_STYLE[entry.type]
        icon = Text()
        if entry.important:
            icon.append("!", style="bold red")
        else:
            icon.append(" ")
        icon.append(style["icon"], style=style["color"])

        body = Text(entry.body.split("\n", 1)[0].strip())

        meta_parts = []
        if entry.id in context_ids:
            meta_parts.append("← in ctx")
        if entry.due:
            meta_parts.append(f"due:{entry.due}")
        if entry.tags:
            meta_parts.extend(f"@{t}" for t in entry.tags)

        table.add_row(str(i), icon, body, " ".join(meta_parts))

    console.print()
    console.print(table)


def display_proposed_entries(proposals: list[dict]) -> None:
    """Display proposed entries for batch review."""
    sig_style = {".": "cyan", "-": "yellow", "=": "magenta", "o": "green"}
    type_to_sig = {"task": ".", "note": "-", "journal": "=", "calendar": "o"}

    table = Table(
        title="Proposed entries",
        title_style="bold",
        show_header=False, box=None, pad_edge=False,
        padding=(0, 1), expand=True,
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("", width=2)
    table.add_column("", ratio=1, overflow="fold")
    table.add_column("", style="dim")

    for i, p in enumerate(proposals, 1):
        sig = type_to_sig.get(p["type"], "?")
        color = sig_style.get(sig, "white")
        icon = Text()
        if p.get("important"):
            icon.append("!", style="bold red")
        else:
            icon.append(" ")
        icon.append(sig, style=color)

        body = Text(p["body"])

        meta_parts = []
        for key in ("due", "d", "t"):
            if key in p.get("metadata", {}):
                meta_parts.append(f"{key}:{p['metadata'][key]}")
        if p.get("tags"):
            meta_parts.extend(f"@{t}" for t in p["tags"])

        table.add_row(str(i), icon, body, " ".join(meta_parts))

    console.print()
    console.print(table)
