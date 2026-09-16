"""Tests for bt find command — FTS5 keyword search + tag search."""

from bute.cli import main
from bute.models import Entry, EntryType
from bute.storage import save_entry


def test_find_by_body(runner, tmp_config, tmp_data):
    """bt find should match entries by body text."""
    e1 = Entry.create(EntryType.TASK, "call the dentist tomorrow")
    e2 = Entry.create(EntryType.NOTE, "buy groceries")
    save_entry(e1)
    save_entry(e2)

    result = runner.invoke(main, ["find", "dentist"])
    assert result.exit_code == 0
    assert "dentist" in result.output
    assert "groceries" not in result.output


def test_find_by_tag(runner, tmp_config, tmp_data):
    """bt find should also match entries by tag."""
    e1 = Entry.create(EntryType.TASK, "some task", tags=["backend"])
    e2 = Entry.create(EntryType.TASK, "other task", tags=["frontend"])
    save_entry(e1)
    save_entry(e2)

    result = runner.invoke(main, ["find", "backend"])
    assert result.exit_code == 0
    assert "some task" in result.output
    assert "other task" not in result.output


def test_find_type_filter(runner, tmp_config, tmp_data):
    """bt find -t should only return tasks."""
    e1 = Entry.create(EntryType.TASK, "fix the dentist appointment")
    e2 = Entry.create(EntryType.NOTE, "dentist office hours")
    save_entry(e1)
    save_entry(e2)

    result = runner.invoke(main, ["find", "-t", "dentist"])
    assert result.exit_code == 0
    assert "fix the" in result.output
    assert "office hours" not in result.output


def test_find_no_results(runner, tmp_config, tmp_data):
    """bt find with no matches shows message."""
    e1 = Entry.create(EntryType.TASK, "something else")
    save_entry(e1)

    result = runner.invoke(main, ["find", "xyznonexistent"])
    assert result.exit_code == 0
    assert "No entries found" in result.output


def test_find_saves_state(runner, tmp_config, tmp_data):
    """bt find should save state for number-action follow-up."""
    e1 = Entry.create(EntryType.TASK, "call the dentist")
    save_entry(e1)

    runner.invoke(main, ["find", "dentist"])

    from bute.state import load_state
    state = load_state()
    assert state["view"] == "find"


def test_find_deduplicates_body_and_tag(runner, tmp_config, tmp_data):
    """Entry matching both body and tag should appear only once."""
    e1 = Entry.create(EntryType.TASK, "fix backend api", tags=["backend"])
    save_entry(e1)

    result = runner.invoke(main, ["find", "backend"])
    assert result.exit_code == 0
    # Should appear once, not twice
    assert result.output.count("fix backend api") == 1


# ---------------------------------------------------------------------------
# Partial-word matching — prefix (tier 1) then substring fallback (tier 2)
# ---------------------------------------------------------------------------

def test_find_matches_word_prefix(runner, tmp_config, tmp_data):
    """bt find dent should match 'dentist' — prefix, no trailing * needed."""
    save_entry(Entry.create(EntryType.TASK, "call the dentist tomorrow"))
    save_entry(Entry.create(EntryType.NOTE, "buy groceries"))

    result = runner.invoke(main, ["find", "dent"])
    assert result.exit_code == 0
    assert "dentist" in result.output
    assert "groceries" not in result.output


def test_find_matches_mid_word_fragment(runner, tmp_config, tmp_data):
    """bt find ntist should match 'dentist' via the substring fallback."""
    save_entry(Entry.create(EntryType.TASK, "call the dentist tomorrow"))
    save_entry(Entry.create(EntryType.NOTE, "buy groceries"))

    result = runner.invoke(main, ["find", "ntist"])
    assert result.exit_code == 0
    assert "dentist" in result.output
    assert "groceries" not in result.output


def test_find_prefers_prefix_matches_over_substring(runner, tmp_config, tmp_data):
    """When the prefix tier finds results, the substring tier stays out of it."""
    save_entry(Entry.create(EntryType.NOTE, "catalog of books"))
    save_entry(Entry.create(EntryType.NOTE, "plan the vacation"))

    result = runner.invoke(main, ["find", "cat"])
    assert result.exit_code == 0
    assert "catalog" in result.output
    assert "vacation" not in result.output


def test_find_multi_word_requires_all_fragments(runner, tmp_config, tmp_data):
    """Every token must match — 'oauth doc' finds the entry with both."""
    save_entry(Entry.create(EntryType.NOTE, "review the OAuth documentation"))
    save_entry(Entry.create(EntryType.NOTE, "OAuth token lifetime"))

    result = runner.invoke(main, ["find", "oauth", "doc"])
    assert result.exit_code == 0
    assert "documentation" in result.output
    assert "token lifetime" not in result.output


def test_find_matches_tag_fragment(runner, tmp_config, tmp_data):
    """bt find health should match the @healthcare tag."""
    save_entry(Entry.create(EntryType.TASK, "renew the policy", tags=["healthcare"]))
    save_entry(Entry.create(EntryType.TASK, "unrelated errand", tags=["chores"]))

    result = runner.invoke(main, ["find", "health"])
    assert result.exit_code == 0
    assert "renew the policy" in result.output
    assert "unrelated errand" not in result.output


