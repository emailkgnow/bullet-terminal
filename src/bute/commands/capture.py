"""Capture command — handles t/n/j/c and task/note/journal/calendar signifier input."""

import os
import re
import subprocess
import tempfile
from datetime import date

import click
import frontmatter

from bute.completion import complete_tags
from bute.display import confirm_capture
from bute.models import SIGNIFIER_MAP, Entry, EntryType
from bute.parser import (
    SIGNIFIER_RE,
    WORD_SIGNIFIER_RE,
    parse_capture_tokens,
    check_removed_meta_keys,
    resolve_date,
    resolve_repeat,
    resolve_time,
)
from bute.storage import load_entry, save_entry


@click.command("capture", hidden=True, context_settings={"ignore_unknown_options": True})
@click.option("--week", "-w", "week_only", is_flag=True, help="This week, not today (bt t -w).")
@click.option("--backlog", "-b", is_flag=True, help="Backlog only — no focus dates.")
@click.argument("tokens", nargs=-1, required=True, shell_complete=complete_tags)
@click.pass_context
def capture_cmd(ctx, week_only, backlog, tokens):
    """Capture a new entry."""
    # -a is a view filter, not a capture scope. ignore_unknown_options would
    # otherwise write it into the body — reject it the way removed metadata
    # keys are rejected, with a pointer at the flag that was meant.
    for tok in tokens[1:]:
        if tok in ("-a", "--all"):
            click.echo(
                f"{tok} filters a view, it doesn't pick a capture scope. "
                "Use -w for this week or -b for the backlog."
            )
            ctx.exit(1)
            return
    # Interactive fallback: if only the signifier is given, prompt for text
    if len(tokens) == 1 and (SIGNIFIER_RE.match(tokens[0]) or WORD_SIGNIFIER_RE.match(tokens[0])):
        import questionary

        type_labels = {
            "t": "task", "t!": "task (important)",
            "n": "note", "n!": "note (important)",
            "j": "journal", "j!": "journal (important)",
            "c": "event", "c!": "event (important)",
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
    try:
        check_removed_meta_keys(meta)
        raw_time = meta.pop("time", None)
        # due: can be a date (due:friday) or a time (due:3pm → today at 3pm)
        raw_due = meta.pop("due", None)
        if raw_due is not None:
            if re.search(r'(?:am|pm)$', raw_due.lower().strip()):
                due = date.today()
                if not raw_time:
                    raw_time = raw_due
            else:
                due = resolve_date(raw_due)
        else:
            due = None
        raw_date = meta.pop("date", None)
        scheduled_date = resolve_date(raw_date) if raw_date else None
        scheduled_time = resolve_time(raw_time) if raw_time else None
        raw_repeat = meta.pop("repeat", None)
        repeat = resolve_repeat(raw_repeat) if raw_repeat is not None else None
    except ValueError as e:
        click.echo(str(e))
        ctx.exit(1)
        return

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

    # Set focus dates on tasks based on flags:
    #   default  → focus_date=today + week_date=monday (bt t)
    #   -w       → week_date only (bt t -w)
    #   -b       → no focus dates (bt t -b)
    config = ctx.obj.get("config")
    has_future_date = entry.scheduled_date and entry.scheduled_date > date.today()
    has_future_due = entry.due and entry.due > date.today()
    if entry.type == EntryType.TASK and not backlog and not has_future_date and not has_future_due:
        from bute.ritual_ops import week_anchor
        entry.week_date = week_anchor(config=config)
        if not week_only:
            entry.focus_date = date.today()

    save_entry(entry, config)
    confirm_capture(entry)


def _resolve_signifier_token(token: str) -> tuple[str, bool]:
    """Resolve a raw CLI signifier token to ('/t'-style key, important flag)."""
    from bute.parser import WORD_TO_SIGNIFIER

    match = SIGNIFIER_RE.match(token)
    if match:
        return f"/{match.group(1)}", match.group(2) == "!"

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

        # Set focus dates on tasks (same logic as inline capture)
        config = ctx.obj.get("config")
        has_future_date = edited.scheduled_date and edited.scheduled_date > date.today()
        has_future_due = edited.due and edited.due > date.today()
        if edited.type == EntryType.TASK and not has_future_date and not has_future_due:
            from bute.ritual_ops import week_anchor
            edited.week_date = week_anchor(config=config)
            edited.focus_date = date.today()

        save_entry(edited, config)
        confirm_capture(edited)
    finally:
        os.unlink(tmp_path)
