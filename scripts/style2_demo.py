"""Style 2 demo — icons per branch with real @bt data."""
from rich.console import Console
from rich.tree import Tree

console = Console()

tree = Tree('[bold]@bt[/bold] mind map')

# Platform Expansion
p = tree.add('🔧 [bold]Platform Expansion[/bold]')
p.add('will bt run on windows. how if we use brew ask claude')
p.add('VPS/SSH support: replace macOS Keychain API key resolution with cross-platform fallback')
p.add('can we equip gemma 4 with bt by default')

# AI Integration
a = tree.add('🤖 [bold]AI Integration[/bold]')
a.add('add ai providers. make it as simple as possible for the user')
a.add('add mcp server to bt see note')
a.add('Claude Remote Access Options for bt — Channels, Remote Control, Dispatch')

# Mobile & Remote Access
m = tree.add('📱 [bold]Mobile & Remote Access[/bold]')
m.add('add mobile access for bt')
m.add('create bt slide deck to present features')

# Community
c = tree.add('🌐 [bold]Community & Feedback[/bold]')
c.add('share bullet-terminal on reddit for feedback')

# Core Development
d = tree.add('✅ [bold dim]Core Development[/bold dim] [dim][Complete][/dim]')
d.add('[dim]keep refining bt[/dim]')
d.add('[dim]i need to keep working on bt[/dim]')
d.add('[dim]check out what all the folders are for[/dim]')
d.add('[dim]I need to create a way to edit entries[/dim]')
d.add('[dim]should i merge journal entries and notes[/dim]')

# Tensions
t = tree.add('⚡ [bold yellow]Tensions / Gaps[/bold yellow]')
t.add('[yellow]Heavy focus on tasks without corresponding reflections — lots of "how" but missing "why"[/yellow]')
t.add('[yellow]Mobile access appears twice with different approaches — need to align[/yellow]')

console.print()
console.print(tree)
console.print()
