"""Provider-agnostic LLM client for bute — supports Anthropic and OpenAI-compatible APIs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bute.models import Entry

logger = logging.getLogger(__name__)

_client = None
_available: bool | None = None
_provider: str | None = None


def _resolve_api_key(value: str) -> str:
    """Resolve API key — supports 'keychain:<service>' or direct value."""
    if not value:
        # Try macOS Keychain default
        try:
            import subprocess
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "bute-anthropic-api-key", "-a", "bute", "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""
    if value.startswith("keychain:"):
        service = value[len("keychain:"):]
        try:
            import subprocess
            result = subprocess.run(
                ["security", "find-generic-password", "-s", service, "-a", "bute", "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""
    return value


def _get_provider(config=None) -> str:
    """Get the provider name from config."""
    if config and "ai" in config:
        return config["ai"].get("provider", "openai")
    return "openai"


def is_available(config=None) -> bool:
    """Check if LLM dependencies are installed and API key is configured."""
    global _available
    if _available is None:
        try:
            import openai  # noqa: F401
            _available = True
        except ImportError:
            try:
                import anthropic  # noqa: F401
                _available = True
            except ImportError:
                _available = False

    if not _available:
        return False

    # Check config for API key (ollama doesn't need one)
    if config:
        provider = config.get("ai", {}).get("provider", "")
        api_key = _resolve_api_key(config.get("ai", {}).get("api_key", ""))
        if provider != "ollama" and not api_key:
            return False

    return True


def _get_client(config=None):
    """Lazy-create an LLM client from config."""
    global _client, _provider
    if _client is not None:
        return _client

    provider = _get_provider(config)
    _provider = provider

    if config and "ai" in config:
        ai_config = config["ai"]
        base_url = ai_config.get("base_url", "")
        api_key = _resolve_api_key(ai_config.get("api_key", ""))
    else:
        base_url = ""
        api_key = ""

    if provider == "anthropic":
        from anthropic import Anthropic
        _client = Anthropic(api_key=api_key or None)
    else:
        from openai import OpenAI
        _client = OpenAI(base_url=base_url or None, api_key=api_key or None)

    return _client


def _get_model(config=None) -> str:
    """Get the model name from config."""
    if config and "ai" in config:
        return config["ai"].get("model", "gpt-4o")
    return "gpt-4o"


def reset():
    """Reset the client singleton (for testing)."""
    global _client, _available, _provider
    _client = None
    _available = None
    _provider = None


def send_message(system: str, user: str, config=None) -> str:
    """Send a message to the LLM and return the response text."""
    try:
        client = _get_client(config)
        model = _get_model(config)

        if _provider == "anthropic":
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text
        else:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return response.choices[0].message.content
    except Exception as e:
        logger.debug("LLM call failed: %s", e, exc_info=True)
        return "[AI unavailable]"


def stream_chat(messages: list[dict], config=None):
    """Stream a multi-turn chat completion. Yields content chunks."""
    try:
        client = _get_client(config)
        model = _get_model(config)

        if _provider == "anthropic":
            system, msgs = _split_system_message(messages)
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system,
                messages=msgs,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        else:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
    except Exception as e:
        logger.debug("LLM stream failed: %s", e, exc_info=True)
        yield "[AI unavailable]"


def stream_chat_with_tools(messages: list[dict], tools: list[dict], config=None):
    """Stream a multi-turn chat completion with tool calling support.

    Yields dicts with either:
      {"type": "content", "content": "text chunk"}
      {"type": "tool_call", "id": "call_xxx", "name": "func", "arguments": "json_str"}
      {"type": "done"}
    """
    try:
        client = _get_client(config)
        model = _get_model(config)

        if _provider == "anthropic":
            yield from _stream_anthropic_tools(client, model, messages, tools)
        else:
            yield from _stream_openai_tools(client, model, messages, tools)

    except Exception as e:
        logger.debug("LLM stream failed: %s", e, exc_info=True)
        yield {"type": "content", "content": "[AI unavailable]"}
        yield {"type": "done"}


def _stream_anthropic_tools(client, model, messages, tools):
    """Stream with tool calling via Anthropic SDK."""
    import json

    system, msgs = _split_system_message(messages)
    anthropic_tools = _convert_tools_to_anthropic(tools)

    # Convert OpenAI-style tool results to Anthropic format
    msgs = _convert_messages_to_anthropic(msgs)

    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system=system,
        messages=msgs,
        tools=anthropic_tools if anthropic_tools else [],
    ) as stream:
        for event in stream:
            if event.type == "content_block_start":
                if event.content_block.type == "tool_use":
                    # Will accumulate via deltas
                    pass
            elif event.type == "text":
                yield {"type": "content", "content": event.text}
            elif event.type == "content_block_stop":
                pass

        # After stream completes, check for tool use in the final message
        response = stream.get_final_message()
        for block in response.content:
            if block.type == "tool_use":
                yield {
                    "type": "tool_call",
                    "id": block.id,
                    "name": block.name,
                    "arguments": json.dumps(block.input),
                }

    yield {"type": "done"}


def _stream_openai_tools(client, model, messages, tools):
    """Stream with tool calling via OpenAI SDK."""
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools if tools else None,
        stream=True,
    )

    tool_calls: dict[int, dict] = {}

    for chunk in stream:
        delta = chunk.choices[0].delta

        if delta.content:
            yield {"type": "content", "content": delta.content}

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls:
                    tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                if tc.id:
                    tool_calls[idx]["id"] = tc.id
                if tc.function and tc.function.name:
                    tool_calls[idx]["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    tool_calls[idx]["arguments"] += tc.function.arguments

        if chunk.choices[0].finish_reason == "tool_calls":
            for idx in sorted(tool_calls.keys()):
                tc = tool_calls[idx]
                yield {"type": "tool_call", "id": tc["id"], "name": tc["name"], "arguments": tc["arguments"]}
            tool_calls.clear()

    yield {"type": "done"}


def _split_system_message(messages: list[dict]) -> tuple[str, list[dict]]:
    """Extract the system message from an OpenAI-style message list."""
    system = ""
    msgs = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            msgs.append(m)
    return system, msgs


def _convert_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert OpenAI function-calling tool schemas to Anthropic format."""
    anthropic_tools = []
    for tool in tools:
        func = tool["function"]
        anthropic_tools.append({
            "name": func["name"],
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        })
    return anthropic_tools


