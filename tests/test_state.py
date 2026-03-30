"""Tests for state management (view-to-action bridge)."""

import pytest

from bute.errors import InvalidEntryNumberError, StateNotFoundError
from bute.state import is_recap_done_today, load_state, mark_recap_done, resolve_numbers, save_state, state_path


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


def test_mark_recap_done(tmp_data):
    mark_recap_done()
    assert is_recap_done_today()


def test_recap_not_done_initially(tmp_data):
    assert not is_recap_done_today()
