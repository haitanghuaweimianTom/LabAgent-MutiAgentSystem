"""Tests for Self-Evolution Module."""
import json
import time
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from self_evolution import (
    LessonCategory,
    LessonEntry,
    EvolutionStore,
    extract_lessons,
    build_overlay,
)


class TestLessonCategory:
    def test_categories_exist(self):
        assert LessonCategory.SYSTEM == "system"
        assert LessonCategory.EXPERIMENT == "experiment"
        assert LessonCategory.WRITING == "writing"
        assert LessonCategory.ANALYSIS == "analysis"
        assert LessonCategory.LITERATURE == "literature"
        assert LessonCategory.PIPELINE == "pipeline"
        assert LessonCategory.IDEATION == "ideation"

    def test_all_seven_categories(self):
        assert len(LessonCategory) == 7


class TestLessonEntry:
    def test_creation(self):
        entry = LessonEntry(
            stage_name="step1",
            category="experiment",
            severity="error",
            description="Test error",
        )
        assert entry.stage_name == "step1"
        assert entry.category == "experiment"
        assert entry.severity == "error"
        assert entry.timestamp > 0

    def test_to_dict(self):
        entry = LessonEntry(
            stage_name="step1",
            category="writing",
            severity="warning",
            description="Test warning",
            run_id="run-001",
        )
        d = entry.to_dict()
        assert d["stage_name"] == "step1"
        assert d["category"] == "writing"
        assert d["severity"] == "warning"
        assert d["run_id"] == "run-001"

    def test_from_dict(self):
        data = {
            "stage_name": "step2",
            "category": "pipeline",
            "severity": "info",
            "description": "Test info",
            "timestamp": 1234567890.0,
            "run_id": "run-002",
            "metadata": {"key": "value"},
        }
        entry = LessonEntry.from_dict(data)
        assert entry.stage_name == "step2"
        assert entry.category == "pipeline"
        assert entry.severity == "info"
        assert entry.metadata == {"key": "value"}

    def test_roundtrip(self):
        original = LessonEntry(
            stage_name="step3",
            category="analysis",
            severity="error",
            description="Roundtrip test",
        )
        data = original.to_dict()
        restored = LessonEntry.from_dict(data)
        assert original.stage_name == restored.stage_name
        assert original.category == restored.category
        assert original.severity == restored.severity
        assert original.description == restored.description


class TestEvolutionStore:
    def test_append_and_load(self, tmp_path):
        store = EvolutionStore(tmp_path / "evolution")
        entry = LessonEntry(
            stage_name="test",
            category="experiment",
            severity="error",
            description="Test lesson",
        )
        store.append(entry)
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].description == "Test lesson"

    def test_append_many(self, tmp_path):
        store = EvolutionStore(tmp_path / "evolution")
        entries = [
            LessonEntry(
                stage_name=f"step{i}",
                category="pipeline",
                severity="info",
                description=f"Lesson {i}",
            )
            for i in range(5)
        ]
        store.append_many(entries)
        assert store.count() == 5

    def test_query_for_stage(self, tmp_path):
        store = EvolutionStore(tmp_path / "evolution")
        store.append(LessonEntry(
            stage_name="step1",
            category="experiment",
            severity="error",
            description="Error in step1",
        ))
        store.append(LessonEntry(
            stage_name="step2",
            category="writing",
            severity="warning",
            description="Warning in step2",
        ))
        results = store.query_for_stage("step1")
        assert len(results) >= 1
        assert any(r.stage_name == "step1" for r in results)

    def test_build_overlay(self, tmp_path):
        store = EvolutionStore(tmp_path / "evolution")
        store.append(LessonEntry(
            stage_name="step1",
            category="experiment",
            severity="error",
            description="Test overlay",
        ))
        overlay = store.build_overlay("step1")
        assert "Test overlay" in overlay
        assert "Evolution Lessons" in overlay

    def test_empty_overlay(self, tmp_path):
        store = EvolutionStore(tmp_path / "evolution")
        overlay = store.build_overlay("nonexistent")
        assert overlay == ""

    def test_count(self, tmp_path):
        store = EvolutionStore(tmp_path / "evolution")
        assert store.count() == 0
        store.append(LessonEntry(
            stage_name="test",
            category="pipeline",
            severity="info",
            description="Test",
        ))
        assert store.count() == 1


class TestExtractLessons:
    def test_extract_from_errors(self):
        results = {
            "step1": {
                "status": "failed",
                "error": "ImportError: No module named numpy",
                "score": None,
                "duration": 10.0,
            }
        }
        lessons = extract_lessons(results, run_id="test-run")
        assert len(lessons) >= 1
        assert any("numpy" in l.description for l in lessons)

    def test_extract_low_scores(self):
        results = {
            "step1": {
                "status": "completed",
                "error": "",
                "score": 0.3,
                "duration": 5.0,
            }
        }
        lessons = extract_lessons(results)
        assert len(lessons) >= 1
        assert any("low quality" in l.description.lower() for l in lessons)

    def test_extract_slow_stages(self):
        results = {
            "step1": {
                "status": "completed",
                "error": "",
                "score": 0.8,
                "duration": 400.0,  # > 5 minutes
            }
        }
        lessons = extract_lessons(results)
        assert len(lessons) >= 1
        assert any("slow" in l.description.lower() for l in lessons)

    def test_no_lessons_from_good_results(self):
        results = {
            "step1": {
                "status": "completed",
                "error": "",
                "score": 0.9,
                "duration": 30.0,
            }
        }
        lessons = extract_lessons(results)
        assert len(lessons) == 0


class TestBuildOverlay:
    def test_build_with_evolution(self, tmp_path):
        store = EvolutionStore(tmp_path / "evolution")
        store.append(LessonEntry(
            stage_name="step1",
            category="experiment",
            severity="error",
            description="Test lesson",
        ))
        overlay = build_overlay("step1", evolution_store=store)
        assert "Test lesson" in overlay

    def test_build_empty(self, tmp_path):
        store = EvolutionStore(tmp_path / "evolution")
        overlay = build_overlay("nonexistent", evolution_store=store)
        assert overlay == ""
