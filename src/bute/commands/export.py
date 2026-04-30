"""Export command — zip all user data for backup."""

import zipfile
from datetime import date
from pathlib import Path

import click
from rich.console import Console

from bute.config import get_data_dir
from bute.guide import write_guide

console = Console()


@click.command("export")
@click.option("-o", "--output", "output_dir", type=click.Path(), default=".",
              help="Output directory (default: current directory).")
@click.pass_context
def export_cmd(ctx, output_dir):
    """Export all entries as a zip file."""
    config = ctx.obj.get("config")
    data_dir = get_data_dir(config)

    if not data_dir.exists():
        console.print("  [dim]No data to export.[/dim]")
        return

    write_guide(data_dir)

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
    include_dirs = ["entries"]
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
        for file_path, arcname in files_to_zip:
            zf.write(file_path, arcname)

    console.print(f"  [green]Exported {len(files_to_zip)} files to:[/green]")
    console.print(f"  [bold]{zip_path}[/bold]")
