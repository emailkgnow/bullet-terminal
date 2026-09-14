"""Tests for bt export command."""

import zipfile

from bute.cli import main
from bute.models import Entry, EntryType
from bute.storage import save_entry


def test_export_creates_zip(runner, tmp_config, tmp_data, tmp_path):
    """bt export should create a zip file with entries."""
    e1 = Entry.create(EntryType.TASK, "call dentist")
    save_entry(e1)

    out_dir = tmp_path / "exports"
    out_dir.mkdir()
    result = runner.invoke(main, ["export", "-o", str(out_dir)])
    assert result.exit_code == 0
    assert "Exported" in result.output

    zips = list(out_dir.glob("bullet-terminal-markdown-*.zip"))
    assert len(zips) == 1

    with zipfile.ZipFile(zips[0]) as zf:
        names = zf.namelist()
        assert "entries/README.md" in names
        assert any("entries/" in n for n in names)


def test_export_includes_readme(runner, tmp_config, tmp_data, tmp_path):
    """Export zip should contain a README explaining the structure."""
    e1 = Entry.create(EntryType.TASK, "test entry")
    save_entry(e1)

    out_dir = tmp_path / "exports"
    out_dir.mkdir()
    runner.invoke(main, ["export", "-o", str(out_dir)])

    zips = list(out_dir.glob("*.zip"))
    with zipfile.ZipFile(zips[0]) as zf:
        readme = zf.read("entries/README.md").decode()
        assert "Bullet Terminal" in readme
        assert "entries/" in readme


def test_export_counter_on_duplicate(runner, tmp_config, tmp_data, tmp_path):
    """Second export on same day should get a counter suffix."""
    e1 = Entry.create(EntryType.TASK, "test entry")
    save_entry(e1)

    out_dir = tmp_path / "exports"
    out_dir.mkdir()
    runner.invoke(main, ["export", "-o", str(out_dir)])
    runner.invoke(main, ["export", "-o", str(out_dir)])

    zips = sorted(out_dir.glob("bullet-terminal-markdown-*.zip"))
    assert len(zips) == 2
    assert "-2" in zips[1].name


def test_export_no_data(runner, tmp_config, tmp_data, tmp_path):
    """bt export with no entries should show message."""
    out_dir = tmp_path / "exports"
    out_dir.mkdir()
    result = runner.invoke(main, ["export", "-o", str(out_dir)])
    assert result.exit_code == 0
    assert "No" in result.output


def test_export_default_cwd(runner, tmp_config, tmp_data, monkeypatch, tmp_path):
    """bt export with no -o should write to cwd."""
    e1 = Entry.create(EntryType.TASK, "test entry")
    save_entry(e1)

    monkeypatch.chdir(tmp_path)
    result = runner.invoke(main, ["export"])
    assert result.exit_code == 0
    assert "Exported" in result.output

    zips = list(tmp_path.glob("bullet-terminal-markdown-*.zip"))
    assert len(zips) == 1
