"""Local embeddings + vector search for bt — powers `bt like` and `bt rebuild`.

No network calls, no API keys. fastembed runs an ONNX model locally;
sqlite-vec stores vectors in `~/bullet-terminal/.index/entries.db`.
"""

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
