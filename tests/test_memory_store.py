"""Tests for Memory Store Module."""
import json
import time
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from memory_store import MemoryCategory, MemoryEntry, MemoryStore


class TestMemoryCategory:
    def test_categories(self):
        assert MemoryCategory.IDEATION == "ideation"
        assert MemoryCategory.EXPERIMENT == "experiment"
        assert MemoryCategory.WRITING == "writing"
        assert MemoryCategory.ANALYSIS == "analysis"
        assert MemoryCategory.REFERENCE == "reference"
        assert MemoryCategory.SYSTEM == "system"
        assert MemoryCategory.PIPELINE == "pipeline"


class TestMemoryEntry:
    def test_creation(self):
        entry = MemoryEntry(
            content="Test memory",
            category="experiment",
            tags=["test", "sample"],
        )
        assert entry.content == "Test memory"
        assert entry.category == "experiment"
        assert entry.tags == ["test", "sample"]
        assert entry.timestamp > 0

    def test_to_dict(self):
        entry = MemoryEntry(
            content="Test",
            category="writing",
            metadata={"key": "value"},
            source="test_source",
            tags=["tag1"],
        )
        d = entry.to_dict()
        assert d["content"] == "Test"
        assert d["category"] == "writing"
        assert d["metadata"] == {"key": "value"}
        assert d["source"] == "test_source"
        assert d["tags"] == ["tag1"]

    def test_from_dict(self):
        data = {
            "content": "Test memory",
            "category": "ideation",
            "metadata": {},
            "timestamp": 1234567890.0,
            "source": "test",
            "tags": ["tag1", "tag2"],
        }
        entry = MemoryEntry.from_dict(data)
        assert entry.content == "Test memory"
        assert entry.category == "ideation"
        assert entry.tags == ["tag1", "tag2"]

    def test_roundtrip(self):
        original = MemoryEntry(
            content="Roundtrip test",
            category="analysis",
            tags=["test"],
        )
        data = original.to_dict()
        restored = MemoryEntry.from_dict(data)
        assert original.content == restored.content
        assert original.category == restored.category
        assert original.tags == restored.tags


class TestMemoryStore:
    def test_add_and_load(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        store.add("Test memory", category="experiment")
        memories = store.load_all()
        assert len(memories) == 1
        assert memories[0].content == "Test memory"

    def test_add_with_tags(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        store.add("Tagged memory", tags=["important", "reference"])
        memories = store.load_all()
        assert memories[0].tags == ["important", "reference"]

    def test_add_many(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        entries = [
            MemoryEntry(content=f"Memory {i}", category="pipeline")
            for i in range(5)
        ]
        count = store.add_many(entries)
        assert count == 5
        assert store.count() == 5

    def test_recall_by_category(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        store.add("Experiment memory", category="experiment")
        store.add("Writing memory", category="writing")
        recalled = store.recall("experiment", category="experiment")
        assert len(recalled) >= 1
        assert all(m.category == "experiment" for m in recalled)

    def test_recall_by_tags(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        store.add("Important memory", tags=["important"])
        store.add("Regular memory", tags=["regular"])
        recalled = store.recall("important", tags=["important"])
        assert len(recalled) >= 1

    def test_recall_semantic(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        store.add("Machine learning model training")
        store.add("Paper writing guidelines")
        recalled = store.recall("machine learning")
        assert len(recalled) >= 1
        assert any("machine learning" in m.content.lower() for m in recalled)

    def test_count(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        assert store.count() == 0
        store.add("Memory 1", category="experiment")
        store.add("Memory 2", category="writing")
        assert store.count() == 2

    def test_count_by_category(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        store.add("Memory 1", category="experiment")
        store.add("Memory 2", category="experiment")
        store.add("Memory 3", category="writing")
        assert store.count(category="experiment") == 2
        assert store.count(category="writing") == 1

    def test_get_categories(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        store.add("Memory 1", category="experiment")
        store.add("Memory 2", category="writing")
        store.add("Memory 3", category="writing")
        cats = store.get_categories()
        assert cats["experiment"] == 1
        assert cats["writing"] == 2

    def test_get_recent(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        for i in range(5):
            store.add(f"Memory {i}")
        recent = store.get_recent(limit=3)
        assert len(recent) == 3

    def test_search_by_tag(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        store.add("Memory 1", tags=["important"])
        store.add("Memory 2", tags=["regular"])
        store.add("Memory 3", tags=["important"])
        results = store.search_by_tag("important")
        assert len(results) == 2

    def test_clear_all(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        store.add("Memory 1")
        store.add("Memory 2")
        removed = store.clear()
        assert removed == 2
        assert store.count() == 0

    def test_clear_by_category(self, tmp_path):
        store = MemoryStore(tmp_path / "memory")
        store.add("Memory 1", category="experiment")
        store.add("Memory 2", category="writing")
        removed = store.clear(category="experiment")
        assert removed == 1
        assert store.count() == 1
