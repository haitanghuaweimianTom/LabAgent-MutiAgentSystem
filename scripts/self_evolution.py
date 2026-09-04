"""
Self-Evolution Module - Cross-Project Learning System

Inspired by AutoResearchClaw's EvolutionStore and Sibyl's cross-project learning.
Records lessons from each pipeline run and injects them into future runs as prompt overlays.

Components:
- LessonCategory: 7 issue categories for classification
- LessonEntry: Single lesson with stage, category, severity, description
- EvolutionStore: JSONL-backed persistent store with time-weighted retrieval
- extract_lessons: Auto-extract lessons from StageResult lists
- build_overlay: Generate per-stage prompt overlay text
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from issue_signature import build_issue_key, normalize_text

__all__ = [
    "LessonCategory",
    "LessonEntry",
    "LessonV2",
    "DigestEntry",
    "EvolutionStore",
    "extract_lessons",
    "build_overlay",
    "update_effectiveness",
    "build_digest",
]


class LessonCategory(str, Enum):
    """9 issue categories for classifying lessons."""

    SYSTEM = "system"
    EXPERIMENT = "experiment"
    WRITING = "writing"
    ANALYSIS = "analysis"
    LITERATURE = "literature"
    PIPELINE = "pipeline"
    IDEATION = "ideation"
    PLANNING = "planning"
    EFFICIENCY = "efficiency"


@dataclass
class LessonEntry:
    """Single lesson from a pipeline run."""

    stage_name: str
    category: str  # LessonCategory value
    severity: str  # "info", "warning", "error"
    description: str
    timestamp: float = field(default_factory=time.time)
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LessonEntry:
        return cls(
            stage_name=data.get("stage_name", "unknown"),
            category=data.get("category", "pipeline"),
            severity=data.get("severity", "info"),
            description=data.get("description", ""),
            timestamp=data.get("timestamp", 0.0),
            run_id=data.get("run_id", ""),
            metadata=data.get("metadata", {}),
        )


# Keywords for auto-classifying errors into categories
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    LessonCategory.SYSTEM: [
        "timeout", "oom", "memory", "network", "connection", "crash", "hang",
        "gpu", "cuda", "disk", "permission", "resource",
    ],
    LessonCategory.EXPERIMENT: [
        "sandbox", "code", "import", "syntax", "runtime", "exception", "traceback",
        "assert", "test", "validate", "install", "package", "dependency",
    ],
    LessonCategory.WRITING: [
        "latex", "paper", "section", "abstract", "figure", "table", "equation",
        "citation", "reference", "format", "draft", "revision", "style",
    ],
    LessonCategory.ANALYSIS: [
        "statistical", "significant", "p-value", "confidence", "variance",
        "metric", "baseline", "comparison", "result", "plot", "chart",
    ],
    LessonCategory.LITERATURE: [
        "arxiv", "search", "query", "paper", "reference", "citation", "doi",
        "semantic", "scholar", "database", "screen", "filter",
    ],
    LessonCategory.PIPELINE: [
        "stage", "pipeline", "orchestrat", "step", "flow", "gate", "quality",
        "score", "threshold", "progress", "iteration",
    ],
    LessonCategory.IDEATION: [
        "hypothesis", "idea", "novel", "contribution", "research question",
        "approach", "method", "innovation", "gap",
    ],
    LessonCategory.PLANNING: [
        "scope", "estimate", "feasib", "plan", "resource", "schedule",
        "budget", "milestone", "deadline", "overrun",
    ],
    LessonCategory.EFFICIENCY: [
        "gpu idle", "throughput", "bottleneck", "batch size", "parallel",
        "slow", "duration", "latency", "redundant", "waste",
    ],
}


def _classify_error(error_text: str) -> tuple[str, float]:
    """Classify error text into a category with confidence score."""
    error_lower = error_text.lower()
    scores: dict[str, float] = {}

    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in error_lower)
        if score > 0:
            scores[category] = score

    if not scores:
        return LessonCategory.PIPELINE, 0.5

    best_category = max(scores, key=scores.get)
    confidence = min(scores[best_category] / 3.0, 1.0)
    return best_category, confidence


def _time_weight(timestamp: float, half_life_days: float = 30.0) -> float:
    """Compute time-decay weight for a lesson. Recent lessons matter more."""
    if timestamp <= 0:
        return 0.0
    now = time.time()
    age_days = (now - timestamp) / 86400.0
    half_life_seconds = half_life_days * 86400.0
    return math.exp(-0.693 * (now - timestamp) / half_life_seconds)


@dataclass
class LessonV2(LessonEntry):
    """Lesson enriched with issue-key dedup, effectiveness, and semantics.

    Subclasses LessonEntry for backward compatibility with existing stores.
    """

    issue_key: str = ""
    root_cause: str = ""
    suggestion: str = ""
    specificity: int = 0          # 1-5
    testability: int = 0          # 1-5
    effectiveness: str = "unverified"  # effective | ineffective | unverified
    total_occurrences: int = 1
    weighted_frequency: float = 1.0
    affected_stages: list[str] = field(default_factory=list)
    source: str = "reflection"    # reflection | rule

    def __post_init__(self) -> None:
        if not self.issue_key:
            self.issue_key = build_issue_key(self.description, self.category)

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "issue_key": self.issue_key,
            "root_cause": self.root_cause,
            "suggestion": self.suggestion,
            "specificity": self.specificity,
            "testability": self.testability,
            "effectiveness": self.effectiveness,
            "total_occurrences": self.total_occurrences,
            "weighted_frequency": self.weighted_frequency,
            "affected_stages": self.affected_stages,
            "source": self.source,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LessonV2:
        obj = cls(
            stage_name=data.get("stage_name", "unknown"),
            category=data.get("category", "pipeline"),
            severity=data.get("severity", "info"),
            description=data.get("description", ""),
            timestamp=data.get("timestamp", 0.0),
            run_id=data.get("run_id", ""),
            metadata=data.get("metadata", {}),
            issue_key=data.get("issue_key", ""),
            root_cause=data.get("root_cause", ""),
            suggestion=data.get("suggestion", ""),
            specificity=int(data.get("specificity", 0) or 0),
            testability=int(data.get("testability", 0) or 0),
            effectiveness=data.get("effectiveness", "unverified"),
            total_occurrences=int(data.get("total_occurrences", 1) or 1),
            weighted_frequency=float(data.get("weighted_frequency", 1.0) or 1.0),
            affected_stages=data.get("affected_stages", []),
            source=data.get("source", "reflection"),
        )
        if not obj.issue_key:
            obj.issue_key = build_issue_key(obj.description, obj.category)
        return obj


@dataclass
class DigestEntry:
    """Aggregated view of all lessons sharing one issue_key."""

    issue_key: str
    category: str
    pattern_summary: str          # shortest description among aggregated lessons
    total_occurrences: int = 0
    weighted_frequency: float = 0.0
    avg_score_when_seen: float = 0.0
    affected_stages: list[str] = field(default_factory=list)
    effectiveness: str = "unverified"
    severity: str = "info"        # info | warning | high
    last_updated: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DigestEntry:
        return cls(**{k: data.get(k, v) for k, v in cls().to_dict().items() if k in data} or data)


def update_effectiveness(
    current_issue_keys: list[str],
    lessons: list[LessonV2],
) -> dict[str, str]:
    """Update lesson effectiveness based on whether their issue recurred.

    Sibyl rule:
    - key still present this run  -> "ineffective"
    - key gone and occurred >= 2  -> "effective"
    - otherwise keep "unverified"

    Mutates lessons' effectiveness in place and returns {issue_key: status}.
    """
    current = set(current_issue_keys)
    status: dict[str, str] = {}
    for lesson in lessons:
        if not lesson.issue_key:
            continue
        if lesson.issue_key in current:
            lesson.effectiveness = "ineffective"
        elif lesson.total_occurrences >= 2 and lesson.issue_key not in current:
            lesson.effectiveness = "effective"
        else:
            lesson.effectiveness = "unverified"
        status[lesson.issue_key] = lesson.effectiveness
    return status


def build_digest(lessons: list[LessonV2]) -> dict[str, DigestEntry]:
    """Aggregate lessons by issue_key into a digest with weighted frequency.

    - representative description = shortest (resistant to drift)
    - weighted_frequency = sum of time-decay weights
    - insight gating: occurrences >= 2 and weighted_frequency >= 1.0 -> severity warning
      weighted_frequency >= 2.5 -> severity high
    """
    groups: dict[str, DigestEntry] = {}
    for lesson in lessons:
        if not lesson.issue_key:
            lesson.issue_key = build_issue_key(lesson.description, lesson.category)
        weight = _time_weight(lesson.timestamp)
        entry = groups.setdefault(
            lesson.issue_key,
            DigestEntry(
                issue_key=lesson.issue_key,
                category=lesson.category,
                pattern_summary=lesson.description,
            ),
        )
        # shortest representative description
        if len(lesson.description) < len(entry.pattern_summary):
            entry.pattern_summary = lesson.description
        entry.total_occurrences += 1
        entry.weighted_frequency += weight
        entry.last_updated = max(entry.last_updated, lesson.timestamp)
        # affected stages union
        for s in lesson.affected_stages or [lesson.stage_name]:
            if s not in entry.affected_stages:
                entry.affected_stages.append(s)
        # severity escalation
        eff = lesson.effectiveness
        if eff != "unverified":
            entry.effectiveness = eff
    for entry in groups.values():
        if entry.weighted_frequency >= 2.5:
            entry.severity = "high"
        elif entry.total_occurrences >= 2 and entry.weighted_frequency >= 1.0:
            entry.severity = "warning"
    return groups


class EvolutionStore:
    """JSONL-backed store for pipeline lessons with time-weighted retrieval."""

    def __init__(self, store_dir: Path | str) -> None:
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lessons_path = self._dir / "lessons.jsonl"

    @property
    def lessons_path(self) -> Path:
        return self._lessons_path

    def append(self, lesson: LessonEntry) -> None:
        """Append a single lesson to the store."""
        with self._lessons_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(lesson.to_dict(), ensure_ascii=False) + "\n")

    def append_many(self, lessons: list[LessonEntry]) -> None:
        """Append multiple lessons atomically."""
        if not lessons:
            return
        with self._lessons_path.open("a", encoding="utf-8") as f:
            for lesson in lessons:
                f.write(json.dumps(lesson.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> list[LessonV2]:
        """Load all lessons from disk (v1 entries are upgraded to LessonV2)."""
        if not self._lessons_path.exists():
            return []
        lessons: list[LessonV2] = []
        for line in self._lessons_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                lessons.append(LessonV2.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                continue
        return lessons

    def query_for_stage(
        self, stage_name: str, *, max_lessons: int = 5
    ) -> list[LessonEntry]:
        """Return the most relevant lessons for a stage, weighted by recency.

        Ineffective lessons are downweighted (0.3x) so they sink to the bottom.
        """
        all_lessons = self.load_all()
        scored: list[tuple[float, LessonEntry]] = []
        for lesson in all_lessons:
            weight = _time_weight(lesson.timestamp)
            if weight <= 0.0:
                continue
            # Boost direct stage matches
            if lesson.stage_name == stage_name:
                weight *= 2.0
            # Boost errors over warnings/info
            if lesson.severity == "error":
                weight *= 1.5
            # Downweight ineffective lessons (Sibyl 0.3x)
            if getattr(lesson, "effectiveness", "unverified") == "ineffective":
                weight *= 0.3
            scored.append((weight, lesson))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:max_lessons]]

    def build_overlay(
        self, stage_name: str, *, max_lessons: int = 5
    ) -> str:
        """Generate a prompt overlay string for a given stage.

        Combines lessons from the evolution store to guide future runs.
        Returns empty string if no relevant lessons exist.
        """
        lessons = self.query_for_stage(stage_name, max_lessons=max_lessons)
        if not lessons:
            return ""

        parts = ["## Evolution Lessons (from past runs)"]
        for i, lesson in enumerate(lessons, 1):
            severity_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(
                lesson.severity, "⚪"
            )
            parts.append(
                f"{i}. {severity_icon} [{lesson.category.upper()}] {lesson.description}"
            )
        return "\n".join(parts)

    def count(self) -> int:
        """Return total number of stored lessons."""
        return len(self.load_all())

    def export_to_memory(self, memory_store: Any) -> int:
        """Export lessons to a memory store.

        The memory_store must expose an add(content, category, metadata) method.
        Returns the number of lessons exported.
        """
        add_fn = getattr(memory_store, "add", None)
        if add_fn is None or not callable(add_fn):
            return 0

        lessons = self.load_all()
        exported = 0
        for lesson in lessons:
            weight = _time_weight(lesson.timestamp)
            if weight <= 0.0:
                continue
            try:
                add_fn(
                    content=lesson.description,
                    category=lesson.category,
                    metadata={
                        "source": "evolution",
                        "stage": lesson.stage_name,
                        "severity": lesson.severity,
                        "run_id": lesson.run_id,
                        "timestamp": lesson.timestamp,
                    },
                )
                exported += 1
            except Exception:
                continue
        return exported


def extract_lessons(
    stage_results: dict[str, dict[str, Any]],
    run_id: str = "",
) -> list[LessonEntry]:
    """Auto-extract lessons from StageResult dicts.

    stage_results: {stage_name: {status, error, score, duration, ...}}
    Returns a list of LessonEntry objects.
    """
    lessons: list[LessonEntry] = []
    now = time.time()

    for stage_name, result in stage_results.items():
        status = result.get("status", "unknown")
        error = result.get("error", "")
        score = result.get("score")
        duration = result.get("duration")

        # Extract error lessons
        if error:
            category, _ = _classify_error(error)
            severity = "error" if status == "failed" else "warning"
            lessons.append(
                LessonEntry(
                    stage_name=stage_name,
                    category=category,
                    severity=severity,
                    description=f"Stage '{stage_name}' error: {error[:200]}",
                    timestamp=now,
                    run_id=run_id,
                    metadata={"status": status, "score": score, "duration": duration},
                )
            )

        # Extract low-score warnings
        if score is not None and score < 0.5:
            lessons.append(
                LessonEntry(
                    stage_name=stage_name,
                    category=LessonCategory.PIPELINE,
                    severity="warning",
                    description=f"Stage '{stage_name}' low quality score: {score:.2f}",
                    timestamp=now,
                    run_id=run_id,
                    metadata={"score": score},
                )
            )

        # Extract slow stage warnings
        if duration is not None and duration > 300:  # > 5 minutes
            lessons.append(
                LessonEntry(
                    stage_name=stage_name,
                    category=LessonCategory.SYSTEM,
                    severity="info",
                    description=f"Stage '{stage_name}' slow: {duration:.1f}s",
                    timestamp=now,
                    run_id=run_id,
                    metadata={"duration": duration},
                )
            )

    return lessons


def build_overlay(
    stage_name: str,
    evolution_store: EvolutionStore | None = None,
    memory_store: Any = None,
    *,
    max_lessons: int = 5,
) -> str:
    """Build a combined overlay from evolution lessons and memory recall.

    This is the main entry point for generating prompt overlays.
    """
    parts: list[str] = []

    # Section 1: Evolution lessons
    if evolution_store is not None:
        evo_overlay = evolution_store.build_overlay(stage_name, max_lessons=max_lessons)
        if evo_overlay:
            parts.append(evo_overlay)

    # Section 2: Memory recall
    if memory_store is not None:
        recall_fn = getattr(memory_store, "recall", None)
        if recall_fn is not None and callable(recall_fn):
            try:
                memories = recall_fn(
                    query=stage_name,
                    category=None,
                    max_results=max_lessons,
                )
                if memories:
                    mem_parts = ["## Recalled Memories"]
                    for i, mem in enumerate(memories, 1):
                        content = getattr(mem, "content", str(mem))
                        mem_parts.append(f"{i}. {content}")
                    parts.append("\n".join(mem_parts))
            except Exception:
                pass

    return "\n\n".join(parts)
