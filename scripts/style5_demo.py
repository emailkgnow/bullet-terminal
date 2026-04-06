"""Style 5 demo — compact two-column layout with real @bt data."""
from rich.console import Console
from rich.columns import Columns
from rich.panel import Panel
from rich.text import Text

console = Console()

console.print()
console.print("  [bold]@bt[/bold] — 15 entries across 6 themes")
console.print()

def make_card(title, color, items, dim=False):
    body = Text()
    for i, item in enumerate(items):
        style = "dim" if dim else ""
        body.append("  • ", style=color if not dim else "dim")
        body.append(item, style=style)
        if i < len(items) - 1:
            body.append("\n")
    return Panel(body, title=f"[bold {color}]{title}[/bold {color}]", border_style=color, padding=(0, 1), expand=True)

cards = [
    make_card("Platform Expansion", "cyan", [
        "will bt run on windows",
        "VPS/SSH cross-platform fallback",
        "equip gemma 4 by default",
    ]),
    make_card("AI Integration", "green", [
        "add ai providers",
        "add mcp server to bt",
        "Claude Channels, Remote Control",
    ]),
    make_card("Mobile & Remote Access", "magenta", [
        "add mobile access for bt",
        "create bt slide deck",
    ]),
    make_card("Community & Feedback", "blue", [
        "share on reddit for feedback",
    ]),
    make_card("Core Development [Done]", "dim", [
        "keep refining bt",
        "keep working on bt",
        "check folder structure",
        "create a way to edit entries",
        "merge journals and notes?",
    ], dim=True),
    make_card("Tensions / Gaps", "yellow", [
        "lots of \"how\" but missing \"why\"",
        "mobile access needs alignment",
    ]),
]

console.print(Columns(cards, equal=True, expand=True))
console.print()
