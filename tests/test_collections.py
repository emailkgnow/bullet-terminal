"""Tests for collections storage and commands."""

from bute.cli import main
from bute.collection_storage import (
    append_to_collection,
    list_collections_with_meta,
    load_collection,
    save_collection,
)
from bute.config import default_config, save_config


# --- Storage tests ---


def test_save_and_load_raw_collection(tmp_data):
    save_collection("test", "raw", {"input": "- . item one\n- . item two\n"})
    coll = load_collection("test")
    assert coll is not None
    assert coll["stage"] == "raw"
    assert coll["input_content"] == "- . item one\n- . item two\n"
    assert coll["analysis_content"] is None
    assert coll["tasks_content"] is None


def test_save_analyzed_collection(tmp_data):
    sections = {
        "input": "- . item one\n",
        "analysis": "**Theme A**\n- item one\n",
    }
    save_collection("test", "analyzed", sections)
    coll = load_collection("test")
    assert coll["stage"] == "analyzed"
    assert coll["input_content"] == "- . item one\n"
    assert coll["analysis_content"] == "**Theme A**\n- item one\n"
    assert coll["tasks_content"] is None


def test_save_executed_collection(tmp_data):
    sections = {
        "input": "- . item one\n",
        "analysis": "**Theme A**\n- item one\n",
        "tasks": "1. Do the thing\n2. Do the other thing\n",
    }
    save_collection("test", "executed", sections)
    coll = load_collection("test")
    assert coll["stage"] == "executed"
    assert coll["input_content"] is not None
    assert coll["analysis_content"] is not None
    assert coll["tasks_content"] == "1. Do the thing\n2. Do the other thing\n"


def test_load_missing_collection(tmp_data):
    assert load_collection("nonexistent") is None


def test_append_to_raw_collection(tmp_data):
    save_collection("test", "raw", {"input": "- . existing item\n"})
    append_to_collection("test", ["- . new item"])
    coll = load_collection("test")
    assert "existing item" in coll["input_content"]
    assert "new item" in coll["input_content"]


def test_append_creates_new_collection(tmp_data):
    append_to_collection("fresh", ["- . first item"])
    coll = load_collection("fresh")
    assert coll is not None
    assert coll["stage"] == "raw"
    assert "first item" in coll["input_content"]


def test_append_rejects_analyzed_collection(tmp_data):
    sections = {
        "input": "- . item\n",
        "analysis": "**Theme**\n- item\n",
    }
    save_collection("test", "analyzed", sections)
    result = append_to_collection("test", ["- . new item"])
    assert result is None  # rejected


def test_list_collections_with_meta(tmp_data):
    save_collection("alpha", "raw", {"input": "- . a\n- . b\n"})
    save_collection("beta", "analyzed", {
        "input": "- . c\n",
        "analysis": "**Theme**\n- c\n",
    })
    meta = list_collections_with_meta()
    names = [m["name"] for m in meta]
    assert "alpha" in names
    assert "beta" in names
    alpha = next(m for m in meta if m["name"] == "alpha")
    assert alpha["stage"] == "raw"
    assert alpha["item_count"] == 2


# --- Capture integration tests ---


def _setup(tmp_config, tmp_data):
    doc = default_config(provider="anthropic")
    doc["ai"]["api_key"] = "sk-test"
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


def test_capture_with_collection(runner, tmp_config, tmp_data):
    """bt t fix faucet +home-reno → adds to collection, no entry created."""
    _setup(tmp_config, tmp_data)
    result = runner.invoke(main, ["t", "fix", "faucet", "+home-reno"])
    assert result.exit_code == 0
    assert "+home-reno" in result.output

    coll = load_collection("home-reno")
    assert coll is not None
    assert "fix faucet" in coll["input_content"]

    # No entry should be created
    from bute.storage import load_entries_by_filter
    entries = load_entries_by_filter(lambda e: True)
    assert len(entries) == 0


def test_capture_with_collection_preserves_signifier(runner, tmp_config, tmp_data):
    """Signifier bullet is preserved in collection item."""
    _setup(tmp_config, tmp_data)
    runner.invoke(main, ["t", "fix", "faucet", "+test-coll"])
    runner.invoke(main, ["n", "kitchen", "is", "12x15", "+test-coll"])

    coll = load_collection("test-coll")
    assert ". fix faucet" in coll["input_content"]
    assert "- kitchen is 12x15" in coll["input_content"]


