"""Tests that the help surfaces describe what bt find actually does."""

from bute.cli import main


def test_help_table_advertises_partial_word_search(runner, tmp_config, tmp_data):
    """bt -h should say find matches partial words, not just 'keyword search'."""
    result = runner.invoke(main, ["-h"])
    assert result.exit_code == 0
    assert "partial" in result.output.lower()


def test_find_help_shows_a_partial_word_example(runner, tmp_config, tmp_data):
    """bt find --help should demonstrate the fragment match."""
    result = runner.invoke(main, ["find", "--help"])
    assert result.exit_code == 0
    output = result.output.lower()
    assert "partial" in output
    assert "dentist" in output
