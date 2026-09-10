"""Tests for state management (view-to-action bridge)."""

import pytest

from bute.errors import InvalidEntryNumberError, StateNotFoundError
from bute.state import load_state, resolve_numbers, save_state, state_path


def test_state_path(tmp_data):
    path = state_path()
    assert str(path).endswith(".state.json")


def test_save_and_load_roundtrip(tmp_data):
    ids = ["AAAA", "BBBB", "CCCC"]
    save_state("ls", ids)
    state = load_state()
    assert state["view"] == "ls"
    assert state["entries"] == ids


def test_save_overwrites(tmp_data):
    save_state("ls", ["A"])
    save_state("active", ["B", "C"])
    state = load_state()
    assert state["view"] == "active"
    assert state["entries"] == ["B", "C"]


def test_load_missing_raises(tmp_data):
    with pytest.raises(StateNotFoundError):
        load_state()


def test_resolve_numbers_single(tmp_data):
    save_state("ls", ["AAA", "BBB", "CCC"])
    result = resolve_numbers([2])
    assert result == ["BBB"]


def test_resolve_numbers_multiple(tmp_data):
    save_state("ls", ["AAA", "BBB", "CCC"])
    result = resolve_numbers([1, 3])
    assert result == ["AAA", "CCC"]


def test_resolve_numbers_out_of_range(tmp_data):
    save_state("ls", ["AAA", "BBB"])
    with pytest.raises(InvalidEntryNumberError):
        resolve_numbers([5])


def test_resolve_numbers_zero(tmp_data):
    save_state("ls", ["AAA"])
    with pytest.raises(InvalidEntryNumberError):
        resolve_numbers([0])




# --- Journal whisper history (recently-shown ring buffer) ---


def test_journal_history_empty_by_default(tmp_data):
    from bute.state import get_journal_history

    assert get_journal_history() == []


def test_record_journal_shown_appends(tmp_data):
    from bute.state import get_journal_history, record_journal_shown

    record_journal_shown("A")
    record_journal_shown("B")
    assert get_journal_history() == ["A", "B"]


def test_journal_history_caps_at_limit(tmp_data):
    from bute.state import JOURNAL_HISTORY_LIMIT, get_journal_history, record_journal_shown

    ids = [f"ID{i:03d}" for i in range(JOURNAL_HISTORY_LIMIT + 10)]
    for entry_id in ids:
        record_journal_shown(entry_id)
    history = get_journal_history()
    assert len(history) == JOURNAL_HISTORY_LIMIT
    assert history == ids[-JOURNAL_HISTORY_LIMIT:]


def test_record_journal_shown_moves_repeat_to_end(tmp_data):
    from bute.state import get_journal_history, record_journal_shown

    record_journal_shown("A")
    record_journal_shown("B")
    record_journal_shown("A")
    assert get_journal_history() == ["B", "A"]
