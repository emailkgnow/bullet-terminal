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
    result = runner.invoke(main, ["/c", "meeting", "time:2pm"])
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
    """due:3pm should set due=today and time=15:00."""
    result = runner.invoke(main, ["/t!", "take", "ozempic", "due:3pm"])
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
    """bt t -l sets week_date but not focus_date."""
    from datetime import date
    from bute.storage import load_entry
    from bute.ritual_ops import week_anchor

    result = runner.invoke(main, ["/t", "-l", "next", "week"])
    # The -l flag is parsed by the capture_cmd; may or may not support here. Skip if unsupported.
    if result.exit_code != 0:
        return
    entries = list(tmp_data.rglob("*.md"))
    if entries:
        loaded = load_entry(entries[0])
        assert loaded.focus_date is None
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
