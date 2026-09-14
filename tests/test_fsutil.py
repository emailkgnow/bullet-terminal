"""Tests for atomic file writes."""

from pathlib import Path

from bute.fsutil import atomic_write_text


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "sub" / "entry.md"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"


def test_atomic_write_overwrites_existing(tmp_path):
    target = tmp_path / "entry.md"
    target.write_text("old")
    atomic_write_text(target, "new")
    assert target.read_text() == "new"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    target = tmp_path / "entry.md"
    atomic_write_text(target, "x")
    leftovers = [p for p in tmp_path.iterdir() if p.name != "entry.md"]
    assert leftovers == []


def test_atomic_write_failure_keeps_original(tmp_path, monkeypatch):
    import os
    target = tmp_path / "entry.md"
    target.write_text("original")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    try:
        atomic_write_text(target, "partial")
    except OSError:
        pass
    assert target.read_text() == "original"
    leftovers = [p for p in tmp_path.iterdir() if p.name != "entry.md"]
    assert leftovers == []
