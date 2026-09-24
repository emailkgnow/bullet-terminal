"""Full-screen entry viewer for `bt <n>` — read first, `e` to edit.

Reading is most of why an entry gets opened, so `bt <n>` renders it rather than
dropping into an editor. `e` hands the real .md file to $EDITOR, then the view
reloads from disk. Textual is imported only here, and this module is imported
only when a viewer actually runs, so other commands don't pay its startup cost.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Callable

from rich.markup import escape as escape_markup
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Markdown, Static

from bute.display import TYPE_STYLE, entry_meta_parts
from bute.models import Entry, TaskStatus
from bute.storage import load_entry

_CHECKBOX = re.compile(r"^(\s*[-*+] )\[([ xX])\] ", re.MULTILINE)


def prepare_body(body: str) -> str:
    """Swap GitHub task-list boxes for glyphs — Textual's Markdown shows them raw."""
    return _CHECKBOX.sub(lambda m: m.group(1) + ("☐ " if m.group(2) == " " else "☑ "), body)


def meta_markup(entry: Entry) -> str:
    """One-line Rich-markup header: signifier, type, status, then the metadata line."""
    style = TYPE_STYLE[entry.type]
    color = style["color"]
    head = ""
    if entry.important:
        head += "[bold red]![/] "
    head += f"[bold {color}]{style['icon']}  {style['label']}[/]"
    if entry.status == TaskStatus.DONE:
        head += "  [green]· done[/]"
    elif entry.status == TaskStatus.DROPPED:
        head += "  [dim]· dropped[/]"
    meta = " · ".join(escape_markup(p) for p in entry_meta_parts(entry))
    return f"{head}  [dim]{meta}[/]"


class EntryViewer(App):
    """Metadata strip, rendered body, key footer. Steps through several entries."""

    ENABLE_COMMAND_PALETTE = False
    CSS = """
    #meta { height: auto; padding: 0 2; border-bottom: solid $primary; }
    #scroll { padding: 0 1; }
    MarkdownH2 { text-style: bold; }
    """
    BINDINGS = [
        Binding("q,escape", "quit", "Quit"),
        Binding("e,ctrl+e", "edit", "Edit"),
        Binding("n", "step(1)", "Next"),
        Binding("p", "step(-1)", "Prev"),
        Binding("j,down", "scroll(1)", "Down", show=False),
        Binding("k,up", "scroll(-1)", "Up", show=False),
    ]

    def __init__(self, paths: list[Path], on_edit: Callable[[Path], None]):
        super().__init__()
        self.paths = paths
        self.on_edit = on_edit
        self.index = 0

    def compose(self) -> ComposeResult:
        yield Static(id="meta")
        with VerticalScroll(id="scroll"):
            yield Markdown(id="body")
        yield Footer()

    def on_mount(self) -> None:
        self.load()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # n/p only exist when there is more than one entry to step through
        if action == "step":
            return len(self.paths) > 1
        return True

    def load(self) -> None:
        """(Re)read the current entry from disk. A broken file keeps the last render."""
        meta = self.query_one("#meta", Static)
        counter = f"  [dim]{self.index + 1}/{len(self.paths)}[/]" if len(self.paths) > 1 else ""
        try:
            entry = load_entry(self.paths[self.index])
        except Exception as e:
            meta.update(f"[bold red]Could not read entry:[/] {escape_markup(str(e))}{counter}")
            return
        meta.update(meta_markup(entry) + counter)
        self.query_one("#body", Markdown).update(prepare_body(entry.body))
        self.query_one("#scroll", VerticalScroll).scroll_home(animate=False)

    def action_scroll(self, lines: int) -> None:
        self.query_one("#scroll", VerticalScroll).scroll_relative(y=lines, animate=False)

    def action_step(self, delta: int) -> None:
        self.index = (self.index + delta) % len(self.paths)
        self.load()

    def action_edit(self) -> None:
        path = self.paths[self.index]
        cmd = [os.environ.get("EDITOR", "nano"), str(path)]
        try:
            with self.suspend():
                subprocess.call(cmd)
        except SuspendNotSupported:
            subprocess.call(cmd)
        try:
            self.on_edit(path)
        except Exception:
            pass  # load() below reports an unreadable file
        self.load()


def run_viewer(paths: list[Path], on_edit: Callable[[Path], None]) -> None:
    EntryViewer(paths, on_edit).run()
