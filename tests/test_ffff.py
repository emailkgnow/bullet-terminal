"""Tests for FFFF pipeline commands and collection storage."""

from unittest.mock import MagicMock, patch

from bute.cli import main
from bute.collection_storage import list_collections, load_collection, save_collection
from bute.config import default_config, save_config


def _setup(tmp_config, tmp_data):
    doc = default_config(provider="anthropic")
    doc["ai"]["api_key"] = "sk-test"
    doc["core"]["data_dir"] = str(tmp_data)
    save_config(doc)


def _mock_llm(response="- item one\n- item two"):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = response
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    return patch("dwn.ai.llm._get_client", return_value=mock_client)


# --- Collection storage tests ---


def test_save_and_load_collection(tmp_data):
    save_collection("test", "raw", "- item one\n- item two\n")
    coll = load_collection("test")
    assert coll is not None
    assert coll["stage"] == "raw"
    assert "item one" in coll["items"]
    assert "item two" in coll["items"]


def test_load_missing_collection(tmp_data):
    assert load_collection("nonexistent") is None


def test_list_collections(tmp_data):
    save_collection("alpha", "raw", "- a\n")
    save_collection("beta", "formed", "- b\n")
    names = list_collections()
    assert "alpha" in names
    assert "beta" in names


# --- FFFF command tests ---


def test_find_with_args(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    result = runner.invoke(main, ["find", "test-project", "idea one", "idea two"])
    assert result.exit_code == 0
    assert "2 items added" in result.output

    coll = load_collection("test-project")
    assert coll is not None
    assert len(coll["items"]) == 2


def test_form_wrong_stage(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    save_collection("test", "formed", "- already formed\n")
    with _mock_llm():
        result = runner.invoke(main, ["form", "test"])
    assert "expected 'raw'" in result.output


def test_focus_wrong_stage(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    save_collection("test", "raw", "- still raw\n")
    with _mock_llm():
        result = runner.invoke(main, ["focus", "test"])
    assert "expected 'formed'" in result.output


def test_finish_creates_tasks(runner, tmp_config, tmp_data):
    _setup(tmp_config, tmp_data)
    save_collection("test", "focused", "- core item\n")

    with _mock_llm("- Create the landing page\n- Write unit tests"):
        result = runner.invoke(main, ["finish", "test"], input="y\n")

    assert result.exit_code == 0
    # Verify tasks were created
    from bute.storage import load_entries_by_filter
    from bute.models import EntryType
    tasks = load_entries_by_filter(lambda e: e.type == EntryType.TASK)
    task_bodies = [t.body for t in tasks]
    assert "Create the landing page" in task_bodies
    assert "Write unit tests" in task_bodies