def test_capture_with_collection_preserves_tags_and_meta(runner, tmp_config, tmp_data):
    """Tags and metadata are preserved in the raw line."""
    _setup(tmp_config, tmp_data)
    runner.invoke(main, ["t", "fix", "faucet", "+test-coll", "@plumbing", "due:friday"])

    coll = load_collection("test-coll")
    content = coll["input_content"]
    assert "fix faucet" in content
    assert "@plumbing" in content
    assert "due:friday" in content


# --- Prompt tests ---


from bute.ai.prompts import analyze_prompt, execute_prompt


def test_analyze_prompt_contains_signifier_key():
    prompt = analyze_prompt()
    assert ". = task" in prompt
    assert "- = note" in prompt
    assert "= = journal" in prompt
    assert "o = calendar" in prompt


def test_execute_prompt_contains_sequencing():
    prompt = execute_prompt()
    assert "sequen" in prompt.lower()
    assert "verb" in prompt.lower()


# --- Command tests ---

from unittest.mock import MagicMock, patch

import pytest

from bute.ai.llm import reset as reset_llm


@pytest.fixture(autouse=True)
def _reset_llm_state():
    """Reset LLM client singleton between tests."""
    reset_llm()
    yield
    reset_llm()


def _mock_llm(response="**Theme A**\n- item one\n- item two"):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = response
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    return patch("bute.ai.llm._get_client", return_value=mock_client)


def test_analyze_raw_collection(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    save_collection("test", "raw", {"input": "- . item one\n- . item two\n"})

    with _mock_llm("**Theme A**\n- item one\n- item two"):
        result = runner.invoke(main, ["+test", "analyze"], input="y\n")

    assert result.exit_code == 0
    coll = load_collection("test")
    assert coll["stage"] == "analyzed"
    assert coll["analysis_content"] is not None
    assert coll["input_content"] is not None  # preserved


def test_analyze_rejects_already_analyzed(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    save_collection("test", "analyzed", {
        "input": "- . item\n",
        "analysis": "**Theme**\n- item\n",
    })

    result = runner.invoke(main, ["+test", "analyze"])
    assert "already analyzed" in result.output.lower()


def test_execute_analyzed_collection(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    save_collection("test", "analyzed", {
        "input": "- . item one\n",
        "analysis": "**Theme A**\n- item one\n",
    })

    with _mock_llm("1. Create the landing page\n2. Write unit tests"):
        result = runner.invoke(main, ["+test", "execute"], input="y\n")

    assert result.exit_code == 0

    # Verify tasks were created
    from bute.models import EntryType
    from bute.storage import load_entries_by_filter
    tasks = load_entries_by_filter(lambda e: e.type == EntryType.TASK)
    task_bodies = [t.body for t in tasks]
    assert "Create the landing page" in task_bodies
    assert "Write unit tests" in task_bodies

    # Verify collection metadata on tasks
    for t in tasks:
        assert t.extra_meta.get("collection") == "test"
        assert "test" in t.tags

    # Verify collection stage
    coll = load_collection("test")
    assert coll["stage"] == "executed"
    assert coll["tasks_content"] is not None


def test_execute_raw_runs_analyze_first(runner, tmp_config, tmp_data):
    """Execute on raw collection should analyze first, then generate tasks."""
    _setup(tmp_config, tmp_data)
    save_collection("test", "raw", {"input": "- . item one\n"})

    # First call returns analysis, second returns tasks
    analyze_response = "**Theme A**\n- item one"
    task_response = "1. Do the thing"

    mock_resp_1 = MagicMock()
    mock_resp_1.choices = [MagicMock()]
    mock_resp_1.choices[0].message.content = analyze_response

    mock_resp_2 = MagicMock()
    mock_resp_2.choices = [MagicMock()]
    mock_resp_2.choices[0].message.content = task_response

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [mock_resp_1, mock_resp_2]

    with patch("bute.ai.llm._get_client", return_value=mock_client):
        result = runner.invoke(main, ["+test", "execute"], input="y\ny\n")

    assert result.exit_code == 0
    coll = load_collection("test")
    assert coll["stage"] == "executed"


def test_collections_list(runner, tmp_config, tmp_data):
    """bt collections shows all collections."""
    _setup(tmp_config, tmp_data)
    save_collection("alpha", "raw", {"input": "- . a\n- . b\n"})
    save_collection("beta", "analyzed", {
        "input": "- . c\n",
        "analysis": "**Theme**\n- c\n",
    })

    result = runner.invoke(main, ["collections"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output