def test_find_survives_fts_operator_characters(runner, tmp_config, tmp_data):
    """Queries containing FTS5 syntax characters must not raise."""
    save_entry(Entry.create(EntryType.NOTE, "learning c++ templates"))

    for query in ["c++", 'he said "hi', "foo OR", "a-b", "*"]:
        result = runner.invoke(main, ["find", query])
        assert result.exit_code == 0, f"{query!r} raised: {result.exception!r}"


def test_find_substring_respects_type_filter(runner, tmp_config, tmp_data):
    """The substring fallback honours -t/-n/-j/-c like the prefix tier does."""
    save_entry(Entry.create(EntryType.TASK, "book the dentist"))
    save_entry(Entry.create(EntryType.NOTE, "dentist office hours"))

    result = runner.invoke(main, ["find", "-t", "ntist"])
    assert result.exit_code == 0
    assert "book the" in result.output
    assert "office hours" not in result.output


# ---------------------------------------------------------------------------
# Match snippets
# ---------------------------------------------------------------------------

def test_match_snippet_returns_line_containing_match():
    from bute.display import match_snippet

    body = "Weekly planning notes\n\nremember to renew the passport\n\nother stuff"
    snippet = match_snippet(body, ["passp"])
    assert snippet is not None
    assert "passport" in snippet


def test_match_snippet_skipped_when_match_is_in_first_line():
    from bute.display import match_snippet

    body = "renew the passport\n\nother stuff"
    assert match_snippet(body, ["passp"]) is None


def test_match_snippet_when_match_is_past_the_first_sentence():
    """The title shows only the first sentence, so a later match needs a snippet."""
    from bute.display import match_snippet

    body = "i'm feeling a bit down. we fought about ten days ago."
    snippet = match_snippet(body, ["ten"])
    assert snippet is not None
    assert "ten days ago" in snippet


def test_match_snippet_when_match_is_past_the_title_truncation():
    """A long unpunctuated first line is truncated in the title; later hits need a snippet."""
    from bute.display import match_snippet

    body = "padding words " * 8 + "needle at the end"
    assert match_snippet(body, ["needle"]) is not None


def test_match_snippet_windows_long_lines():
    from bute.display import match_snippet

    body = "title line\n" + ("padding words " * 30) + "needle " + ("more words " * 30)
    snippet = match_snippet(body, ["needle"])
    assert snippet is not None
    assert "needle" in snippet
    assert len(snippet) < 120


def test_match_snippet_returns_none_without_match():
    from bute.display import match_snippet

    assert match_snippet("title\nbody text", ["absent"]) is None


def test_find_shows_snippet_for_deep_match(runner, tmp_config, tmp_data):
    """A match buried in a long note surfaces its surrounding line."""
    body = "Weekly planning notes\n\nremember to renew the passport before travel"
    save_entry(Entry.create(EntryType.NOTE, body))

    result = runner.invoke(main, ["find", "passp"])
    assert result.exit_code == 0
    assert "passport" in result.output


def test_find_json_output_has_no_snippets(runner, tmp_config, tmp_data):
    """--json keeps its {view, entries} shape; snippets are display-only."""
    import json

    save_entry(Entry.create(EntryType.NOTE, "title\n\nthe dentist visit"))

    result = runner.invoke(main, ["find", "--json", "dent"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert set(payload) == {"view", "entries"}
    assert len(payload["entries"]) == 1


# ---------------------------------------------------------------------------
# Match highlighting
# ---------------------------------------------------------------------------

def test_term_spans_cover_the_whole_word():
    """A partial term selects the full word, not just the matched letters."""
    from bute.display import _term_spans

    text = "renew the passport"
    assert [text[a:b] for a, b in _term_spans(text, ["passp"])] == ["passport"]
    assert [text[a:b] for a, b in _term_spans(text, ["sspor"])] == ["passport"]


def test_term_spans_merge_adjacent_matches():
    from bute.display import _term_spans

    text = "call the dentist today"
    spans = _term_spans(text, ["dent", "today"])
    assert [text[a:b] for a, b in spans] == ["dentist", "today"]


def test_term_spans_empty_without_match():
    from bute.display import _term_spans

    assert _term_spans("nothing here", ["absent"]) == []
    assert _term_spans("nothing here", []) == []


def test_highlight_terms_colors_whole_word():
    from bute.display import _highlight_terms

    out = _highlight_terms("renew the passport", ["passp"])
    assert "[bold yellow]passport[/bold yellow]" in out


def test_highlight_terms_renders_literal_brackets():
    """Markup-looking text in an entry stays literal after highlighting."""
    from rich.console import Console
    from bute.display import _highlight_terms

    console = Console(file=None, width=60)
    with console.capture() as cap:
        console.print(_highlight_terms("a [bold] dentist", ["dent"]), highlight=False)
    assert "[bold] dentist" in cap.get()


def test_entry_row_styles_the_matching_word_in_the_title():
    """The matching word in the entry's first line carries the match style."""
    from bute.display import _MATCH_STYLE, _build_entry_row

    entry = Entry.create(EntryType.NOTE, "call the dentist")
    _, _, body, _ = _build_entry_row(1, entry, terms=["dent"])

    styled = [
        str(body)[span.start:span.end]
        for span in body.spans
        if span.style == _MATCH_STYLE
    ]
    assert styled == ["dentist"]


def test_entry_row_without_terms_has_no_match_style():
    from bute.display import _MATCH_STYLE, _build_entry_row

    entry = Entry.create(EntryType.NOTE, "call the dentist")
    _, _, body, _ = _build_entry_row(1, entry)
    assert all(span.style != _MATCH_STYLE for span in body.spans)
