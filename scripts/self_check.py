"""
Self-Check Diagnostics + Quality Trend.

Inspired by Sibyl's `get_self_check_diagnostics` and `quality_trend.md`.

After each run we inspect recent outcomes and the digest for warning signs:
  - declining quality trend (last few scores strictly decreasing)
  - recurring system errors (same issue_key fires >= 3 in the last few runs)
  - accumulation of ineffective lessons (a digested issue that keeps recurring
    but is still marked ineffective => the fix strategy isn't working)

When any signal fires, a diagnostics file is written. The next run's reflection
agent is told to explicitly address it (evidence-driven, forced response).
A healthy run clears the diagnostics file (clean state leaves no stale alarms).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "SelfChecker",
    "diagnose",
    "build_quality_trend_md",
]

_DECLINE_WINDOW = 3     # last N outcomes must be strictly decreasing
_RECUR_WINDOW = 5       # look at last N outcomes
_RECUR_THRESHOLD = 3    # same issue_key appearing at least this many times
_INEFFECTIVE_OCC = 4    # ineffective lesson with this many occurrences is a real problem


def _is_strictly_decreasing(scores: list[float]) -> bool:
    return all(scores[i] > scores[i + 1] for i in range(len(scores) - 1))


def diagnose(
    outcomes: list[dict[str, Any]],
    digest: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Return a diagnostics dict if any alarm fires, else None."""
    diag: dict[str, Any] = {}

    # 1) Declining quality trend over the most recent window.
    recent = [o for o in outcomes if o.get("score") is not None][- 8:]
    if len(recent) >= _DECLINE_WINDOW:
        scores = [float(o["score"]) for o in recent]
        tail = scores[-(_DECLINE_WINDOW):]
        if _is_strictly_decreasing(tail):
            diag["declining_trend"] = True
            diag["recent_scores"] = scores
            diag["recommendation"] = (
                "质量持续下降，建议检查实验设计与写作策略。"
            )

    # 2) Recurring system errors in the recent outcomes.
    recent_outcomes = outcomes[-_RECUR_WINDOW:]
    sys_keys = [o.get("issue_key") for o in recent_outcomes
                if o.get("category") == "system" and o.get("issue_key")]
    from collections import Counter
    recurring = [k for k, c in Counter(sys_keys).items() if c >= _RECUR_THRESHOLD]
    if recurring:
        diag["recurring_errors"] = recurring
        diag["recommendation"] = diag.get("recommendation", "") + (
            f"检测到系统错误反复出现: {recurring}，建议检查基础设施。"
        )

    # 3) Ineffective lessons that keep recurring.
    ineffective = [
        key for key, entry in digest.items()
        if getattr(entry, "effectiveness", "") == "ineffective"
        and getattr(entry, "total_occurrences", 1) >= _INEFFECTIVE_OCC
    ]
    if ineffective:
        diag["ineffective_lessons"] = ineffective
        diag["recommendation"] = diag.get("recommendation", "") + (
            f"以下教训未见效果，建议调整策略或同义词表: {ineffective}"
        )

    return diag if diag else None


def build_quality_trend_md(scores: list[float]) -> str:
    """Render the last opportunity trend markdown (up/down arrows per delta)."""
    if not scores:
        return ""
    lines = ["# Quality Trend (最近运行)"]
    prev = None
    for s in scores:
        if prev is None:
            arrow = "·"
        elif s > prev:
            arrow = "↑"
        elif s < prev:
            arrow = "↓"
        else:
            arrow = "→"
        lines.append(f"- {s:.2f} {arrow}")
        prev = s
    return "\n".join(lines)


class SelfChecker:
    """Writes self-check diagnostics and quality-trend reports under a directory."""

    def __init__(self, state_dir: Path | str) -> None:
        self._dir = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.diagnostics_path = self._dir / "self_check_diagnostics.json"
        self.quality_trend_path = self._dir / "quality_trend.md"

    def diagnose_and_report(
        self,
        outcomes: list[dict[str, Any]],
        digest: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        diag = diagnose(outcomes, digest)
        if diag:
            self.write_diagnostics(diag)
        else:
            self.clear_diagnostics()
        return diag

    def write_diagnostics(self, diag: dict[str, Any]) -> None:
        self.diagnostics_path.write_text(
            json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def clear_diagnostics(self) -> None:
        if self.diagnostics_path.exists():
            self.diagnostics_path.unlink()

    def write_quality_trend(self, scores: list[float]) -> None:
        self.quality_trend_path.write_text(
            build_quality_trend_md(scores), encoding="utf-8"
        )