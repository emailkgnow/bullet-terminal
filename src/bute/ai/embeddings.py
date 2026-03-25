"""Local ONNX embedding model for bute using fastembed."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_model = None
_available: bool | None = None

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def is_available() -> bool:
    """Check if fastembed is installed. Cached after first call."""
    global _available
    if _available is None:
        try:
            import fastembed  # noqa: F401

            _available = True
        except ImportError:
            _available = False
    return _available


def _get_model():
    """Lazy-load the embedding model on first use."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns a list of 384 floats."""
    model = _get_model()
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in a batch. More efficient for rebuild."""
    if not texts:
        return []
    model = _get_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]
