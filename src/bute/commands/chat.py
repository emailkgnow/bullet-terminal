"""Interactive AI chat sessions with tool calling support."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from bute.display import TYPE_STYLE

if TYPE_CHECKING:
    from bute.models import Entry

console = Console()


@dataclass
class ChatSession:
    """Holds state for an interactive chat session."""

    config: dict
    context_entries: list[Entry] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    last_bt_results: list[Entry] = field(default_factory=list)

    @classmethod
    def start(cls, config: dict) -> ChatSession:
        """Create a new blank chat session with just the system prompt."""
        from bute.ai.prompts import chat_system_prompt

        session = cls(
            config=config,
            context_entries=[],
            messages=[
                {"role": "system", "content": chat_system_prompt()},
            ],
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


def execute_bt_view(args: list[str], config) -> list:
    """Execute a bt view command within chat and return matching entries."""
    from bute.storage import query_and_load

    if not args:
        return []

    first = args[0]

    sig_to_query = {
        "t": {"type": "task", "status": "active"},
        "n": {"type": "note"},
        "j": {"type": "journal"},
        "c": {"type": "calendar"},
    }

    # Signifier views: t, n, j, c (with optional @tag)
    if first in sig_to_query:
        kwargs = dict(sig_to_query[first])
        for arg in args[1:]:
            if arg.startswith("@") and len(arg) > 1:
                kwargs["tag"] = arg[1:]
        return query_and_load(config, **kwargs)

    # Important + type: t!, n!, etc.
    stripped = first.rstrip("!")
    if first.endswith("!") and stripped in sig_to_query:
        kwargs = dict(sig_to_query[stripped])
        kwargs["important"] = True
        return query_and_load(config, **kwargs)

    # Tag filter: @tagname
    if first.startswith("@") and len(first) > 1:
        return query_and_load(config, tag=first[1:])

    # Important filter: !
    if first == "!":
        return query_and_load(config, important=True)

    return []


def display_bt_results(entries: list, context_ids: set[str]) -> None:
    """Display bt query results with in-context markers."""
    if not entries:
        console.print("  [dim]No entries found.[/dim]")
        return

    table = Table(
        show_header=False, box=None, pad_edge=False,
        padding=(0, 1), expand=True,
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("", width=2)
    table.add_column("", ratio=1, overflow="fold")
    table.add_column("", style="dim")

    for i, entry in enumerate(entries, 1):
        style = TYPE_STYLE[entry.type]
        icon = Text()
        if entry.important:
            icon.append("!", style="bold red")
        else:
            icon.append(" ")
        icon.append(style["icon"], style=style["color"])

        body = Text(entry.body.split("\n", 1)[0].strip())

        meta_parts = []
        if entry.id in context_ids:
            meta_parts.append("← in ctx")
        if entry.due:
            meta_parts.append(f"due:{entry.due}")
        if entry.tags:
            meta_parts.extend(f"@{t}" for t in entry.tags)

        table.add_row(str(i), icon, body, " ".join(meta_parts))

    console.print()
    console.print(table)


@click.command("chat")
@click.pass_context
def chat_cmd(ctx):
    """Start an AI chat session — read & act on your entries."""
    config = ctx.obj.get("config") if ctx.obj else None
    start_chat_session(config)


def start_chat_session(config) -> None:
    """Start an interactive AI chat session with tool access."""
    from bute.ai import _LLM_INSTALL_MSG, is_embedding_available, is_llm_available

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    session = ChatSession.start(config)
    embeddings_available = is_embedding_available()

    console.print()
    console.print("  [bold]bt chat[/bold] — AI session with tool access")
    console.print("  [dim]/bt <args> to pull entries, /done to exit[/dim]")

    _run_repl(session, embeddings_available)


def _run_repl(session: ChatSession, embeddings_available: bool) -> None:
    """Run the chat REPL."""
    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            result = _handle_slash_command(session, user_input)
            if result == "exit":
                return
            continue

        # Number-action
        tokens = user_input.split()
        if tokens[0].isdigit():
            _handle_number_action(session, tokens)
            continue

        # Regular message → send to AI with tools
        session.add_user_message(user_input)
        _stream_with_tools(session, embeddings_available)


def _stream_with_tools(session: ChatSession, embeddings_available: bool) -> None:
    """Stream an AI response, handling tool calls in a loop."""
    from rich.live import Live

    from bute.ai.llm import stream_chat_with_tools
    from bute.ai.tools import execute_tool, get_tool_schemas
    from bute.display import display_ai_response

    tools = get_tool_schemas(embeddings_available=embeddings_available)

    while True:
        content_parts = []
        tool_calls = []

        with Live(Text(""), refresh_per_second=10, console=console, transient=True) as live:
            for event in stream_chat_with_tools(session.messages, tools, session.config):
                if event["type"] == "content":
                    content_parts.append(event["content"])
                    live.update(Text("".join(content_parts)))
                elif event["type"] == "tool_call":
                    tool_calls.append(event)
                elif event["type"] == "done":
                    break

        content_text = "".join(content_parts)

        # No tool calls — display response and return
        if not tool_calls:
            if content_text.strip():
                session.add_assistant_message(content_text)
                display_ai_response(content_text)
            return

        # Has tool calls — record assistant message with tool_calls, execute, loop
        assistant_msg = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in tool_calls
            ],
        }
        if content_text:
            assistant_msg["content"] = content_text
        session.messages.append(assistant_msg)

        # Execute each tool call and add results
        for tc in tool_calls:
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}

            console.print(f"  [dim]→ {tc['name']}[/dim]")
            result = execute_tool(tc["name"], args, session.config)

            session.messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        # Loop back to let the AI process tool results


def _handle_slash_command(session: ChatSession, command: str) -> str | None:
    """Handle a slash command. Returns 'exit' or None to continue."""
    parts = command.split(None, 1)
    cmd = parts[0].lower()
    args_str = parts[1] if len(parts) > 1 else ""

    if cmd == "/done":
        return "exit"

    if cmd == "/bt":
        bt_args = args_str.split() if args_str else []
        if not bt_args:
            console.print("  [dim]Usage: /bt t, /bt n, /bt @tag, /bt ![/dim]")
            return None
        entries = execute_bt_view(bt_args, session.config)
        if entries:
            session.last_bt_results = entries
            context_ids = {e.id for e in session.context_entries}
            display_bt_results(entries, context_ids)
            # Inject results into message history so the AI can see them
            from bute.ai.prompts import format_entries
            session.messages.append({
                "role": "user",
                "content": f"[/bt {args_str} — {len(entries)} entries]\n{format_entries(entries)}",
            })
        else:
            console.print("  [dim]No entries found.[/dim]")
        return None

    console.print(f"  [dim]Unknown command: {cmd}[/dim]")
    console.print("  [dim]Available: /bt <args>, /done[/dim]")
    return None


def _handle_number_action(session: ChatSession, tokens: list[str]) -> None:
    """Handle number-action commands in chat (e.g., '3 done', '1 @tag')."""
    numbers = []
    rest = list(tokens)
    while rest and rest[0].isdigit():
        numbers.append(int(rest.pop(0)))

    if not rest:
        console.print("  [dim]No action specified. Usage: 3 done, 1 @tag[/dim]")
        return

    action = rest[0]
    action_args = rest[1:]

    if not session.last_bt_results:
        console.print("  [dim]No entries to reference. Run /bt first.[/dim]")
        return

    # Resolve numbers to entries
    resolved = []
    for n in numbers:
        if n < 1 or n > len(session.last_bt_results):
            console.print(
                f"  [red]#{n} out of range (1-{len(session.last_bt_results)})[/red]"
            )
            return
        resolved.append(session.last_bt_results[n - 1])

    # Standard bt actions (done, drop, !, @tag, untag, later, backlog)
    from bute.commands.action import ACTION_HANDLERS, handle_add_tag, handle_remove_tag
    from bute.errors import DwnError
    from bute.display import display_action_confirmation
    from bute.storage import entry_path_from_id, load_entry

    # Handle @tag action
    if action.startswith("@") and len(action) > 1:
        tag = action[1:]
        for entry in resolved:
            handle_add_tag(entry, tag, session.config)
            display_action_confirmation(entry, f"@{tag}")
        return

    # Handle untag
    if action == "untag":
        if not action_args:
            console.print("  [dim]Usage: 1 untag @backend[/dim]")
            return
        tag = action_args[0].lstrip("@")
        for entry in resolved:
            handle_remove_tag(entry, tag, session.config)
            display_action_confirmation(entry, f"untag @{tag}")
        return

    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        console.print(f"  [dim]Unknown action: {action}[/dim]")
        return

    for entry in resolved:
        try:
            handler(entry, action_args, session.config)
            display_action_confirmation(entry, action)
        except DwnError as e:
            console.print(f"  [red]{e.format_message()}[/red]")
