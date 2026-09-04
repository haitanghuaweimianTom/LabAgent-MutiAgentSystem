"""Tests for LessonV2, effectiveness tracking, and digest aggregation."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from self_evolution import (
    LessonCategory,
    LessonV2,
    update_effectiveness,
    build_digest,
    EvolutionStore,
)


class TestLessonCategories:
    def test_nine_categories(self):
        assert len(LessonCategory) == 9
        assert LessonCategory.PLANNING == "planning"
        assert LessonCategory.EFFICIENCY == "efficiency"


class TestLessonV2:
    def test_extends_lesson_entry(self):
        lesson = LessonV2(
            stage_name="step3",
            category="experiment",
            severity="error",
            description="Some specific problem description here",
        )
        assert lesson.issue_key != ""
        assert lesson.effectiveness == "unverified"
        assert lesson.total_occurrences == 1
        assert lesson.source == "reflection"

    def test_roundtrip_dict(self):
        lesson = LessonV2(
            stage_name="step3",
            category="experiment",
            severity="error",
            description="Specific problem description for roundtrip",
            root_cause="cause",
            suggestion="fix",
            specificity=5,
            testability=4,
            effectiveness="ineffective",
            affected_stages=["step3"],
            source="reflection",
        )
        data = lesson.to_dict()
        restored = LessonV2.from_dict(data)
        assert restored.issue_key == lesson.issue_key
        assert restored.effectiveness == "ineffective"
        assert restored.specificity == 5

    def test_effective_weight_in_query(self, tmp_path):
        import math
        store = EvolutionStore(tmp_path / "evo")
        store.append(LessonV2(
            stage_name="step1",
            category="system",
            severity="error",
            description="specific system timeout problem with enough length",
            effectiveness="effective",
        ))
        store.append(LessonV2(
            stage_name="step1",
            category="system",
            severity="error",
            description="another specific system problem that is ineffective",
            effectiveness="ineffective",
        ))
        results = store.query_for_stage("step1", max_lessons=2)
        # effective lesson should rank before the ineffective one
        effs = [r.effectiveness for r in results]
        assert "effective" in effs
        assert effs.index("effective") < effs.index("ineffective")


class TestUpdateEffectiveness:
    def test_recurring_issue_marked_ineffective(self):
        lesson = LessonV2(
            stage_name="step1", category="experiment", severity="error",
            description="Specific recurring timeout problem with enough text",
            total_occurrences=3,
        )
        status = update_effectiveness([lesson.issue_key], [lesson])
        assert status[lesson.issue_key] == "ineffective"
        assert lesson.effectiveness == "ineffective"

    def test_resolved_issue_marked_effective(self):
        lesson = LessonV2(
            stage_name="step1", category="experiment", severity="error",
            description="A specific resolved problem with enough text",
            total_occurrences=2,
        )
        status = update_effectiveness([], [lesson])
        assert status[lesson.issue_key] == "effective"

    def test_low_occurrence_stays_unverified(self):
        lesson = LessonV2(
            stage_name="step1", category="experiment", severity="error",
            description="A brand new specific problem that just appeared",
            total_occurrences=1,
        )
        status = update_effectiveness([], [lesson])
        assert status[lesson.issue_key] == "unverified"


class TestBuildDigest:
    def test_aggregates_by_issue_key(self):
        # Two lessons with same underlying issue (different wording/signature-tolerant)
        l1 = LessonV2(
            stage_name="step1", category="system", severity="error",
            description="运行超时导致整个运行失败",
            total_occurrences=1,
        )
        l2 = LessonV2(
            stage_name="step1", category="system", severity="error",
            description="timeout exceeded caused whole run to fail",
            total_occurrences=1,
        )
        digest = build_digest([l1, l2])
        # both share the same issue_key (timeout canonical)
        assert l1.issue_key == l2.issue_key
        assert digest[l1.issue_key].total_occurrences == 2

    def test_uses_shortest_description(self):
        l1 = LessonV2(
            stage_name="step1", category="writing", severity="warning",
            description="A very long writing problem description that goes on and on",
            total_occurrences=1,
        )
        l2 = LessonV2(
            stage_name="step1", category="writing", severity="warning",
            description="short writing problem",
            total_occurrences=1,
        )
        digest = build_digest([l1, l2])
        assert digest[l2.issue_key].pattern_summary == "short writing problem"