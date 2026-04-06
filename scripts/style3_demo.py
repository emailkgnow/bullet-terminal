"""Style 3 demo — color-coded branches with real @bt data."""
from rich.console import Console
from rich.tree import Tree

console = Console()

tree = Tree('[bold]@bt[/bold]')

# Platform Expansion — cyan
p = tree.add('[bold cyan]Platform Expansion[/bold cyan]  [dim](3 items)[/dim]', guide_style='cyan')
p.add('[cyan]●[/cyan] will bt run on windows. how if we use brew ask claude')
p.add('[cyan]●[/cyan] VPS/SSH support: replace macOS Keychain API key resolution with cross-platform fallback')
p.add('[cyan]●[/cyan] can we equip gemma 4 with bt by default')

# AI Integration — green
a = tree.add('[bold green]AI Integration[/bold green]  [dim](3 items)[/dim]', guide_style='green')
a.add('[green]●[/green] add ai providers. make it as simple as possible for the user')
a.add('[green]●[/green] add mcp server to bt see note')
a.add('[green]●[/green] Claude Remote Access Options for bt — Channels, Remote Control, Dispatch')

# Mobile & Remote Access — magenta
m = tree.add('[bold magenta]Mobile & Remote Access[/bold magenta]  [dim](2 items)[/dim]', guide_style='magenta')
m.add('[magenta]●[/magenta] add mobile access for bt')
m.add('[magenta]●[/magenta] create bt slide deck to present features')

# Community — blue
c = tree.add('[bold blue]Community & Feedback[/bold blue]  [dim](1 item)[/dim]', guide_style='blue')
c.add('[blue]●[/blue] share bullet-terminal on reddit for feedback')

# Core Development — dim
d = tree.add('[bold dim]Core Development[/bold dim]  [dim][Complete] (5 items)[/dim]', guide_style='dim')
d.add('[dim]● keep refining bt[/dim]')
d.add('[dim]● i need to keep working on bt[/dim]')
d.add('[dim]● check out what all the folders are for[/dim]')
d.add('[dim]● I need to create a way to edit entries[/dim]')
d.add('[dim]● should i merge journal entries and notes[/dim]')

# Tensions — yellow
t = tree.add('[bold yellow]Tensions / Gaps[/bold yellow]  [dim](2 items)[/dim]', guide_style='yellow')
t.add('[yellow]●[/yellow] Heavy focus on tasks without corresponding reflections — lots of "how" but missing "why"')
t.add('[yellow]●[/yellow] Mobile access appears twice with different approaches — need to align')

console.print()
console.print(tree)
console.print()
