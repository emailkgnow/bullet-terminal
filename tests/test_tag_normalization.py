"""Tags are always stored and matched in lowercase."""

from bute.commands.action import handle_add_tag
from bute.commands.tags import _parse_tag_tokens
from bute.models import Entry, EntryType
from bute.storage import load_entry, save_entry


def test_add_tag_action_lowercases(tmp_data):
    entry = Entry.create(EntryType.TASK, "fix bug")
    save_entry(entry)
    handle_add_tag(entry, "Backend", None)
    assert entry.tags == ["backend"]


def test_add_tag_action_treats_case_variant_as_duplicate(tmp_data):
    entry = Entry.create(EntryType.TASK, "fix bug", tags=["backend"])
    save_entry(entry)
    handle_add_tag(entry, "Backend", None)
    assert entry.tags == ["backend"]


def test_filter_tokens_are_lowercased():
    include, exclude = _parse_tag_tokens(("@Elham", "-@Done"))
    assert include == ["elham"]
    assert exclude == ["done"]


def test_externally_written_uppercase_tag_loads_lowercase(tmp_data):
    """BYOAI: an external agent may write tags: [Elham] straight into a .md file."""
    entry = Entry.create(EntryType.JOURNAL, "lunch with Elham", tags=["placeholder"])
    path = save_entry(entry)
    path.write_text(path.read_text().replace("placeholder", "Elham"))
    assert load_entry(path).tags == ["elham"]


def test_cli_tag_filter_is_case_insensitive(runner, tmp_config, tmp_data):
    """bt @Elham must find entries tagged elham."""
    from bute.cli import main
    from bute.config import default_config, save_config

    doc = default_config()
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)
    save_entry(Entry.create(EntryType.JOURNAL, "lunch with Elham", tags=["elham"]))

    result = runner.invoke(main, ["@Elham"])
    assert result.exit_code == 0
    assert "lunch with Elham" in result.output


def test_help_documents_double_duty_tags(runner, tmp_config, tmp_data):
    """bt -h should teach @@tag, not just @tag."""
    from bute.cli import main

    result = runner.invoke(main, ["-h"])
    assert result.exit_code == 0
    assert "@@tag" in result.output
    assert "double duty" in result.output.lower()
