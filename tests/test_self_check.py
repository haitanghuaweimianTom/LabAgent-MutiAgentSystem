"""Tests for self_check.py - self-check diagnostics + quality trend."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from self_check import SelfChecker, build_quality_trend_md, diagnose
from self_evolution import DigestEntry


def outcome(score, category="experiment", issue_key=None, ts=1.0):
    return {
        "score": score,
        "category": category,
        "issue_key": issue_key,
        "timestamp": ts,
    }


class TestDiagnose:
    def test_none_when_healthy(self):
        outs = [outcome(0.8), outcome(0.8), outcome(0.8)]
        assert diagnose(outs, {}) is None

    def test_declining_trend_detected(self):
        outs = [outcome(0.9), outcome(0.7), outcome(0.5)]
        result = diagnose(outs, {})
        assert result is not None
        assert result.get("declining_trend") is True

    def test_recurring_system_error(self):
        outs = [
            outcome(0.6, "system", "k1"),
            outcome(0.6, "system", "k1"),
            outcome(0.6, "system", "k1"),  # >= 3
        ]
        result = diagnose(outs, {})
        assert result is not None
        assert "k1" in result.get("recurring_errors", [])

    def test_ineffective_lesson_accumulation(self):
        digest = {
            "abc": DigestEntry(
                issue_key="abc", category="system", pattern_summary="p",
                total_occurrences=5, effectiveness="ineffective",
            )
        }
        result = diagnose([], digest)
        assert result is not None
        assert "abc" in result.get("ineffective_lessons", [])


class TestQualityTrend:
    def test_build_markdown(self):
        md = build_quality_trend_md([0.9, 0.7, 0.5])
        assert "0.9" in md
        assert "0.5" in md

    def test_empty_scores(self):
        assert build_quality_trend_md([]) == ""


class TestSelfChecker:
    def test_write_diagnostics_file(self, tmp_path):
        checker = SelfChecker(tmp_path)
        checker.write_diagnostics({"declining_trend": True, "recent_scores": [0.9, 0.7]})
        f = tmp_path / "self_check_diagnostics.json"
        assert f.exists()
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["declining_trend"] is True

    def test_cleanup_when_healthy(self, tmp_path):
        checker = SelfChecker(tmp_path)
        checker.write_diagnostics({"declining_trend": True})
        # healthy run clears the file
        checker.clear_diagnostics()
        assert not (tmp_path / "self_check_diagnostics.json").exists()

    def test_write_quality_trend_file(self, tmp_path):
        checker = SelfChecker(tmp_path)
        checker.write_quality_trend([0.9, 0.7, 0.5])
        md = (tmp_path / "quality_trend.md").read_text(encoding="utf-8")
        assert "0.7" in md

    def test_diagnose_writes_none_and_cleans(self, tmp_path):
        checker = SelfChecker(tmp_path)
        # Healthy run: no diagnostics file should remain
        checker.diagnose_and_report([outcome(0.9), outcome(0.9)], {})
        assert not (tmp_path / "self_check_diagnostics.json").exists()