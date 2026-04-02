"""Export command — zip all user data for backup."""

import zipfile
from datetime import date
from pathlib import Path

import click
from rich.console import Console

from bute.config import get_data_dir

console = Console()

README_CONTENT = """\
# Bullet Terminal Export

This archive is a complete snapshot of your Bullet Terminal (bt) data,
exported on {date}.

## What's Inside

```
entries/          Your entries — tasks, notes, journals, calendar events
  YYYY-MM/        Organized by month
    <ULID>.md     One Markdown file per entry (YAML frontmatter + body)

collections/      Your collections — idea-to-action funnels
  <name>.md       One file per collection (Input/Analysis/Tasks sections)

habits/           Your habit tracking data
  <name>/         One folder per habit
```

## Entry Format

Each `.md` file in `entries/` is a standalone Markdown file with YAML
frontmatter containing structured metadata:

```yaml
---
id: 01ABC123...          # ULID (time-sortable unique ID)
type: task               # task, note, journal, or calendar
status: active           # active, done, or dropped (tasks only)
created: 2026-01-15T...  # ISO timestamp
tags:                    # Optional tags
  - backend
  - urgent
due: 2026-01-20          # Optional due date (tasks)
date: 2026-01-20         # Optional scheduled date (calendar)
time: '14:30'            # Optional scheduled time (calendar)
---

The entry body text goes here.
```

## Directory Structure Rationale

- **Month folders** (`YYYY-MM/`) keep the filesystem manageable as entries
  grow over time. ULIDs encode their creation timestamp, so entries
  naturally sort chronologically within each folder.

- **Collections** are sectioned Markdown files that progress through
  stages: raw input -> AI analysis -> sequenced tasks. Each stage
  appends a new section, preserving the full trail.

- **Habits** store daily check-in data as simple files.

## Using This Export

These are plain Markdown files. You can:

- Read them in any text editor or Markdown viewer
- Import them into Obsidian, Notion, or any PKM tool
- Search them with grep, ripgrep, or your editor's search
- Reinstall Bullet Terminal and point it at these files to restore

The `.md` files are the source of truth — Bullet Terminal's SQLite
index is just a performance cache and is rebuilt automatically from
these files on first run.

## Learn More

Bullet Terminal: https://github.com/emailkgnow/bullet-terminal
"""


@click.command("export")
@click.option("-o", "--output", "output_dir", type=click.Path(), default=".",
              help="Output directory (default: current directory).")
@click.pass_context
def export_cmd(ctx, output_dir):
    """Export all entries, collections, and habits as a zip file."""
    config = ctx.obj.get("config")
    data_dir = get_data_dir(config)

    if not data_dir.exists():
        console.print("  [dim]No data to export.[/dim]")
        return

    # Build filename with counter for same-day exports
    out_path = Path(output_dir).resolve()
    today = date.today().isoformat()
    zip_name = f"bullet-terminal-markdown-{today}.zip"
    zip_path = out_path / zip_name

    counter = 1
    while zip_path.exists():
        counter += 1
        zip_name = f"bullet-terminal-markdown-{today}-{counter}.zip"
        zip_path = out_path / zip_name

    # Collect files from user data directories
    include_dirs = ["entries", "collections", "habits"]
    files_to_zip: list[tuple[Path, str]] = []

    for dirname in include_dirs:
        dir_path = data_dir / dirname
        if not dir_path.exists():
            continue
        for file_path in sorted(dir_path.rglob("*")):
            if file_path.is_file():
                arcname = str(file_path.relative_to(data_dir))
                files_to_zip.append((file_path, arcname))

    if not files_to_zip:
        console.print("  [dim]No files to export.[/dim]")
        return

    # Write zip
    out_path.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add README
        zf.writestr("README.md", README_CONTENT.format(date=today))

        for file_path, arcname in files_to_zip:
            zf.write(file_path, arcname)

    console.print(f"  [green]Exported {len(files_to_zip)} files to:[/green]")
    console.print(f"  [bold]{zip_path}[/bold]")
