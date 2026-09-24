"""Tests for the Textual entry viewer behind `bt <n>`."""

import asyncio
from datetime import date

from textual.widgets import Markdown, Static

from bute.models import Entry, EntryType
from bute.storage import entry_path_from_id, save_entry
from bute.viewer import EntryViewer, meta_markup, prepare_body


def _saved(body, **kw):
    entry = Entry.create(kw.pop("entry_type", EntryType.NOTE), body, **kw)
    save_entry(entry)
    return entry, entry_path_from_id(entry.id)


def _meta_text(app):
    return str(app.query_one("#meta", Static).render())


def _run(app, script):
    async def go():
        async with app.run_test(size=(90, 30)) as pilot:
            await pilot.pause()
            await script(pilot)
    asyncio.run(go())


# --- pure helpers ---

def test_meta_markup_carries_signifier_and_metadata(tmp_config, tmp_data):
    entry = Entry.create(
        EntryType.TASK, "x", important=True, tags=["backend"],
        due=date(2026, 10, 2), repeat="weekly",
    )
    markup = meta_markup(entry)
    assert "!" in markup
    assert ".  task" in markup
    assert "due 2026-10-02" in markup
    assert "repeat weekly" in markup
    assert "@backend" in markup
    assert entry.id[:8] in markup


def test_meta_markup_escapes_rich_markup_in_values(tmp_config, tmp_data):
    entry = Entry.create(EntryType.NOTE, "x", extra_meta={"src": "[red]boom"})
    assert "\\[red]boom" in meta_markup(entry)


def test_prepare_body_renders_task_list_boxes():
    body = "- [ ] open\n- [x] done\n  * [X] nested\nnot [ ] a list"
    assert prepare_body(body) == "- ☐ open\n- ☑ done\n  * ☑ nested\nnot [ ] a list"


# --- app behaviour ---

def test_viewer_shows_entry(tmp_config, tmp_data):
    entry, path = _saved("# Heading\n\nbody text", tags=["retirement"])
    app = EntryViewer([path], on_edit=lambda p: None)

    async def script(pilot):
        assert "@retirement" in _meta_text(app)
        assert app.query_one("#body", Markdown).source == "# Heading\n\nbody text"
        await pilot.press("q")

    _run(app, script)


def test_viewer_steps_between_entries(tmp_config, tmp_data):
    _, first = _saved("first body")
    _, second = _saved("second body")
    app = EntryViewer([first, second], on_edit=lambda p: None)

    async def script(pilot):
        assert "1/2" in _meta_text(app)
        await pilot.press("n")
        assert "2/2" in _meta_text(app)
        assert app.query_one("#body", Markdown).source == "second body"
        await pilot.press("n")  # wraps
        assert "1/2" in _meta_text(app)
        await pilot.press("p")
        assert "2/2" in _meta_text(app)

    _run(app, script)


def test_single_entry_has_no_counter_or_stepping(tmp_config, tmp_data):
    _, path = _saved("only")
    app = EntryViewer([path], on_edit=lambda p: None)

    async def script(pilot):
        assert "1/1" not in _meta_text(app)
        assert app.check_action("step", (1,)) is False

    _run(app, script)


def test_edit_runs_editor_then_reloads(tmp_config, tmp_data, monkeypatch):
    _, path = _saved("before")
    monkeypatch.setenv("EDITOR", "fake-editor")
    calls, edited = [], []

    def fake_editor(cmd, *a, **kw):
        calls.append(cmd)
        path.write_text(path.read_text().replace("before", "after"))
        return 0

    monkeypatch.setattr("bute.viewer.subprocess.call", fake_editor)
    app = EntryViewer([path], on_edit=edited.append)

    async def script(pilot):
        await pilot.press("e")
        await pilot.pause()
        assert calls == [["fake-editor", str(path)]]
        assert edited == [path]
        assert app.query_one("#body", Markdown).source == "after"

    _run(app, script)


def test_edit_defaults_to_nano(tmp_config, tmp_data, monkeypatch):
    _, path = _saved("body")
    monkeypatch.delenv("EDITOR", raising=False)
    calls = []
    monkeypatch.setattr("bute.viewer.subprocess.call", lambda cmd, *a, **kw: calls.append(cmd) or 0)
    app = EntryViewer([path], on_edit=lambda p: None)

    async def script(pilot):
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert calls[0][0] == "nano"

    _run(app, script)


def test_broken_yaml_after_edit_keeps_last_render(tmp_config, tmp_data, monkeypatch):
    _, path = _saved("good body")

    def break_file(cmd, *a, **kw):
        path.write_text("---\ntype: [unclosed\n---\nbody\n")
        return 0

    monkeypatch.setattr("bute.viewer.subprocess.call", break_file)

    def reindex(p):
        raise ValueError("bad yaml")

    app = EntryViewer([path], on_edit=reindex)

    async def script(pilot):
        await pilot.press("e")
        await pilot.pause()
        assert "Could not read entry" in _meta_text(app)
        assert app.query_one("#body", Markdown).source == "good body"
        assert app.is_running

    _run(app, script)
