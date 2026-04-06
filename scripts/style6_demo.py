"""Style 6 demo — BuJo signifier style with real @bt data."""
from rich.console import Console
from rich.tree import Tree

console = Console()

tree = Tree('[bold]@bt[/bold] — 15 entries across 6 themes')

# Platform Expansion
p = tree.add('[bold cyan]Platform Expansion[/bold cyan]  [dim]3 tasks[/dim]')
p.add('[cyan].[/cyan] will bt run on windows. how if we use brew ask claude')
p.add('[cyan].[/cyan] VPS/SSH support: replace macOS Keychain API key resolution with cross-platform fallback')
p.add('[cyan].[/cyan] can we equip gemma 4 with bt by default')

# AI Integration
a = tree.add('[bold cyan]AI Integration[/bold cyan]  [dim]2 tasks, 1 note[/dim]')
a.add('[cyan].[/cyan] add ai providers. make it as simple as possible for the user')
a.add('[cyan].[/cyan] add mcp server to bt see note')
a.add('[yellow]-[/yellow] Claude Remote Access Options for bt — Channels, Remote Control, Dispatch')

# Mobile & Remote Access
m = tree.add('[bold cyan]Mobile & Remote Access[/bold cyan]  [dim]2 tasks[/dim]')
m.add('[cyan].[/cyan] add mobile access for bt')
m.add('[cyan].[/cyan] create bt slide deck to present features')

# Community
c = tree.add('[bold cyan]Community & Feedback[/bold cyan]  [dim]1 task[/dim]')
c.add('[cyan].[/cyan] share bullet-terminal on reddit for feedback')

# Core Development
d = tree.add('[dim]Core Development[/dim]  [dim][Complete] 5 tasks[/dim]')
d.add('[dim]. keep refining bt[/dim]')
d.add('[dim]. i need to keep working on bt[/dim]')
d.add('[dim]. check out what all the folders are for[/dim]')
d.add('[dim]. I need to create a way to edit entries[/dim]')
d.add('[dim]. should i merge journal entries and notes[/dim]')

# Tensions / Gaps
t = tree.add('[bold yellow]Tensions / Gaps[/bold yellow]')
t.add('[yellow]-[/yellow] Heavy focus on tasks without corresponding reflections — lots of "how" but missing "why"')
t.add('[yellow]-[/yellow] Mobile access appears twice with different approaches — need to align')

console.print()
console.print(tree)
console.print()
