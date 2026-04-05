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


def test_capture_plus_token_creates_entry(runner, tmp_config, tmp_data):
    """bt t fix faucet +home-reno should create an entry (not redirect to collection)."""
    result = runner.invoke(main, ["t", "fix", "faucet", "+home-reno"])
    assert result.exit_code == 0
    entries = list(tmp_data.rglob("*.md"))
    assert len(entries) == 1
    content = entries[0].read_text()
    assert "fix faucet +home-reno" in content
