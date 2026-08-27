"""
Iterative Quality Gate - Auto-Continue/Terminate Decision

Inspired by Sibyl's quality gate with auto-decision logic.
Automatically decides whether to continue, revise, or terminate based on quality scores.

Components:
- QualityMetric: Individual quality measurement
- GateDecision: Decision outcome with reasoning
- IterativeQualityGate: Multi-stage gate with auto-decision
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "GateAction",
    "QualityMetric",
    "GateDecision",
    "IterativeQualityGate",
]


class GateAction(str, Enum):
    """Gate decision actions."""
    CONTINUE = "continue"      # Quality sufficient, proceed
    REVISE = "revise"          # Needs improvement, revise and re-evaluate
    TERMINATE = "terminate"    # Quality too low, abort pipeline
    SKIP = "skip"              # Skip optional stage


@dataclass
class QualityMetric:
    """Individual quality measurement."""
    name: str
    score: float  # 0.0 to 1.0
    weight: float = 1.0
    threshold: float = 0.5  # Minimum acceptable score
    details: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def passed(self) -> bool:
        return self.score >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "threshold": self.threshold,
            "passed": self.passed,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class GateDecision:
    """Decision outcome with reasoning."""
    stage: str
    action: GateAction
    weighted_score: float
    metrics: list[QualityMetric]
    reasoning: str
    revision_count: int = 0
    max_revisions: int = 3
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "action": self.action.value,
            "weighted_score": self.weighted_score,
            "metrics": [m.to_dict() for m in self.metrics],
            "reasoning": self.reasoning,
            "revision_count": self.revision_count,
            "max_revisions": self.max_revisions,
            "timestamp": self.timestamp,
        }


class IterativeQualityGate:
    """Multi-stage quality gate with auto-decision logic.

    Features:
    - Weighted scoring across multiple metrics
    - Configurable thresholds per stage
    - Auto-decision: continue/revise/terminate
    - Revision tracking with max limit
    - Historical decision logging
    """

    def __init__(
        self,
        workspace_dir: Path | str,
        *,
        continue_threshold: float = 0.7,
        revise_threshold: float = 0.4,
        max_revisions: int = 3,
    ) -> None:
        """
        Args:
            workspace_dir: Workspace directory for logging
            continue_threshold: Score above which to continue
            revise_threshold: Score below which to terminate
            max_revisions: Maximum revision attempts before terminating
        """
        self._workspace = Path(workspace_dir)
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._decisions_path = self._workspace / "quality_decisions.jsonl"
        self._continue_threshold = continue_threshold
        self._revise_threshold = revise_threshold
        self._max_revisions = max_revisions
        self._revision_counts: dict[str, int] = {}

    def evaluate(
        self,
        stage: str,
        metrics: list[QualityMetric],
        *,
        context: dict[str, Any] | None = None,
    ) -> GateDecision:
        """Evaluate quality metrics and make a gate decision.

        Args:
            stage: Pipeline stage name
            metrics: List of quality metrics to evaluate
            context: Additional context for decision

        Returns:
            GateDecision with action and reasoning
        """
        # Compute weighted score
        if not metrics:
            weighted_score = 0.0
        else:
            total_weight = sum(m.weight for m in metrics)
            if total_weight == 0:
                weighted_score = 0.0
            else:
                weighted_score = sum(m.score * m.weight for m in metrics) / total_weight

        # Get revision count for this stage
        revision_count = self._revision_counts.get(stage, 0)

        # Make decision
        action, reasoning = self._decide(
            stage, weighted_score, metrics, revision_count, context
        )

        # Update revision count
        if action == GateAction.REVISE:
            self._revision_counts[stage] = revision_count + 1

        decision = GateDecision(
            stage=stage,
            action=action,
            weighted_score=weighted_score,
            metrics=metrics,
            reasoning=reasoning,
            revision_count=revision_count,
            max_revisions=self._max_revisions,
        )

        # Log decision
        self._log_decision(decision)

        return decision

    def _decide(
        self,
        stage: str,
        score: float,
        metrics: list[QualityMetric],
        revision_count: int,
        context: dict[str, Any] | None,
    ) -> tuple[GateAction, str]:
        """Make gate decision based on score and metrics."""
        reasons = []

        # Check if any critical metric failed
        critical_failures = [m for m in metrics if not m.passed and m.weight >= 1.0]
        if critical_failures:
            names = [m.name for m in critical_failures]
            reasons.append(f"Critical metrics failed: {', '.join(names)}")

        # Check revision limit
        if revision_count >= self._max_revisions:
            reasons.append(f"Max revisions ({self._max_revisions}) reached")
            return GateAction.TERMINATE, "; ".join(reasons)

        # Decision logic
        if score >= self._continue_threshold:
            if not critical_failures:
                reasons.append(f"Score {score:.2f} >= {self._continue_threshold}")
                return GateAction.CONTINUE, "; ".join(reasons) if reasons else "Quality sufficient"
            else:
                reasons.append(f"Score OK but critical failures present")
                return GateAction.REVISE, "; ".join(reasons)

        elif score >= self._revise_threshold:
            reasons.append(f"Score {score:.2f} in revision range [{self._revise_threshold}, {self._continue_threshold})")
            return GateAction.REVISE, "; ".join(reasons)

        else:
            reasons.append(f"Score {score:.2f} < {self._revise_threshold}")
            return GateAction.TERMINATE, "; ".join(reasons)

    def _log_decision(self, decision: GateDecision) -> None:
        """Log decision to disk."""
        with self._decisions_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(decision.to_dict(), ensure_ascii=False) + "\n")

    def get_history(self, stage: str | None = None) -> list[GateDecision]:
        """Get decision history, optionally filtered by stage."""
        if not self._decisions_path.exists():
            return []

        decisions = []
        for line in self._decisions_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                # Filter out 'passed' field from metrics (it's a property, not a constructor param)
                metrics_data = []
                for m in data.get("metrics", []):
                    filtered = {k: v for k, v in m.items() if k != "passed"}
                    metrics_data.append(QualityMetric(**filtered))
                decision = GateDecision(
                    stage=data["stage"],
                    action=GateAction(data["action"]),
                    weighted_score=data["weighted_score"],
                    metrics=metrics_data,
                    reasoning=data.get("reasoning", ""),
                    revision_count=data.get("revision_count", 0),
                    max_revisions=data.get("max_revisions", 3),
                    timestamp=data.get("timestamp", 0.0),
                )
                if stage is None or decision.stage == stage:
                    decisions.append(decision)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        return decisions

    def get_stage_stats(self, stage: str) -> dict[str, Any]:
        """Get statistics for a specific stage."""
        decisions = self.get_history(stage)
        if not decisions:
            return {"total": 0}

        actions = {}
        for d in decisions:
            actions[d.action.value] = actions.get(d.action.value, 0) + 1

        scores = [d.weighted_score for d in decisions]
        return {
            "total": len(decisions),
            "actions": actions,
            "avg_score": sum(scores) / len(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
        }

    def reset_stage(self, stage: str) -> None:
        """Reset revision count for a stage."""
        self._revision_counts.pop(stage, None)

    def should_continue(self, stage: str) -> bool:
        """Check if pipeline should continue based on recent decision."""
        decisions = self.get_history(stage)
        if not decisions:
            return True

        last_decision = decisions[-1]
        return last_decision.action in (GateAction.CONTINUE, GateAction.REVISE)
