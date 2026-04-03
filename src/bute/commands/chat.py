"""Interactive AI chat sessions anchored to bt entries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bute.models import Entry


@dataclass
class ChatSession:
    """Holds state for an interactive chat session."""

    anchor: Entry
    config: dict
    context_entries: list[Entry] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)
    last_bt_results: list[Entry] = field(default_factory=list)

    @classmethod
    def start(cls, entry: Entry, config: dict) -> ChatSession:
        """Create a new chat session anchored to an entry."""
        from bute.ai.prompts import chat_prompt, format_entries

        session = cls(
            anchor=entry,
            config=config,
            context_entries=[entry],
            messages=[
                {"role": "system", "content": chat_prompt()},
                {
                    "role": "user",
                    "content": (
                        f"I want to think through this entry:\n\n"
                        f"{format_entries([entry])}\n\n"
                        f"Help me process it."
                    ),
                },
            ],
            proposals=[],
            last_bt_results=[],
        )
        return session

    def add_to_context(self, entries: list[Entry]) -> None:
        """Add entries to the chat context (skips duplicates)."""
        from bute.ai.prompts import format_entries

        existing_ids = {e.id for e in self.context_entries}
        new_entries = [e for e in entries if e.id not in existing_ids]
        if not new_entries:
            return
        self.context_entries.extend(new_entries)
        self.messages.append({
            "role": "user",
            "content": f"[Added to context]\n{format_entries(new_entries)}",
        })

    def add_user_message(self, text: str) -> None:
        """Add a user message to the history."""
        self.messages.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str) -> None:
        """Add an assistant response to the history."""
        self.messages.append({"role": "assistant", "content": text})


_BT_BLOCK_RE = re.compile(r"```bt\s*\n(.*?)```", re.DOTALL)

_SIGNIFIER_TO_TYPE = {".": "task", "-": "note", "=": "journal", "o": "calendar"}


def parse_proposals(response_text: str) -> list[dict]:
    """Extract proposed entries from ```bt code blocks in AI response.

    Returns list of dicts with keys: type, important, body, tags, metadata.
    """
    proposals = []
    for match in _BT_BLOCK_RE.finditer(response_text):
        block = match.group(1)
        for line in block.strip().splitlines():
            parsed = _parse_proposal_line(line.strip())
            if parsed:
                proposals.append(parsed)
    return proposals


def _parse_proposal_line(line: str) -> dict | None:
    """Parse a single proposal line like '. task text @tag due:date'."""
    if not line:
        return None

    tokens = line.split()
    if not tokens:
        return None

    first = tokens[0]
    signifier = first.rstrip("!")
    important = first.endswith("!") and len(first) > 1

    if signifier not in _SIGNIFIER_TO_TYPE:
        return None

    entry_type = _SIGNIFIER_TO_TYPE[signifier]

    body_parts = []
    tags = []
    metadata = {}

    for token in tokens[1:]:
        if re.match(r"^@[a-zA-Z0-9_-]+$", token):
            tags.append(token[1:])
        elif ":" in token and not token.startswith(":") and token.split(":")[0] in ("due", "d", "t"):
            key, value = token.split(":", 1)
            metadata[key] = value
        else:
            body_parts.append(token)

    if not body_parts:
        return None

    return {
        "type": entry_type,
        "important": important,
        "body": " ".join(body_parts),
        "tags": tags,
        "metadata": metadata,
    }
