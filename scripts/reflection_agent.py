"""
Reflection Agent + Rule Gate - LLM-based lesson extraction.

Inspired by Sibyl's reflection agent and AI Scientist v2's evidence-driven
reflection. After each pipeline run, an LLM analyzes the run's mechanical
evidence (scores, errors, durations, gate decisions) and produces structured
issues (root cause + actionable suggestion). A deterministic RuleGate then
filters out vague, unspecific, or low-testability suggestions before they
pollute the evolution store.

Design goals:
- Evidence-driven: the reflection prompt only feeds mechanical evidence.
- Hybrid: LLM generates; rules govern. If the LLM call fails we degrade to
  the existing rule-based extractor (never block the pipeline).
- Budget: exactly ONE LLM call per run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from self_evolution import extract_lessons

__all__ = [
    "ReflectionIssue",
    "ReflexReport",
    "RuleGate",
    "ReflectionAgent",
    "rule_extract_fallback",
    "VAGUE_KEYWORDS",
]

# Vague / generic advice that adds no value to future runs.
VAGUE_KEYWORDS = [
    "更仔细",
    "更认真",
    "注意质量",
    "提高质量",
    "注意细节",
    "尽量",
    "避免出错",
    "be careful",
    "pay attention",
    "be more careful",
    "improve quality",
]

# Prompt fragments that convert raw evidence into structured issues.
_SYSTEM_PROMPT = """你是学术论文生成流水线的反思 agent。分析本次运行的机械证据，找出可复用的教训。
你必须输出可在未来运行中避免的问题（issue），每条都要给出：类别、描述、根因、可执行建议、影响阶段、具体性评分、可测试性评分。

规则：
1. 只根据提供的机械证据（分数、报错、耗时、重试、评审意见等）推断，不要编造。
2. 描述和"建议"必须具体到可执行（含具体方法/参数/算法名），拒绝空泛建议（如"更仔细""注意质量"）。
3. if 上轮 self_check 诊断存在，必须回应并纳入改进建议。

