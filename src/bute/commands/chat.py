"""Interactive AI chat sessions anchored to bt entries."""

from __future__ import annotations

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
