"""Tests for the embedding module."""

import pytest

fastembed = pytest.importorskip("fastembed")

from bute.ai.embeddings import EMBEDDING_DIM, embed_text, embed_texts, is_available


def test_is_available():
    assert is_available() is True


@pytest.mark.slow
def test_embed_text_returns_correct_dim():
    result = embed_text("hello world")
    assert isinstance(result, list)
    assert len(result) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in result)


@pytest.mark.slow
def test_embed_texts_batch():
    results = embed_texts(["hello", "world"])
    assert len(results) == 2
    assert all(len(v) == EMBEDDING_DIM for v in results)


@pytest.mark.slow
def test_embed_texts_empty():
    assert embed_texts([]) == []
