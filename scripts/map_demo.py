"""Mind map demo with real @bt data."""
from bute.display import display_analyze_map

response = """THEME: Platform Expansion
. will bt run on windows
. VPS/SSH cross-platform fallback
. equip gemma 4 by default

THEME: AI Integration
. add ai providers
. add mcp server to bt
- Claude Remote Access Options

THEME: Mobile & Remote Access
. add mobile access for bt
. create bt slide deck

THEME: Community & Feedback
. share bullet-terminal on reddit

THEME: Core Development
. keep refining bt
. create a way to edit entries
. check out folder structure

THEME: Tensions / Gaps
- Heavy focus on tasks without reflections
- Mobile access needs alignment"""

display_analyze_map("bt", response)
