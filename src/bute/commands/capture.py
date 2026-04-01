"""Capture command — handles t/n/j/c and task/note/journal/cal signifier input."""

import click

from bute.display import confirm_capture
from bute.models import SIGNIFIER_MAP, Entry, EntryType
from bute.parser import (
    BULLET_RE,
    SIGNIFIER_RE,
    WORD_SIGNIFIER_RE,
    parse_capture_tokens,
    resolve_date,
    resolve_time,
)
from bute.storage import save_entry


@click.command("capture", hidden=True)
@click.option("--later", "-l", is_flag=True, help="Skip @thisweek — backlog only.")
@click.argument("tokens", nargs=-1, required=True)
@click.pass_context
def capture_cmd(ctx, later, tokens):
    """Capture a new entry."""
    # Interactive fallback: if only the signifier is given, prompt for text
    if len(tokens) == 1 and (SIGNIFIER_RE.match(tokens[0]) or BULLET_RE.match(tokens[0]) or WORD_SIGNIFIER_RE.match(tokens[0])):
        import questionary

        type_labels = {
            "t": "task", "t!": "task (important)",
            "n": "note", "n!": "note (important)",
            "j": "journal", "j!": "journal (important)",
            "c": "event", "c!": "event (important)",
            ".": "task", ".!": "task (important)",
            "=": "journal", "=!": "journal (important)",
            "-": "note", "-!": "note (important)",
            "o": "event", "o!": "event (important)",
            "task": "task", "task!": "task (important)",
            "note": "note", "note!": "note (important)",
            "journal": "journal", "journal!": "journal (important)",
            "cal": "event", "cal!": "event (important)",
        }
        key = tokens[0].lstrip("/")
        label = type_labels.get(key, "entry")
        text = questionary.text(f"{label}:").ask()
        if not text or not text.strip():
            click.echo("Cancelled.")
            return
        # Re-tokenize: signifier + user's text split into words
        tokens = (tokens[0], *text.strip().split())

    parsed = parse_capture_tokens(tokens)

    # Collection capture — add to collection, no entry created
    if parsed.collection:
        from bute.collection_storage import append_to_collection, load_collection
        from rich.console import Console

        console = Console()

        # Map signifier to BuJo bullet
        bullet_map = {"/t": ".", "/n": "-", "/j": "=", "/c": "o"}
        bullet = bullet_map.get(parsed.signifier, ".")

        # Reconstruct raw line: bullet + body + tags + metadata
        parts = [bullet, parsed.body]
        for tag in parsed.tags:
            parts.append(f"@{tag}")
        for key, value in parsed.metadata.items():
            parts.append(f"{key}:{value}")
        raw_line = " ".join(parts)

        config = ctx.obj.get("config")
        result = append_to_collection(parsed.collection, [f"- {raw_line}"], config=config)
        if result is None:
            console.print(f"  [red]Cannot add to +{parsed.collection} — already processed.[/red]")
            return

        coll = load_collection(parsed.collection, config=config)
        count = coll["item_count"] if coll else 0
        console.print(f"  [green]Added to +{parsed.collection} ({count} items)[/green]")
        return

    entry_type = SIGNIFIER_MAP[parsed.signifier]

    # Extract and resolve known metadata keys
    meta = dict(parsed.metadata)
    due = resolve_date(meta.pop("due")) if "due" in meta else None
    # Support both d: and date:
    raw_date = meta.pop("d", None) or meta.pop("date", None)
    scheduled_date = resolve_date(raw_date) if raw_date else None
    # Support both t: and time:
    raw_time = meta.pop("t", None) or meta.pop("time", None)
    scheduled_time = resolve_time(raw_time) if raw_time else None
    repeat = meta.pop("repeat", None)

    entry = Entry.create(
        entry_type=entry_type,
        body=parsed.body,
        important=parsed.important,
        tags=parsed.tags,
        due=due,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        repeat=repeat,
        extra_meta=meta,
    )

    # Auto-add @thisweek and @today for tasks unless --later flag
    if entry.type == EntryType.TASK and not later:
        if "thisweek" not in entry.tags:
            entry.tags.append("thisweek")
        if "today" not in entry.tags:
            entry.tags.append("today")

    config = ctx.obj.get("config")
    save_entry(entry, config)
    from bute.ai import embed_entry
    embed_entry(entry.id, entry.body, config)
    confirm_capture(entry)