def _convert_messages_to_anthropic(messages: list[dict]) -> list[dict]:
    """Convert OpenAI-style messages (with tool_calls/tool roles) to Anthropic format."""
    result = []
    for m in messages:
        if m["role"] == "assistant" and "tool_calls" in m:
            # Convert assistant message with tool_calls to Anthropic content blocks
            content = []
            if m.get("content"):
                content.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                import json
                content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                })
            result.append({"role": "assistant", "content": content})
        elif m["role"] == "tool":
            # Convert tool result — Anthropic expects these as user messages with tool_result blocks
            # Check if previous message is already a user with tool_result, and merge
            tool_block = {
                "type": "tool_result",
                "tool_use_id": m["tool_call_id"],
                "content": m["content"],
            }
            if result and result[-1]["role"] == "user" and isinstance(result[-1]["content"], list):
                result[-1]["content"].append(tool_block)
            else:
                result.append({"role": "user", "content": [tool_block]})
        else:
            result.append({"role": m["role"], "content": m["content"]})
    return result


def send_with_entries(
    system: str, entries: list[Entry], question: str, config=None
) -> str:
    """Format entries as context, append question, and send to LLM."""
    from bute.ai.prompts import format_entries

    context = format_entries(entries)
    user_message = f"## Entries\n\n{context}\n\n## Question\n\n{question}"
    return send_message(system, user_message, config)
