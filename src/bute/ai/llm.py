"""Provider-agnostic LLM client for bute using OpenAI-compatible API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bute.models import Entry

logger = logging.getLogger(__name__)

_client = None
_available: bool | None = None


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


def is_available(config=None) -> bool:
    """Check if openai is installed and API key is configured."""
    global _available
    if _available is None:
        try:
            import openai  # noqa: F401

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
    """Lazy-create an OpenAI client from config."""
    global _client
    if _client is not None:
        return _client

    from openai import OpenAI

    if config and "ai" in config:
        ai_config = config["ai"]
        base_url = ai_config.get("base_url", "")
        api_key = _resolve_api_key(ai_config.get("api_key", ""))
    else:
        base_url = ""
        api_key = ""

    _client = OpenAI(base_url=base_url or None, api_key=api_key or None)
    return _client


def _get_model(config=None) -> str:
    """Get the model name from config."""
    if config and "ai" in config:
        return config["ai"].get("model", "gpt-4o")
    return "gpt-4o"


def reset():
    """Reset the client singleton (for testing)."""
    global _client, _available
    _client = None
    _available = None


def send_message(system: str, user: str, config=None) -> str:
    """Send a message to the LLM and return the response text.

    Returns "[AI unavailable]" on any error.
    """
    try:
        client = _get_client(config)
        model = _get_model(config)
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


def send_with_entries(
    system: str, entries: list[Entry], question: str, config=None
) -> str:
    """Format entries as context, append question, and send to LLM."""
    from bute.ai.prompts import format_entries

    context = format_entries(entries)
    user_message = f"## Entries\n\n{context}\n\n## Question\n\n{question}"
    return send_message(system, user_message, config)
