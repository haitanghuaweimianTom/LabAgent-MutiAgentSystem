"""
Context Filtered Overlay - Stage-routed, relevance-scored prompt injection.

Inspired by Sibyl's `filter_relevant_lessons` + `render_skill_prompt`.

Not every lesson is relevant to every stage. We route lessons to the stages
that matter and rank them by a relevance score combining:
  - stage-category match
  - topic / problem word overlap
  - whether a current (fresh) issue's text is a substring
  - effectiveness (effective adds, ineffective subtracts)
  - weighted frequency (how often / how recently the issue fired)

The top-N (default 8) become a compact markdown overlay appended to the step's
user prompt, together with the injected issue-keys (needed later to decide
whether a lesson was actually surfaced before we judge it as recurred).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from self_evolution import LessonCategory, LessonV2

__all__ = [
    "STAGE_CATEGORIES",
    "score_lesson_for_stage",
    "build_context_overlay",
]

# Route the 8 issue categories to the pipeline's steps.
STAGE_CATEGORIES: dict[str, list[str]] = {
    "step1":  ["literature", "ideation", "planning"],
    "step1b": ["ideation", "planning"],
    "step2":  ["experiment", "analysis", "ideation"],
    "step3":  ["system", "experiment", "efficiency"],
    "step4":  ["writing", "analysis"],
    "step5":  ["writing", "analysis"],
    "step6":  ["system", "efficiency"],
    "step7":  ["writing", "pipeline"],
}

_DEFAULT_STAGE = "step4"

_WEIGHT_CATEGORY = 3.0
_WEIGHT_TOPIC = 2.0
_WEIGHT_RECENT = 3.0
_WEIGHT_EFFECTIVE = 1.0
_WEIGHT_INEFFECTIVE = -2.0
_WEIGHT_FREQ = 2.0  # cap on weighted_frequency/contribution


def _stage_categories(stage: str) -> list[str]:
    return STAGE_CATEGORIES.get(stage, STAGE_CATEGORIES[_DEFAULT_STAGE])


def _tokens(text: str) -> set[str]:
    tokens = set()
    for ch in "，。；、！？(),.:;'\"-_/":
        text = text.replace(ch, " ")
    for tok in text.lower().split():
        if len(tok) >= 2:
            tokens.add(tok)
    return tokens


def score_lesson_for_stage(lesson: LessonV2, stage: str) -> float:
    """Return a relevance score for injecting this lesson into a step's prompt."""
    score = 0.0
    cats = _stage_categories(stage)
    if lesson.category in cats:
        score += _WEIGHT_CATEGORY
    # weighted frequency (time-decayed), mapped into [0, _WEIGHT_FREQ]
    score += min(getattr(lesson, "weighted_frequency", 1.0) / 3.0, _WEIGHT_FREQ)
    # effectiveness
    eff = getattr(lesson, "effectiveness", "unverified")
    if eff == "effective":
        score += _WEIGHT_EFFECTIVE
    elif eff == "ineffective":
        score += _WEIGHT_INEFFECTIVE
    return score


def _topic_overlap(lesson: LessonV2, topic: str) -> float:
    if not topic:
        return 0.0
    topic_tokens = _tokens(topic)
    if not topic_tokens:
        return 0.0
    lesson_tokens = _tokens(lesson.description) | _tokens(lesson.suggestion)
    overlap = len(topic_tokens & lesson_tokens)
    return min(overlap, _WEIGHT_TOPIC) * (overlap / max(len(topic_tokens), 1))


def _recent_substring_bonus(lesson: LessonV2, recent_issues: list[str]) -> bool:
    if not recent_issues:
        return False
    for issue in recent_issues:
        if not issue:
            continue
        if issue in lesson.description or lesson.description in issue:
            return True
    return False


def _format_lesson(lesson: LessonV2) -> str:
    eff = getattr(lesson, "effectiveness", "unverified")
    severity_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(lesson.severity, "⚪")
    occ = getattr(lesson, "total_occurrences", 1)
    line = f"- {severity_icon} [{lesson.category.upper()}][{eff}] {lesson.description} (出现{occ}次)"
    if lesson.suggestion:
        line += f"\n  建议: {lesson.suggestion}"
    return line


def build_context_overlay(
    stage: str,
    lessons: list[LessonV2],
    *,
    topic: str = "",
    recent_issues: list[str] | None = None,
    max_lessons: int = 8,
    return_keys: bool = False,
) -> str | tuple[str, list[str]]:
    """Build a context-filtered prompt overlay for a stage.

    Args:
        stage: pipeline step name (e.g. "step3").
        lessons: candidate lessons (typically from the run's snapshot).
        topic: the research problem text (for topic overlap boosting).
        recent_issues: issues detected in the current run (substring boost).
        max_lessons: how many lessons to include (top-N by score).
        return_keys: if True, also return the injected issue_keys.

    Returns:
        overlay markdown string, or (overlay, injected_keys) if return_keys.
    """
    lessons = list(lessons)
    if not lessons:
        return ("", []) if return_keys else ""

    recent_issues = recent_issues or []
    scored: list[tuple[float, LessonV2]] = []
    for lesson in lessons:
        score = score_lesson_for_stage(lesson, stage)
        score += _topic_overlap(lesson, topic)
        if _recent_substring_bonus(lesson, recent_issues):
            score += _WEIGHT_RECENT
        scored.append((score, lesson))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max_lessons]

    if not top:
        return ("", []) if return_keys else ""

    injected_keys = [l.issue_key for _, l in top if l.issue_key]
    parts = ["## 经验教训 (上下文过滤)"]
    for _, lesson in top:
        parts.append(_format_lesson(lesson))

    overlay = "\n".join(parts)
    return (overlay, injected_keys) if return_keys else overlay