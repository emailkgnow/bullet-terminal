"""Style 4 demo — panel boxes per cluster with real @bt data."""
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

console.print()
console.print("  [bold]@bt[/bold] — 15 entries across 6 themes")
console.print()

# Platform Expansion
body = Text()
body.append("  ● ", style="cyan")
body.append("will bt run on windows. how if we use brew ask claude\n")
body.append("  ● ", style="cyan")
body.append("VPS/SSH support: replace macOS Keychain API key resolution with cross-platform fallback\n")
body.append("  ● ", style="cyan")
body.append("can we equip gemma 4 with bt by default")
console.print(Panel(body, title="[bold cyan]Platform Expansion[/bold cyan]", border_style="cyan", padding=(0, 1)))

# AI Integration
body = Text()
body.append("  ● ", style="green")
body.append("add ai providers. make it as simple as possible for the user\n")
body.append("  ● ", style="green")
body.append("add mcp server to bt see note\n")
body.append("  ● ", style="green")
body.append("Claude Remote Access Options for bt — Channels, Remote Control, Dispatch")
console.print(Panel(body, title="[bold green]AI Integration[/bold green]", border_style="green", padding=(0, 1)))

# Mobile & Remote Access
body = Text()
body.append("  ● ", style="magenta")
body.append("add mobile access for bt\n")
body.append("  ● ", style="magenta")
body.append("create bt slide deck to present features")
console.print(Panel(body, title="[bold magenta]Mobile & Remote Access[/bold magenta]", border_style="magenta", padding=(0, 1)))

# Community
body = Text()
body.append("  ● ", style="blue")
body.append("share bullet-terminal on reddit for feedback")
console.print(Panel(body, title="[bold blue]Community & Feedback[/bold blue]", border_style="blue", padding=(0, 1)))

# Core Development
body = Text()
body.append("  ● keep refining bt\n", style="dim")
body.append("  ● i need to keep working on bt\n", style="dim")
body.append("  ● check out what all the folders are for\n", style="dim")
body.append("  ● I need to create a way to edit entries\n", style="dim")
body.append("  ● should i merge journal entries and notes", style="dim")
console.print(Panel(body, title="[dim]Core Development [Complete][/dim]", border_style="dim", padding=(0, 1)))

# Tensions / Gaps
body = Text()
body.append("  ● ", style="yellow")
body.append("Heavy focus on tasks without corresponding reflections — lots of \"how\" but missing \"why\"\n", style="yellow")
body.append("  ● ", style="yellow")
body.append("Mobile access appears twice with different approaches — need to align", style="yellow")
console.print(Panel(body, title="[bold yellow]Tensions / Gaps[/bold yellow]", border_style="yellow", padding=(0, 1)))

console.print()
