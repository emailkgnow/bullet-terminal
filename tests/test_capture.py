"""End-to-end tests for the capture command."""

from bute.cli import main


def test_capture_task(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["/t", "call", "dentist"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    assert len(entries) == 1


def test_capture_with_metadata(runner, tmp_config, tmp_data):
    result = runner.invoke(
        main, ["/t!", "fix", "bug", "due:tomorrow", "@backend"]
    )
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "important: true" in content
    assert "backend" in content
    assert "fix bug" in content


def test_capture_note(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["/n", "API", "uses", "OAuth2"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "type: note" in content


def test_capture_journal(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["/j", "feeling", "good"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "type: journal" in content


def test_capture_calendar(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["/c", "meeting", "time:2:00pm"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "type: calendar" in content
    assert "time: '14:00'" in content


def test_capture_preserves_colon_in_body(runner, tmp_config, tmp_data):
    """1:1 should stay as body text, not be parsed as key:value."""
    result = runner.invoke(main, ["/c", "1:1", "with", "Ahmed"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "1:1 with Ahmed" in content


def test_capture_multiple_tags(runner, tmp_config, tmp_data):
    result = runner.invoke(
        main, ["/t", "review", "PR", "@backend", "@code-review"]
    )
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "backend" in content
    assert "code-review" in content


def test_capture_due_time_sets_today(runner, tmp_config, tmp_data):
    """due:3:00pm should set due=today and time=15:00."""
    result = runner.invoke(main, ["/t!", "take", "ozempic", "due:3:00pm"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    content = entries[0].read_text()
    assert "time: '15:00'" in content
    assert "take ozempic" in content


def test_capture_plus_token_creates_entry(runner, tmp_config, tmp_data):
    """bt t fix faucet +home-reno should create an entry (not redirect to collection)."""
    result = runner.invoke(main, ["t", "fix", "faucet", "+home-reno"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    assert len(entries) == 1
    content = entries[0].read_text()
    assert "fix faucet +home-reno" in content


def test_capture_task_sets_focus_and_week_dates(runner, tmp_config, tmp_data):
    """Capturing a task (no flags, no future date) sets focus_date=today and week_date=monday."""
    from datetime import date
    from bute.storage import load_entry
    from bute.ritual_ops import week_anchor

    result = runner.invoke(main, ["/t", "do", "a", "thing"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    assert len(entries) == 1
    loaded = load_entry(entries[0])
    assert loaded.focus_date == date.today()
    assert loaded.week_date == week_anchor()


def test_capture_task_later_flag_sets_week_date_only(runner, tmp_config, tmp_data):
    """The -l flag is gone; it's now written into the body text as part of normal capture."""
    from datetime import date
    from bute.storage import load_entry
    from bute.ritual_ops import week_anchor

    result = runner.invoke(main, ["/t", "-l", "next", "week"])
    # -l is no longer an option, so it gets written into the body.
    # Since there's no future date, a normal capture sets both focus_date and week_date.
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    assert len(entries) == 1
    loaded = load_entry(entries[0])
    # Both should be set because -l in the body doesn't trigger special behavior anymore
    assert loaded.focus_date == date.today()
    assert loaded.week_date == week_anchor()


def test_capture_note_has_no_focus_dates(runner, tmp_config, tmp_data):
    """Non-task captures don't set focus_date or week_date."""
    from bute.storage import load_entry

    result = runner.invoke(main, ["/n", "just", "a", "note"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    loaded = load_entry(entries[0])
    assert loaded.focus_date is None
    assert loaded.week_date is None


def test_capture_does_not_embed(runner, tmp_config, tmp_data, monkeypatch):
    """Capture must never load the embedding model — bt like backfills lazily.

    Spies on the actual ONNX model constructor (`_get_model`, the lowest
    point in bute.ai.embeddings where the model is built) rather than
    raising from it: the old capture-path embed helper (since removed)
    wrapped its call in a bare `except Exception`, so a raising mock was
    silently swallowed and the test would pass regardless of whether the
    model was ever loaded. A
    call-count spy proves the real thing: zero calls means capture never
    touched the model.
    """
    import bute.ai.embeddings as emb

    calls = []
    monkeypatch.setattr(emb, "_get_model", lambda: calls.append(1))
    result = runner.invoke(main, ["t", "fast", "capture"])
    assert result.exit_code == 0, result.output
    assert "fast capture" in result.output
    assert calls == [], "capture must not load the embedding model"


def test_capture_confirmation_shows_extra_meta(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["t", "call", "bank", "project:alpha"])
    assert result.exit_code == 0, result.output
    assert "project:alpha" in result.output


def test_capture_confirmation_safe_with_rich_markup_in_extra_meta(runner, tmp_config, tmp_data):
    """Verify capture confirmation handles Rich markup characters in extra_meta without crashing or escaping visibly."""
    # Test with unmatched closing tag — would crash if not escaped
    result = runner.invoke(main, ["t", "call", "bank", "key:[/]"])
    assert result.exit_code == 0, result.output
    # Confirmation should show the literal value (with escaped brackets, but that's internal)
    assert "key:" in result.output
    # Confirm no stray backslashes visible (Text() doesn't show escape chars)
    assert "\\[" not in result.output


def test_capture_week_flag_sets_week_date_only(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    result = runner.invoke(main, ["t", "-w", "research", "flights"])
    assert result.exit_code == 0, result.output
    entry = query_and_load(type="task")[0]
    assert entry.week_date is not None
    assert entry.focus_date is None


def test_capture_backlog_flag_sets_neither(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    result = runner.invoke(main, ["t", "-b", "someday", "idea"])
    assert result.exit_code == 0, result.output
    entry = query_and_load(type="task")[0]
    assert entry.week_date is None
    assert entry.focus_date is None


def test_capture_bare_sets_both(runner, tmp_config, tmp_data):
    from datetime import date
    from bute.storage import query_and_load

    result = runner.invoke(main, ["t", "call", "dentist"])
    assert result.exit_code == 0, result.output
    entry = query_and_load(type="task")[0]
    assert entry.focus_date == date.today()
    assert entry.week_date is not None


def test_capture_rejects_all_flag(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    result = runner.invoke(main, ["t", "-a", "buy", "milk"])
    assert result.exit_code != 0
    assert "-w" in result.output and "-b" in result.output
    assert query_and_load(type="task") == []


def test_later_flag_is_gone(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    runner.invoke(main, ["t", "-l", "research", "flights"])
    # -l is no longer an option; it must not silently set week_date only.
    entries = query_and_load(type="task")
    assert not any(e.week_date is not None and e.focus_date is None for e in entries)
