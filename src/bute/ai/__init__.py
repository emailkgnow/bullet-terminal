"""AI subsystem for bute — embeddings, vector search, and LLM."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def is_embedding_available() -> bool:
    """Check if both fastembed and sqlite-vec are installed."""
    from bute.ai.embeddings import is_available as embed_ok
    from bute.ai.vectors import is_available as vec_ok

    return embed_ok() and vec_ok()


def embed_entry(entry_id: str, body: str, config=None) -> None:
    """Embed an entry's body text and store the vector. No-op if deps missing."""
    if not is_embedding_available():
        return
    try:
        from bute.ai.embeddings import embed_text
        from bute.ai.vectors import upsert

        vector = embed_text(body)
        upsert(entry_id, vector, config)
    except Exception:
        logger.debug("Embedding failed for entry %s", entry_id[:8], exc_info=True)


def search_similar(
    query: str, limit: int = 10, config=None
) -> list[tuple[str, float]]:
    """Embed a query and return nearest entry IDs with distances.

    Returns empty list if deps are missing.
    """
    if not is_embedding_available():
        return []
    from bute.ai.embeddings import embed_text
    from bute.ai.vectors import search

    query_vector = embed_text(query)
    return search(query_vector, limit, config)


# --- LLM ---

_LLM_INSTALL_MSG = (
    "  [yellow]AI features require the openai package and a configured provider.[/yellow]\n"
    "  Install: [bold]uv pip install 'bute\\[ai]'[/bold]\n"
    "  Configure: [bold]bute init[/bold]"
)


def is_llm_available(config=None) -> bool:
    """Check if the LLM client is available and configured."""
    from bute.ai.llm import is_available

    return is_available(config)


def llm_send(system: str, user: str, config=None) -> str:
    """Send a message to the LLM. Returns fallback string on error."""
    from bute.ai.llm import send_message

    return send_message(system, user, config)


def llm_send_with_entries(
    system: str, entries: list, question: str, config=None
) -> str:
    """Format entries as context and send to LLM."""
    from bute.ai.llm import send_with_entries

    return send_with_entries(system, entries, question, config)
