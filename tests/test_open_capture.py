"""Tests for bt t/n/j/c open — editor-based long-form capture."""

from unittest.mock import patch

import frontmatter

from bute.cli import main
from bute.models import Entry, EntryType


def _fake_editor(body="wrote this in the editor", tags=None):
    """Return a subprocess.call mock that writes body into the temp file."""
    def editor_side_effect(cmd, *args, **kwargs):
        path = cmd[1]  # [editor, filepath]
        post = frontmatter.load(path)
        post.content = body
        if tags:
            post.metadata["tags"] = tags
        with open(path, "w") as f:
            f.write(frontmatter.dumps(post))
        return 0
    return editor_side_effect


def test_open_capture_task(runner, tmp_config, tmp_data):
    with patch("subprocess.call", side_effect=_fake_editor("buy groceries")):
        result = runner.invoke(main, ["t", "open"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    assert len(entries) == 1
    content = entries[0].read_text()
    assert "type: task" in content
    assert "buy groceries" in content
    assert "thisweek" in content
    assert "today" in content


def test_open_capture_note(runner, tmp_config, tmp_data):
    with patch("subprocess.call", side_effect=_fake_editor("research notes on OAuth")):
        result = runner.invoke(main, ["n", "open"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    assert len(entries) == 1
    content = entries[0].read_text()
    assert "type: note" in content
    assert "research notes on OAuth" in content


def test_open_capture_journal(runner, tmp_config, tmp_data):
    with patch("subprocess.call", side_effect=_fake_editor("long reflection")):
        result = runner.invoke(main, ["j", "open"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "type: journal" in content


def test_open_capture_calendar(runner, tmp_config, tmp_data):
    with patch("subprocess.call", side_effect=_fake_editor("team offsite")):
        result = runner.invoke(main, ["c", "open"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "type: calendar" in content


def test_open_capture_empty_body_cancels(runner, tmp_config, tmp_data):
    with patch("subprocess.call", side_effect=_fake_editor("")):
        result = runner.invoke(main, ["t", "open"])
    assert result.exit_code == 0
    assert "cancelled" in result.output.lower()
    entries = list(tmp_data.rglob("*.md"))
    assert len(entries) == 0


def test_open_capture_with_tags_from_editor(runner, tmp_config, tmp_data):
    with patch("subprocess.call", side_effect=_fake_editor("tagged entry", tags=["backend", "urgent"])):
        result = runner.invoke(main, ["n", "open"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "backend" in content
    assert "urgent" in content


def test_open_capture_word_signifier(runner, tmp_config, tmp_data):
    with patch("subprocess.call", side_effect=_fake_editor("word form works")):
        result = runner.invoke(main, ["task", "open"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "type: task" in content


def test_open_capture_bullet_signifier(runner, tmp_config, tmp_data):
    with patch("subprocess.call", side_effect=_fake_editor("bullet form works")):
        result = runner.invoke(main, [".", "open"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "type: task" in content


def test_open_capture_important(runner, tmp_config, tmp_data):
    with patch("subprocess.call", side_effect=_fake_editor("urgent thing")):
        result = runner.invoke(main, ["t!", "open"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "important: true" in content


def test_open_capture_cleans_up_temp_file(runner, tmp_config, tmp_data):
    """Temp file should be deleted after editor closes."""
    temp_paths = []

    def capture_path_editor(cmd, *args, **kwargs):
        path = cmd[1]
        temp_paths.append(path)
        post = frontmatter.load(path)
        post.content = "some body"
        with open(path, "w") as f:
            f.write(frontmatter.dumps(post))
        return 0

    with patch("subprocess.call", side_effect=capture_path_editor):
        runner.invoke(main, ["t", "open"])

    import os
    assert len(temp_paths) == 1
    assert not os.path.exists(temp_paths[0])
