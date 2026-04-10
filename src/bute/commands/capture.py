"""Capture command — handles t/n/j/c and task/note/journal/calendar signifier input."""

import os
import subprocess
import tempfile
from datetime import date

import click
import frontmatter

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
from bute.storage import load_entry, save_entry


@click.command("capture", hidden=True)
@click.option("--later", "-l", is_flag=True, help="This week, not today (Task log).")
@click.option("--backlog", "-b", is_flag=True, help="Backlog only — no focus tags.")
@click.argument("tokens", nargs=-1, required=True)
@click.pass_context
def capture_cmd(ctx, later, backlog, tokens):
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
            "calendar": "event", "calendar!": "event (important)",
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
    repeat = meta.pop("r", None) or meta.pop("repeat", None)

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

    # Auto-tag tasks based on flags:
    #   default  → @thisweek + @today (Focus Log)
    #   -l       → @thisweek only (Task log, not today)
    #   -b       → no focus tags (Backlog)
    has_future_date = entry.scheduled_date and entry.scheduled_date > date.today()
    has_future_due = entry.due and entry.due > date.today()
    if entry.type == EntryType.TASK and not backlog and not has_future_date and not has_future_due:
        if "thisweek" not in entry.tags:
            entry.tags.append("thisweek")
        if not later and "today" not in entry.tags:
            entry.tags.append("today")

    config = ctx.obj.get("config")
    save_entry(entry, config)
    from bute.ai import embed_entry
    embed_entry(entry.id, entry.body, config)
    confirm_capture(entry)


def _resolve_signifier_token(token: str) -> tuple[str, bool]:
    """Resolve a raw CLI signifier token to ('/t'-style key, important flag)."""
    from bute.parser import BULLET_TO_SIGNIFIER, WORD_TO_SIGNIFIER

    match = SIGNIFIER_RE.match(token)
    if match:
        return f"/{match.group(1)}", match.group(2) == "!"

    bullet_match = BULLET_RE.match(token)
    if bullet_match:
        letter = BULLET_TO_SIGNIFIER[bullet_match.group(1)]
        return f"/{letter}", bullet_match.group(2) == "!"

    word_match = WORD_SIGNIFIER_RE.match(token)
    if word_match:
        letter = WORD_TO_SIGNIFIER[word_match.group(1)]
        return f"/{letter}", word_match.group(2) == "!"

    raise click.UsageError(f"Unknown signifier: {token}")


@click.command("open_capture", hidden=True)
@click.argument("signifier")
@click.pass_context
def open_capture_cmd(ctx, signifier):
    """Open $EDITOR for long-form entry capture."""
    sig_key, important = _resolve_signifier_token(signifier)
    entry_type = SIGNIFIER_MAP[sig_key]

    # Create a skeleton entry
    entry = Entry.create(entry_type=entry_type, body="", important=important)

    # Build the markdown template
    post = frontmatter.Post(content="\n", **entry.to_frontmatter_dict())
    template = frontmatter.dumps(post)

    # Write to a temp file and open in editor
    editor = os.environ.get("EDITOR", "nano")
    with tempfile.NamedTemporaryFile(
        suffix=".md", prefix=f"bt-{entry_type.value}-", mode="w", delete=False
    ) as f:
        f.write(template)
        tmp_path = f.name

    try:
        subprocess.call([editor, tmp_path])

        # Read back the edited file
        from pathlib import Path
        edited = load_entry(Path(tmp_path))

        if not edited.body.strip():
            click.echo("Empty body — cancelled.")
            return

        # Preserve the original entry's ID, type, and created timestamp
        # but pick up everything the user edited (body, tags, metadata)
        edited.id = entry.id
        edited.type = entry.type
        edited.created = entry.created

        # Auto-tag tasks (same logic as inline capture)
        has_future_date = edited.scheduled_date and edited.scheduled_date > date.today()
        has_future_due = edited.due and edited.due > date.today()
        if edited.type == EntryType.TASK and not has_future_date and not has_future_due:
            if "thisweek" not in edited.tags:
                edited.tags.append("thisweek")
            if "today" not in edited.tags:
                edited.tags.append("today")

        config = ctx.obj.get("config")
        save_entry(edited, config)
        from bute.ai import embed_entry
        embed_entry(edited.id, edited.body, config)
        confirm_capture(edited)
    finally:
        os.unlink(tmp_path)
