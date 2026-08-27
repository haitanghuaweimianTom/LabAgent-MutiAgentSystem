"""Tests for Iterative Quality Gate Module."""
import json
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from iterative_quality_gate import (
    GateAction,
    QualityMetric,
    GateDecision,
    IterativeQualityGate,
)


class TestGateAction:
    def test_actions(self):
        assert GateAction.CONTINUE == "continue"
        assert GateAction.REVISE == "revise"
        assert GateAction.TERMINATE == "terminate"
        assert GateAction.SKIP == "skip"


class TestQualityMetric:
    def test_creation(self):
        metric = QualityMetric(
            name="accuracy",
            score=0.85,
            weight=1.0,
            threshold=0.7,
        )
        assert metric.name == "accuracy"
        assert metric.score == 0.85
        assert metric.passed is True

    def test_failed_metric(self):
        metric = QualityMetric(
            name="accuracy",
            score=0.3,
            threshold=0.7,
        )
        assert metric.passed is False

    def test_to_dict(self):
        metric = QualityMetric(
            name="accuracy",
            score=0.85,
            weight=1.2,
            threshold=0.7,
        )
        d = metric.to_dict()
        assert d["name"] == "accuracy"
        assert d["score"] == 0.85
        assert d["weight"] == 1.2
        assert d["passed"] is True


class TestGateDecision:
    def test_creation(self):
        decision = GateDecision(
            stage="step1",
            action=GateAction.CONTINUE,
            weighted_score=0.8,
            metrics=[],
            reasoning="Score sufficient",
        )
        assert decision.stage == "step1"
        assert decision.action == GateAction.CONTINUE
        assert decision.weighted_score == 0.8

    def test_to_dict(self):
        decision = GateDecision(
            stage="step1",
            action=GateAction.REVISE,
            weighted_score=0.5,
            metrics=[QualityMetric("test", 0.5)],
            reasoning="Needs work",
            revision_count=1,
        )
        d = decision.to_dict()
        assert d["stage"] == "step1"
        assert d["action"] == "revise"
        assert d["revision_count"] == 1


class TestIterativeQualityGate:
    def test_continue_on_high_score(self, tmp_path):
        gate = IterativeQualityGate(tmp_path)
        metrics = [
            QualityMetric("accuracy", 0.85, threshold=0.7),
            QualityMetric("completeness", 0.9, threshold=0.7),
        ]
        decision = gate.evaluate("step1", metrics)
        assert decision.action == GateAction.CONTINUE
        assert decision.weighted_score > 0.7

    def test_revise_on_medium_score(self, tmp_path):
        gate = IterativeQualityGate(tmp_path)
        metrics = [
            QualityMetric("accuracy", 0.5, threshold=0.7),
        ]
        decision = gate.evaluate("step1", metrics)
        assert decision.action == GateAction.REVISE

    def test_terminate_on_low_score(self, tmp_path):
        gate = IterativeQualityGate(tmp_path, revise_threshold=0.4)
        metrics = [
            QualityMetric("accuracy", 0.2, threshold=0.7),
        ]
        decision = gate.evaluate("step1", metrics)
        assert decision.action == GateAction.TERMINATE

    def test_terminate_on_critical_failure(self, tmp_path):
        gate = IterativeQualityGate(tmp_path)
        metrics = [
            QualityMetric("accuracy", 0.9, threshold=0.7, weight=1.0),
            QualityMetric("validity", 0.3, threshold=0.7, weight=1.0),
        ]
        decision = gate.evaluate("step1", metrics)
        assert decision.action == GateAction.REVISE

    def test_max_revisions_terminate(self, tmp_path):
        gate = IterativeQualityGate(tmp_path, max_revisions=2)
        metrics = [
            QualityMetric("accuracy", 0.5, threshold=0.7),
        ]
        gate.evaluate("step1", metrics)
        gate.evaluate("step1", metrics)
        decision = gate.evaluate("step1", metrics)
        assert decision.action == GateAction.TERMINATE
        assert decision.revision_count == 2

    def test_weighted_score(self, tmp_path):
        gate = IterativeQualityGate(tmp_path)
        metrics = [
            QualityMetric("accuracy", 0.8, weight=2.0, threshold=0.7),
            QualityMetric("completeness", 0.6, weight=1.0, threshold=0.7),
        ]
        decision = gate.evaluate("step1", metrics)
        # Weighted: (0.8*2 + 0.6*1) / (2+1) = 2.2/3 = 0.733
        assert abs(decision.weighted_score - 0.733) < 0.01

    def test_empty_metrics(self, tmp_path):
        gate = IterativeQualityGate(tmp_path)
        decision = gate.evaluate("step1", [])
        assert decision.weighted_score == 0.0
        assert decision.action == GateAction.TERMINATE

    def test_decision_logged(self, tmp_path):
        gate = IterativeQualityGate(tmp_path)
        metrics = [QualityMetric("test", 0.8)]
        gate.evaluate("step1", metrics)
        decisions_path = tmp_path / "quality_decisions.jsonl"
        assert decisions_path.exists()
        lines = decisions_path.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_get_history(self, tmp_path):
        workspace = tmp_path / "gate_history"
        gate = IterativeQualityGate(workspace)
        metrics = [QualityMetric("test", 0.8)]
        gate.evaluate("step1", metrics)
        gate.evaluate("step2", metrics)
        history = gate.get_history()
        assert len(history) == 2

    def test_get_history_by_stage(self, tmp_path):
        workspace = tmp_path / "gate_history_stage"
        gate = IterativeQualityGate(workspace)
        metrics = [QualityMetric("test", 0.8)]
        gate.evaluate("step1", metrics)
        gate.evaluate("step1", metrics)
        gate.evaluate("step2", metrics)
        history = gate.get_history(stage="step1")
        assert len(history) == 2

    def test_get_stage_stats(self, tmp_path):
        workspace = tmp_path / "gate_stats"
        gate = IterativeQualityGate(workspace)
        metrics = [QualityMetric("test", 0.8)]
        gate.evaluate("step1", metrics)
        stats = gate.get_stage_stats("step1")
        assert stats["total"] == 1
        assert "continue" in stats["actions"]

    def test_should_continue(self, tmp_path):
        workspace = tmp_path / "gate_continue"
        gate = IterativeQualityGate(workspace)
        metrics = [QualityMetric("test", 0.8)]
        gate.evaluate("step1", metrics)
        assert gate.should_continue("step1") is True

    def test_should_not_continue_on_terminate(self, tmp_path):
        workspace = tmp_path / "gate_terminate"
        gate = IterativeQualityGate(workspace, revise_threshold=0.4)
        metrics = [QualityMetric("test", 0.2)]
        gate.evaluate("step1", metrics)
        assert gate.should_continue("step1") is False

    def test_reset_stage(self, tmp_path):
        workspace = tmp_path / "gate_reset"
        gate = IterativeQualityGate(workspace, max_revisions=1)
        metrics = [QualityMetric("test", 0.5, threshold=0.7)]
        gate.evaluate("step1", metrics)
        gate.reset_stage("step1")
        decision = gate.evaluate("step1", metrics)
        assert decision.action == GateAction.REVISE