仅输出 JSON，不要输出其他文字。JSON 格式：
{
  "issues": [
    {
      "category": "experiment|system|writing|analysis|literature|pipeline|ideation|planning|efficiency",
      "description": "具体问题描述",
      "root_cause": "根因分析",
      "suggestion": "可执行的具体建议（含方法名/参数）",
      "affected_stages": ["step2"],
      "specificity": 5,
      "testability": 5
    }
  ],
  "success_patterns": ["有效的实践，未来应继续保持"],
  "quality_trajectory": {"direction": "up|down|flat", "notes": "简要说明"},
  "self_check_response": "（若存在诊断，给出针对性措施）"
}"""


@dataclass
class ReflectionIssue:
    """A single analyzed issue from a pipeline run."""

    category: str
    description: str
    root_cause: str = ""
    suggestion: str = ""
    affected_stages: list[str] = field(default_factory=list)
    specificity: int = 0      # 1-5
    testability: int = 0      # 1-5
    source: str = "reflection"  # reflection | rule
    run_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "description": self.description,
            "root_cause": self.root_cause,
            "suggestion": self.suggestion,
            "affected_stages": self.affected_stages,
            "specificity": self.specificity,
            "testability": self.testability,
            "source": self.source,
            "run_id": self.run_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReflectionIssue:
        return cls(
            category=data.get("category", "pipeline"),
            description=data.get("description", ""),
            root_cause=data.get("root_cause", ""),
            suggestion=data.get("suggestion", ""),
            affected_stages=data.get("affected_stages", []),
            specificity=int(data.get("specificity", 0) or 0),
            testability=int(data.get("testability", 0) or 0),
            source=data.get("source", "reflection"),
            run_id=data.get("run_id", ""),
        )


@dataclass
class ReflexReport:
    """The full output of a reflection pass."""

    issues: list[ReflectionIssue] = field(default_factory=list)
    success_patterns: list[str] = field(default_factory=list)
    quality_trajectory: dict[str, Any] = field(default_factory=dict)
    self_check_response: str = ""
    fallback_used: bool = False
    raw: str = ""


class RuleGate:
    """Deterministic filter that keeps only specific, testable issues."""

    def __init__(self, min_length: int = 15, max_lessons: int = 5) -> None:
        self.min_length = min_length
        self.max_lessons = max_lessons

    @staticmethod
    def _contains_vague(text: str) -> bool:
        low = (text or "").lower()
        return any(kw in low for kw in VAGUE_KEYWORDS)

    def filter(self, issues: list[ReflectionIssue]) -> list[ReflectionIssue]:
        kept: list[ReflectionIssue] = []
        for issue in issues:
            desc = issue.description or ""
            sugg = issue.suggestion or ""
            if self._contains_vague(desc) or self._contains_vague(sugg):
                continue
            if len(desc) < self.min_length or len(sugg) < self.min_length:
                continue
            if issue.specificity < 3 or issue.testability < 3:
                continue
            kept.append(issue)
        kept.sort(key=lambda i: (i.specificity * i.testability), reverse=True)
        return kept[: self.max_lessons]


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def _extract_json_block(content: str) -> Optional[dict[str, Any]]:
    """Parse JSON from model output, tolerating code fences and trailing text."""
    if not content:
        return None
    m = _JSON_FENCE_RE.search(content)
    candidate = m.group(1) if m else content
    try:
        parsed = json.loads(candidate.strip())
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    # Try to find first balanced { ... }
    try:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    return None


def _build_evidence_prompt(evidence: dict[str, Any], run_id: str = "") -> str:
    """Serialize mechanical evidence into a compact, JSON-serializable prompt string."""
    return json.dumps(evidence, ensure_ascii=False, indent=2, default=str)


def rule_extract_fallback(
    stage_results: dict[str, dict[str, Any]], run_id: str = ""
) -> list[ReflectionIssue]:
    """Deterministic fallback when the LLM reflection is unavailable.

    Delegates to self_evolution.extract_lessons and marks results as source="rule".
    """
    entries = extract_lessons(stage_results, run_id=run_id)
    return [
        ReflectionIssue(
            category=e.category,
            description=e.description,
            root_cause="",
            suggestion="",
            affected_stages=[e.stage_name],
            specificity=0,
            testability=0,
            source="rule",
            run_id=run_id,
        )
        for e in entries
    ]


class ReflectionAgent:
    """Runs an LLM-based reflection over run evidence with a rule gate fallback.

    Args:
        llm_fn: async callable `async def llm_fn(system_prompt, user_prompt, **kwargs) -> dict`.
                The returned dict must contain a "content" key. If None, only the
                deterministic fallback is used.
        max_evidence_tokens: roughly cap evidence size (via truncation).
    """

    def __init__(
        self,
        llm_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None,
        max_evidence_chars: int = 8000,
    ) -> None:
        self._llm_fn = llm_fn
        self.max_evidence_chars = max_evidence_chars
        self.gate = RuleGate()

    async def reflect(
        self,
        evidence: dict[str, Any],
        run_id: str = "",
    ) -> ReflexReport:
        if self._llm_fn is None:
            issues = rule_extract_fallback(evidence, run_id=run_id)
            return ReflexReport(issues=issues, fallback_used=True, raw="")

        prompt = _build_evidence_prompt(evidence, run_id)
        # Truncate overly long evidence to protect the prompt budget.
        if len(prompt) > self.max_evidence_chars:
            prompt = prompt[: self.max_evidence_chars] + "\n...(证据被截断)"

        user_prompt = (
            "请基于以下本次运行的机械证据进行反思，输出 JSON。\n\n"
            f"【证据】\n{prompt}\n\n"
            "【运行ID】" + run_id
        )

        try:
            resp = await self._llm_fn(_SYSTEM_PROMPT, user_prompt)
        except Exception:
            issues = rule_extract_fallback(evidence, run_id=run_id)
            return ReflexReport(issues=issues, fallback_used=True, raw="")

        content = resp.get("content", "") if isinstance(resp, dict) else ""
        parsed = _extract_json_block(content)

        if parsed is None:
            issues = rule_extract_fallback(evidence, run_id=run_id)
            return ReflexReport(issues=issues, fallback_used=True, raw=content)

        raw_issues = [
            ReflectionIssue.from_dict({**i, "run_id": run_id})
            for i in parsed.get("issues", [])
            if isinstance(i, dict)
        ]
        issues = self.gate.filter(raw_issues)
        return ReflexReport(
            issues=issues,
            success_patterns=[
                s for s in parsed.get("success_patterns", []) if isinstance(s, str)
            ],
            quality_trajectory=parsed.get("quality_trajectory", {}),
            self_check_response=parsed.get("self_check_response", ""),
            fallback_used=False,
            raw=content,
        )