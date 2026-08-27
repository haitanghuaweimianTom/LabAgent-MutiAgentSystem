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

__all__ = [
    "LessonCategory",
    "LessonEntry",
    "EvolutionStore",
    "extract_lessons",
    "build_overlay",
]


class LessonCategory(str, Enum):
    """7 issue categories for classifying lessons."""

    SYSTEM = "system"
    EXPERIMENT = "experiment"
    WRITING = "writing"
    ANALYSIS = "analysis"
    LITERATURE = "literature"
    PIPELINE = "pipeline"
    IDEATION = "ideation"


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

    def load_all(self) -> list[LessonEntry]:
        """Load all lessons from disk."""
        if not self._lessons_path.exists():
            return []
        lessons: list[LessonEntry] = []
        for line in self._lessons_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                lessons.append(LessonEntry.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                continue
        return lessons

    def query_for_stage(
        self, stage_name: str, *, max_lessons: int = 5
    ) -> list[LessonEntry]:
        """Return the most relevant lessons for a stage, weighted by recency.

        Includes lessons that directly match the stage, plus high-severity
        lessons from related stages.
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
