"""Tests for context_overlay.py - stage-routed, relevance-scored prompt overlay."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

from context_overlay import (
    build_context_overlay,
    score_lesson_for_stage,
    STAGE_CATEGORIES,
)
from self_evolution import LessonV2


def make_lesson(desc, category, **kw):
    l = LessonV2(
        stage_name=kw.get("stage_name", "step1"),
        category=category,
        severity=kw.get("severity", "error"),
        description=desc,
        effectiveness=kw.get("effectiveness", "unverified"),
        weighted_frequency=kw.get("weighted_frequency", 1.0),
        suggestion=kw.get("suggestion", ""),
        affected_stages=kw.get("affected_stages", []),
    )
    return l


class TestStageCategories:
    def test_all_steps_present(self):
        for step in ["step1", "step1b", "step2", "step3", "step4", "step5", "step6", "step7"]:
            assert step in STAGE_CATEGORIES
            assert isinstance(STAGE_CATEGORIES[step], list)
            assert len(STAGE_CATEGORIES[step]) > 0

    def test_research_maps_literature(self):
        assert "literature" in STAGE_CATEGORIES["step1"]


class TestScoreForStage:
    def test_matching_category_boosted(self):
        lesson = make_lesson("specific timeout problem with enough text", "system")
        score_matched = score_lesson_for_stage(lesson, "step3")  # system in step3
        score_unmatched = score_lesson_for_stage(lesson, "step4")  # writing mostly
        assert score_matched > score_unmatched

    def test_effective_boosted_over_ineffective(self):
        eff = make_lesson("specific effective problem text", "experiment", effectiveness="effective")
        ineff = make_lesson("specific ineffective problem text", "experiment", effectiveness="ineffective")
        assert score_lesson_for_stage(eff, "step3") > score_lesson_for_stage(ineff, "step3")


class TestBuildContextOverlay:
    def test_empty_returns_empty(self):
        assert build_context_overlay("step1", []) == ""

    def test_includes_matching_lesson_and_suggestion(self):
        lesson = make_lesson(
            "VRPTW solver times out above fifty nodes with too much detail here",
            "system",
            suggestion="use ortools with a time limit of sixty seconds",
            effectiveness="effective",
        )
        overlay = build_context_overlay("step3", [lesson])
        assert "经验教训" in overlay
        assert "VRPTW" in overlay
        assert "ortools" in overlay

    def test_reroute_to_unrelated_stage_still_includes_top(self):
        lesson = make_lesson(
            "a very specific writing problem that is long and detailed", 
            "writing",
            effectiveness="effective",
        )
        overlay = build_context_overlay("step1", [lesson])
        # even if step-step routing mismatches, a relevant effective lesson may appear
        # but you generally expect the overlay to be non-empty when there's an effective lesson
        assert overlay != ""

    def test_max_lessons_respected(self):
        lessons = [
            make_lesson(f"specific problem number {i} constructed with enough length", "experiment", effectiveness="effective")
            for i in range(12)
        ]
        overlay = build_context_overlay("step3", lessons, max_lessons=3)
        assert overlay.count("specific problem") == 3

    def test_returns_injected_keys(self):
        lessons = [
            make_lesson(f"specific issue key test {i} enough length here", "experiment", effectiveness="effective")
            for i in range(3)
        ]
        overlay, keys = build_context_overlay("step3", lessons, return_keys=True)
        assert len(keys) == 3
        assert len(overlay) > 0