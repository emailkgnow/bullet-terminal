"""The generated README is the contract external AI agents read.

If it documents frontmatter keys bt does not actually parse, agents write
entries bt silently misreads — so the documented example is round-tripped
through bt's own loader here.
"""

import re

import pytest

from bute.guide import generate_readme, write_guide
from bute.storage import load_entry


def documented_example(tmp_path) -> str:
    """Pull the entry-format YAML example out of the generated README."""
    readme = generate_readme(tmp_path)
    block = re.search(r"## Entry format.*?```yaml\n(.*?)```", readme, re.S)
    assert block, "README no longer contains an entry-format example"
    return block.group(1)


def test_documented_example_round_trips_through_bt(tmp_path):
    example = documented_example(tmp_path)
    entry_file = tmp_path / "example.md"
    entry_file.write_text(example + "\nThe entry body goes here.\n")

    entry = load_entry(entry_file)

    assert entry.scheduled_date is not None, (
        "README documents a scheduled date key that load_entry does not read"
    )
    assert entry.scheduled_time is not None, (
        "README documents a scheduled time key that load_entry does not read"
    )


def test_documented_example_uses_the_keys_storage_reads(tmp_path):
    example = documented_example(tmp_path)

    assert re.search(r"^date:", example, re.M), "expected a `date:` key"
    assert re.search(r"^time:", example, re.M), "expected a `time:` key"
    assert not re.search(r"^scheduled_date:", example, re.M)
    assert not re.search(r"^scheduled_time:", example, re.M)
