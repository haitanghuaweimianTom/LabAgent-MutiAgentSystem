"""
Enhanced Debate Module - 6-Persona Multi-Perspective Debate

Inspired by Sibyl's 6-agent multi-perspective debate system.
Expands from 3 to 6 specialized personas for comprehensive evaluation.

Personas:
1. Planner: Research strategy, novelty, contribution
2. Experimenter: Experiment design, methodology, execution
3. Critic: Quality, rigor, completeness
4. Skeptic: Devil's advocate, challenges assumptions
5. Writer: Paper structure, narrative flow
6. Editor: Language, clarity, presentation
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "DebatePersona",
    "DebateRound",
    "DebateResult",
    "EnhancedDebate",
]

logger = logging.getLogger(__name__)


@dataclass
class DebatePersona:
    """A specialized debate persona with role-specific evaluation criteria."""

    name: str
    system_prompt: str
    focus_areas: list[str]
    weight: float = 1.0  # Importance weight for synthesis

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "focus_areas": self.focus_areas,
            "weight": self.weight,
        }


@dataclass
class DebateRound:
    """A single round of debate with all persona responses."""

    round_num: int
    responses: list[dict[str, Any]] = field(default_factory=list)
    synthesis: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_num": self.round_num,
            "responses": self.responses,
            "synthesis": self.synthesis,
        }


@dataclass
class DebateResult:
    """Complete debate result with rounds and final synthesis."""

    topic: str
    rounds: list[DebateRound] = field(default_factory=list)
    final_synthesis: str = ""
    consensus_score: float = 0.0
    key_issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "rounds": [r.to_dict() for r in self.rounds],
            "final_synthesis": self.final_synthesis,
            "consensus_score": self.consensus_score,
            "key_issues": self.key_issues,
            "recommendations": self.recommendations,
        }


# Default 6 personas based on Sibyl's multi-perspective debate
DEFAULT_PERSONAS = [
    DebatePersona(
        name="Planner",
        system_prompt=(
            "你是研究策略规划师。你关注：\n"
            "1. 研究问题的新颖性和重要性\n"
            "2. 贡献点是否清晰明确\n"
            "3. 研究路线是否合理\n"
            "4. 与现有工作的区别和优势\n"
            "请从战略角度评估方案。"
        ),
        focus_areas=["novelty", "contribution", "strategy", "comparison"],
        weight=1.2,
    ),
    DebatePersona(
        name="Experimenter",
        system_prompt=(
            "你是实验设计专家。你关注：\n"
            "1. 实验设计的科学性和完整性\n"
            "2. 方法论是否合理\n"
            "3. 评估指标是否恰当\n"
            "4. 实验可重复性\n"
            "请从实验角度评估方案。"
        ),
        focus_areas=["methodology", "experiment_design", "reproducibility", "metrics"],
        weight=1.1,
    ),
    DebatePersona(
        name="Critic",
        system_prompt=(
            "你是质量评审员。你关注：\n"
            "1. 论文的整体质量\n"
            "2. 逻辑是否严谨\n"
            "3. 证据是否充分\n"
            "4. 是否存在重大缺陷\n"
            "请严格评审，指出所有问题。"
        ),
        focus_areas=["quality", "rigor", "evidence", "defects"],
        weight=1.3,
    ),
    DebatePersona(
        name="Skeptic",
        system_prompt=(
            "你是怀疑论者（魔鬼代言人）。你关注：\n"
            "1. 方案的潜在风险和局限性\n"
            "2. 假设是否合理\n"
            "3. 结论是否过度推广\n"
            "4. 反驳可能的批评\n"
            "请挑战方案中的薄弱环节。"
        ),
        focus_areas=["risks", "limitations", "assumptions", "challenges"],
        weight=1.0,
    ),
    DebatePersona(
        name="Writer",
        system_prompt=(
            "你是论文结构师。你关注：\n"
            "1. 论文结构是否清晰\n"
            "2. 故事线是否连贯\n"
            "3. 各部分逻辑是否通顺\n"
            "4. 是否符合学术写作规范\n"
            "请从写作角度评估。"
        ),
        focus_areas=["structure", "narrative", "flow", "conventions"],
        weight=0.9,
    ),
    DebatePersona(
        name="Editor",
        system_prompt=(
            "你是语言编辑。你关注：\n"
            "1. 语言表达是否清晰\n"
            "2. 术语使用是否准确\n"
            "3. 图表描述是否恰当\n"
            "4. 格式是否统一\n"
            "请从语言角度给出修改建议。"
        ),
        focus_areas=["language", "terminology", "clarity", "formatting"],
        weight=0.8,
    ),
]


class EnhancedDebate:
    """6-persona enhanced debate system.

    Features:
    - 6 specialized personas with role-specific evaluation
    - Multi-round debate with synthesis
    - Consensus scoring
    - Key issue extraction
    - Recommendation generation
    """

    def __init__(
        self,
        call_fn,
        models: list[str] | None = None,
        rounds: int = 2,
        personas: list[DebatePersona] | None = None,
    ) -> None:
        """
        Args:
            call_fn: Async function (system, user, max_tokens) -> dict
            models: Candidate models (for multi-model debate)
            rounds: Number of debate rounds
            personas: Custom personas (default: 6 standard personas)
        """
        self.call_fn = call_fn
        self.models = models or ["MiniMax-M3"]
        self.rounds = rounds
        self.personas = personas or DEFAULT_PERSONAS

    async def debate(
        self,
        topic: str,
        context: str,
        *,
        max_tokens_per_persona: int = 4000,
    ) -> DebateResult:
        """Run multi-persona debate on a topic.

        Args:
            topic: Debate topic/question
            context: Supporting context (paper draft, experiment results, etc.)
            max_tokens_per_persona: Max tokens per persona response

        Returns:
            DebateResult with rounds, synthesis, and recommendations
        """
        result = DebateResult(topic=topic)

        for round_num in range(self.rounds):
            round_obj = DebateRound(round_num=round_num + 1)

            # Each persona evaluates
            for persona in self.personas:
                response = await self._get_persona_response(
                    persona, topic, context, round_num + 1, max_tokens_per_persona
                )
                round_obj.responses.append(response)

            # Synthesize round
            round_obj.synthesis = self._synthesize_round(round_obj.responses, topic)
            result.rounds.append(round_obj)

        # Final synthesis
        result.final_synthesis = self._final_synthesis(result.rounds, topic)
        result.consensus_score = self._compute_consensus(result.rounds)
        result.key_issues = self._extract_key_issues(result.rounds)
        result.recommendations = self._generate_recommendations(result.rounds)

        return result

    async def _get_persona_response(
        self,
        persona: DebatePersona,
        topic: str,
        context: str,
        round_num: int,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Get response from a single persona."""
        system = (
            f"{persona.system_prompt}\n\n"
            f"这是第 {round_num}/{self.rounds} 轮辩论。\n"
            f"请对以下主题给出你的评估和建议。"
        )

        user = f"【辩论主题】\n{topic}\n\n【上下文】\n{context[:4000]}"

        try:
            resp = await self.call_fn(system, user, max_tokens=max_tokens)
            feedback = resp.get("content", "")
        except Exception as e:
            logger.warning(f"Persona {persona.name} failed: {e}")
            feedback = f"评估失败: {e}"

        return {
            "name": persona.name,
            "feedback": feedback,
            "round": round_num,
            "focus_areas": persona.focus_areas,
        }

    def _synthesize_round(self, responses: list[dict], topic: str) -> str:
        """Synthesize responses from a single debate round."""
        if not responses:
            return ""

        lines = [f"## Round Synthesis — {topic}\n"]

        for resp in responses:
            lines.append(f"### {resp['name']} ({', '.join(resp['focus_areas'][:2])})")
            lines.append(resp["feedback"][:600])
            lines.append("")

        return "\n".join(lines)

    def _final_synthesis(self, rounds: list[DebateRound], topic: str) -> str:
        """Generate final synthesis from all rounds."""
        if not rounds:
            return ""

        lines = [f"# Final Debate Synthesis — {topic}\n"]

        # Collect all responses by persona
        persona_views: dict[str, list[str]] = {}
        for round_obj in rounds:
            for resp in round_obj.responses:
                name = resp["name"]
                if name not in persona_views:
                    persona_views[name] = []
                persona_views[name].append(resp["feedback"])

        # Summarize each persona's final view
        for persona in self.personas:
            views = persona_views.get(persona.name, [])
            if views:
                lines.append(f"## {persona.name}")
                # Take the last (most mature) view
                lines.append(views[-1][:500])
                lines.append("")

        return "\n".join(lines)

    def _compute_consensus(self, rounds: list[DebateRound]) -> float:
        """Compute consensus score (0-1) based on persona agreement."""
        if not rounds or not rounds[-1].responses:
            return 0.0

        # Simple heuristic: check if key terms appear across personas
        all_text = " ".join(
            resp["feedback"] for resp in rounds[-1].responses
        ).lower()

        # Positive indicators
        positive_terms = ["推荐", "可行", "合理", "有效", "改进", "优势"]
        negative_terms = ["风险", "问题", "缺陷", "不足", "改进", "挑战"]

        pos_count = sum(1 for t in positive_terms if t in all_text)
        neg_count = sum(1 for t in negative_terms if t in all_text)

        total = pos_count + neg_count
        if total == 0:
            return 0.5

        return pos_count / total

    def _extract_key_issues(self, rounds: list[DebateRound]) -> list[str]:
        """Extract key issues from debate responses."""
        issues = []

        # Look for critical issues from Skeptic and Critic
        for round_obj in rounds:
            for resp in round_obj.responses:
                if resp["name"] in ("Skeptic", "Critic"):
                    # Extract sentences with issue indicators
                    for sentence in resp["feedback"].split("。"):
                        if any(kw in sentence for kw in ["问题", "风险", "缺陷", "不足", "挑战"]):
                            issues.append(sentence.strip()[:200])

        # Deduplicate and limit
        seen = set()
        unique_issues = []
        for issue in issues:
            if issue not in seen:
                seen.add(issue)
                unique_issues.append(issue)
        return unique_issues[:10]

    def _generate_recommendations(self, rounds: list[DebateRound]) -> list[str]:
        """Generate actionable recommendations from debate."""
        recommendations = []

        for round_obj in rounds:
            for resp in round_obj.responses:
                if resp["name"] == "Planner":
                    # Extract recommendations from Planner
                    for line in resp["feedback"].split("\n"):
                        if any(kw in line for kw in ["建议", "推荐", "应该", "需要"]):
                            recommendations.append(line.strip()[:200])

        # Deduplicate
        seen = set()
        unique_recs = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recs.append(rec)
        return unique_recs[:10]
