"""Entry bodies must survive Rich's markup parser.

Rich eats square brackets in any plain string it renders: `[[deep work]]` comes
out as `[]`. Bodies are user-authored — and the data dir sits inside an Obsidian
vault, where `[[wikilinks]]` are normal — so every site that interpolates a body
into markup has to escape it first.
"""

from datetime import date

from bute.display import (
    console,
    display_action_confirmation,
    display_habit_line_entries,
)
from bute.models import Entry, EntryType

BRACKETED = "read [[deep work]] chapter 3"


def _render(fn, *args, **kwargs) -> str:
    with console.capture() as cap:
        fn(*args, **kwargs)
    return cap.get()


def test_action_confirmation_keeps_brackets():
    entry = Entry.create(EntryType.TASK, BRACKETED)

    out = _render(display_action_confirmation, entry, "done")

    assert "[[deep work]]" in out
    assert "[done]" in out


def test_habit_line_keeps_brackets():
    entry = Entry.create(EntryType.TASK, BRACKETED)

    out = _render(display_habit_line_entries, [entry], date.today())

    assert "[[deep work]]" in out


def test_numbered_habit_rows_keep_brackets():
    entry = Entry.create(EntryType.TASK, BRACKETED)

    out = _render(display_habit_line_entries, [entry], date.today(), start_num=1)

    assert "[[deep work]]" in out


def test_a_real_style_name_in_a_body_is_not_applied():
    """A body containing `[red]` must print it, not turn the rest red."""
    entry = Entry.create(EntryType.TASK, "mark [red] flag")

    out = _render(display_action_confirmation, entry, "done")

    assert "[red]" in out


def test_search_title_keeps_brackets():
    """`bt find` puts the user's query in the title: Find: "[[deep work]]"."""
    from bute.display import display_entry_list

    out = _render(display_entry_list, [], 'Find: "[[deep work]]"')

    assert "[[deep work]]" in out


def test_configured_habit_names_keep_brackets():
    from bute.display import display_habit_line

    out = _render(display_habit_line, {"read [[daily]]": True}, ["read [[daily]]"])

    assert "[[daily]]" in out
