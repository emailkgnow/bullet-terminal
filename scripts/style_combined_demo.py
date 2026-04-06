"""Combined style — color-coding from 3, BuJo signifiers from 6, extended guides."""
from rich.console import Console
from rich.tree import Tree

console = Console()

tree = Tree('[bold]@bt[/bold] — 15 entries across 6 themes')

PAD = "      "  # extra padding for extended second-level lines


# Platform Expansion — cyan
p = tree.add('[bold cyan]Platform Expansion[/bold cyan]  [dim]3 tasks[/dim]', guide_style='cyan')
p.add(f'[cyan]{PAD}.  will bt run on windows. how if we use brew ask claude[/cyan]', guide_style='cyan')
p.add(f'[cyan]{PAD}.  VPS/SSH support: replace macOS Keychain API key resolution with cross-platform fallback[/cyan]', guide_style='cyan')
p.add(f'[cyan]{PAD}.  can we equip gemma 4 with bt by default[/cyan]', guide_style='cyan')

# AI Integration — green
a = tree.add('[bold green]AI Integration[/bold green]  [dim]2 tasks, 1 note[/dim]', guide_style='green')
a.add(f'[green]{PAD}.  add ai providers. make it as simple as possible for the user[/green]', guide_style='green')
a.add(f'[green]{PAD}.  add mcp server to bt see note[/green]', guide_style='green')
a.add(f'[green]{PAD}-  Claude Remote Access Options for bt — Channels, Remote Control, Dispatch[/green]', guide_style='green')

# Mobile & Remote Access — magenta
m = tree.add('[bold magenta]Mobile & Remote Access[/bold magenta]  [dim]2 tasks[/dim]', guide_style='magenta')
m.add(f'[magenta]{PAD}.  add mobile access for bt[/magenta]', guide_style='magenta')
m.add(f'[magenta]{PAD}.  create bt slide deck to present features[/magenta]', guide_style='magenta')

# Community — blue
c = tree.add('[bold blue]Community & Feedback[/bold blue]  [dim]1 task[/dim]', guide_style='blue')
c.add(f'[blue]{PAD}.  share bullet-terminal on reddit for feedback[/blue]', guide_style='blue')

# Core Development — dim
d = tree.add('[dim]Core Development  [Complete] 5 tasks[/dim]', guide_style='dim')
d.add(f'[dim]{PAD}.  keep refining bt[/dim]', guide_style='dim')
d.add(f'[dim]{PAD}.  i need to keep working on bt[/dim]', guide_style='dim')
d.add(f'[dim]{PAD}.  check out what all the folders are for[/dim]', guide_style='dim')
d.add(f'[dim]{PAD}.  I need to create a way to edit entries[/dim]', guide_style='dim')
d.add(f'[dim]{PAD}.  should i merge journal entries and notes[/dim]', guide_style='dim')

# Tensions / Gaps — yellow
t = tree.add('[bold yellow]Tensions / Gaps[/bold yellow]', guide_style='yellow')
t.add(f'[yellow]{PAD}-  Heavy focus on tasks without corresponding reflections — lots of "how" but missing "why"[/yellow]', guide_style='yellow')
t.add(f'[yellow]{PAD}-  Mobile access appears twice with different approaches — need to align[/yellow]', guide_style='yellow')

console.print()
console.print(tree)
console.print()
