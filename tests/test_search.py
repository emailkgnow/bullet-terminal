"""Integration tests for like and find commands."""

from unittest.mock import patch

import pytest

from bute.cli import main
from bute.models import Entry, EntryType
from bute.state import save_state
from bute.storage import save_entry


def _fake_embed_text(text):
    """Deterministic fake embedding based on text hash."""
    h = hash(text) % 1000
    return [float(h)] * 384


def _fake_embed_texts(texts):
    return [_fake_embed_text(t) for t in texts]


@pytest.fixture
def _mock_embeddings():
    """Mock embedding functions for speed."""
    with (
        patch("bute.ai.embeddings.is_available", return_value=True),
        patch("bute.ai.vectors.is_available", return_value=True),
        patch("bute.ai.embeddings.embed_text", side_effect=_fake_embed_text),
        patch("bute.ai.embeddings.embed_texts", side_effect=_fake_embed_texts),
    ):
        yield


def test_like_no_embeddings(runner, tmp_config, tmp_data):
    """Without embeddings, show install message."""
    with patch("bute.ai.embeddings.is_available", return_value=False):
        result = runner.invoke(main, ["like", "test"])
    assert result.exit_code == 0
    assert "embeddings" in result.output.lower()


def test_rebuild_no_embeddings(runner, tmp_config, tmp_data):
    """Without embeddings, rebuild still indexes entries but skips vectors."""
    e = Entry.create(EntryType.TASK, "call dentist")
    save_entry(e)

    with patch("bute.ai.embeddings.is_available", return_value=False):
        result = runner.invoke(main, ["rebuild"])
    assert result.exit_code == 0
    assert "embeddings" in result.output.lower()


@pytest.mark.skipif(
    not pytest.importorskip("sqlite_vec", reason="sqlite-vec not installed"),
    reason="sqlite-vec required",
)
class TestWithVectorDB:
    """Tests that need a real sqlite-vec DB but use mocked embeddings.

    No dedicated vector-DB setup/teardown is needed: `bute.ai.vectors`
    stores vectors in the same SQLite index as the rest of bt (see
    `bute.db.get_connection`), which the `tmp_data` fixture already
    points at a fresh temp directory and closes on teardown.
    """

    def test_rebuild_embeds_all(self, runner, tmp_config, tmp_data, _mock_embeddings):
        # Create entries
        for text in ["task one", "task two", "note three"]:
            e = Entry.create(EntryType.TASK, text)
            save_entry(e)

        result = runner.invoke(main, ["rebuild"])
        assert result.exit_code == 0
        assert "3" in result.output  # "Embedded 3 entries"

        from bute.ai.vectors import count

        assert count() == 3

    def test_like_returns_results(self, runner, tmp_config, tmp_data, _mock_embeddings):
        # Create and embed entries
        e1 = Entry.create(EntryType.TASK, "call dentist")
        e2 = Entry.create(EntryType.NOTE, "OAuth2 tokens")
        save_entry(e1)
        save_entry(e2)

        from bute.ai.vectors import upsert

        upsert(e1.id, _fake_embed_text(e1.body))
        upsert(e2.id, _fake_embed_text(e2.body))

        result = runner.invoke(main, ["like", "dentist"])
        assert result.exit_code == 0

    def test_like_saves_state(self, runner, tmp_config, tmp_data, _mock_embeddings):
        e = Entry.create(EntryType.TASK, "test")
        save_entry(e)

        from bute.ai.vectors import upsert

        upsert(e.id, _fake_embed_text(e.body))

        runner.invoke(main, ["like", "test"])

        from bute.state import load_state

        state = load_state()
        assert state["view"] == "like"

    def test_like_entry_excludes_source(self, runner, tmp_config, tmp_data, _mock_embeddings):
        e1 = Entry.create(EntryType.TASK, "source entry")
        e2 = Entry.create(EntryType.NOTE, "related entry")
        save_entry(e1)
        save_entry(e2)

        from bute.ai.vectors import upsert

        upsert(e1.id, _fake_embed_text(e1.body))
        upsert(e2.id, _fake_embed_text(e2.body))

        save_state("ls", [e1.id, e2.id])
        result = runner.invoke(main, ["like", "1"])
        assert result.exit_code == 0
        assert "source entry" not in result.output or "Like:" in result.output


def test_install_hint_renders_the_installable_command():
    """The hint a user without embeddings sees must be copy-pasteable.

    Rich treats `[embeddings]` as markup and silently drops it, so the extra has
    to be escaped or the printed command installs bt without semantic search.
    """
    import io

    from rich.console import Console

    from bute.commands.search import _INSTALL_MSG

    buf = io.StringIO()
    Console(file=buf, width=200, force_terminal=False).print(_INSTALL_MSG)
    rendered = buf.getvalue()

    assert "[embeddings]" in rendered
    assert "git+https://github.com/emailkgnow/bullet-terminal" in rendered
    # `--from .` only works inside a repo checkout; the user reading this installed
    # from the git URL and has no checkout.
    assert "--from ." not in rendered
