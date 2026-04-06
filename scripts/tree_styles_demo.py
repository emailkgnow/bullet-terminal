"""
Rich Tree visual style exploration for bt @tag analyze output.
Shows 5 distinct rendering styles for the same mind-map data.
"""

from rich.console import Console
from rich.tree import Tree
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.columns import Columns
from rich import box

console = Console(width=100)

# ─── Data ────────────────────────────────────────────────────────────────

MINDMAP = {
    "Platform Expansion": {
        "items": [
            "Windows support via WSL/native paths",
            "VPS/SSH — remote bt over SSH tunnel",
            "Gemma 4 — local LLM as offline provider",
        ],
    },
    "AI Integration": {
        "items": [
            "Multi-provider support (OpenAI, Anthropic, local)",
            "MCP server — expose bt as tool for AI agents",
            "Claude channels — bt as conversational interface",
        ],
    },
    "Mobile & Remote Access": {
        "items": [
            "Mobile access via AI agent + MCP dispatch",
            "Slide deck — generate reveal.js from entries",
        ],
    },
    "Tensions / Gaps": {
        "items": [
            "CLI purity vs. accessibility — more users need GUI/mobile",
            "Local-first vs. AI-dependent — graceful degradation matters",
        ],
    },
}

BRANCH_COLORS = ["cyan", "green", "magenta", "yellow"]
BRANCH_ICONS = ["🔧", "🤖", "📱", "⚡"]


# ─── Style 1: Default Rich Tree ─────────────────────────────────────────

def style_default():
    console.rule("[bold]Style 1 — Default Rich Tree (guide lines)")
    console.print()

    tree = Tree("@bt — project mind map")
    for branch_name, data in MINDMAP.items():
        branch = tree.add(branch_name)
        for item in data["items"]:
            branch.add(item)

    console.print(tree)
    console.print()


# ─── Style 2: Custom Icons per Branch ───────────────────────────────────

def style_icons():
    console.rule("[bold]Style 2 — Icons per branch type")
    console.print()

    tree = Tree("[bold white]@bt[/] mind map", guide_style="dim")
    for (branch_name, data), icon in zip(MINDMAP.items(), BRANCH_ICONS):
        branch = tree.add(f"{icon} [bold]{branch_name}[/]")
        for item in data["items"]:
            branch.add(f"  {item}")

    console.print(tree)
    console.print()


# ─── Style 3: Color-coded Branches ──────────────────────────────────────

def style_colored():
    console.rule("[bold]Style 3 — Color-coded branches")
    console.print()

    tree = Tree(
        "[bold white on grey23]  @bt  [/]",
        guide_style="bold bright_black",
    )
    for (branch_name, data), color in zip(MINDMAP.items(), BRANCH_COLORS):
        branch = tree.add(
            f"[bold {color}]{branch_name}[/]  [dim]({len(data['items'])} items)[/]",
            guide_style=color,
        )
        for item in data["items"]:
            branch.add(f"[{color}]●[/] {item}")

    console.print(tree)
    console.print()


# ─── Style 4: Panel Clusters ────────────────────────────────────────────

def style_panels():
    console.rule("[bold]Style 4 — Panel boxes per cluster")
    console.print()

    for (branch_name, data), color in zip(MINDMAP.items(), BRANCH_COLORS):
        items_text = "\n".join(f"  [{color}]●[/] {item}" for item in data["items"])
        panel = Panel(
            items_text,
            title=f"[bold {color}]{branch_name}[/]",
            title_align="left",
            border_style=color,
            box=box.ROUNDED,
            width=80,
            padding=(0, 1),
        )
        console.print(panel)

    console.print()


# ─── Style 5: Compact Columns ───────────────────────────────────────────

def style_compact():
    console.rule("[bold]Style 5 — Compact column layout")
    console.print()

    renderables = []
    for (branch_name, data), color in zip(MINDMAP.items(), BRANCH_COLORS):
        lines = [f"[bold {color}]{branch_name}[/]"]
        lines.append(f"[{color}]{'─' * len(branch_name)}[/]")
        for item in data["items"]:
            # Truncate long items for compact display
            short = item if len(item) <= 35 else item[:32] + "..."
            lines.append(f"[dim]•[/] {short}")
        renderables.append(Panel(
            "\n".join(lines),
            box=box.SIMPLE,
            width=42,
            padding=(0, 1),
        ))

    console.print(Columns(renderables, equal=True, expand=True))
    console.print()


# ─── Style 6 (bonus): Tree with BuJo signifiers ────────────────────────

def style_bujo():
    console.rule("[bold]Style 6 (bonus) — BuJo signifier style")
    console.print()

    tree = Tree(
        "[bold white]@bt[/] [dim]— 10 entries across 4 themes[/]",
        guide_style="bright_black",
    )
    signifiers = {
        "Platform Expansion": (".", "cyan"),       # task dot
        "AI Integration": (".", "green"),           # task dot
        "Mobile & Remote Access": (".", "magenta"), # task dot
        "Tensions / Gaps": ("-", "yellow"),         # note dash
    }
    for (branch_name, data) in MINDMAP.items():
        sig, color = signifiers[branch_name]
        branch = tree.add(
            f"[bold {color}]{branch_name}[/]  "
            f"[dim]{len(data['items'])} {'notes' if sig == '-' else 'tasks'}[/]"
        )
        for item in data["items"]:
            branch.add(f"[bold {color}]{sig}[/] {item}")

    console.print(tree)
    console.print()


# ─── Style 7 (bonus): Nested tree with summary line ────────────────────

def style_summary_tree():
    console.rule("[bold]Style 7 (bonus) — Tree with theme tags")
    console.print()

    tree = Tree(
        "[bold]@bt[/]",
        guide_style="dim blue",
    )
    theme_tags = ["#platform", "#ai", "#mobile", "#tensions"]
    for (branch_name, data), color, tag in zip(MINDMAP.items(), BRANCH_COLORS, theme_tags):
        label = Text()
        label.append(f"{branch_name}", style=f"bold {color}")
        label.append(f"  {tag}", style="dim italic")
        branch = tree.add(label)
        for item in data["items"]:
            leaf = Text()
            leaf.append("  › ", style=f"bold {color}")
            leaf.append(item)
            branch.add(leaf)

    console.print(tree)
    console.print()


# ─── Run all ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    console.print()
    console.print(
        Panel(
            "[bold]Rich Tree Style Exploration[/]\n"
            "Visual options for [cyan]bt @tag analyze[/] mind-map output",
            box=box.DOUBLE,
            width=60,
            style="dim",
        )
    )
    console.print()

    style_default()
    style_colored()
    style_icons()
    style_panels()
    style_compact()
    style_bujo()
    style_summary_tree()
