"""Tests for collections storage and commands."""

from bute.collection_storage import (
    append_to_collection,
    list_collections_with_meta,
    load_collection,
    save_collection,
)


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
