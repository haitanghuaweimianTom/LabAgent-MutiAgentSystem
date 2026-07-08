"""同行评议 Agent —— Phase 2 流水线扩容。

定位：在 writer 之后插入"模拟同行评议"步骤。Agent 扮演 CCF-A 审稿人，
对生成的论文做四维度评分 + 主/次要意见 + 接受/修订/拒稿建议 +
具体修改建议。

【严格控制幻觉】
- 只根据实际传入的论文内容评分，不编造具体页码行号
- 评分必须基于 *实际可见* 的章节、公式、图表
- suggested_edits 要具体可执行（"补充数据集引用"而非"改进方法部分"）

【与 Writer 自评-重写的区别】
- writer_agent 的 CRITIQUE 是同 Agent 自评（四维 25 分制，阈值 75）
- peer_review_agent 是 *外部* 模拟审稿人（1-5 分制），可独立返回
  accept/revise/reject。revision 决定会触发 writer 重写（见 orchestrator）。
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentFactory
from ..core.security import wrap_user_content
from ..core.paper_templates import load_template as _load_template_from_registry

logger = logging.getLogger(__name__)


PEER_REVIEW_SYSTEM = """你是一名严谨的 CCF-A 类会议/期刊审稿人。
请对给定论文（LaTeX 源码 + 章节摘要）做同行评议。

【严格控制幻觉】
- 只评估论文 *实际* 包含的章节、方法、实验；不要凭空补充论文里没有的引用或结果
- suggested_edits 要具体到章节或公式（"在 Section 4.2 补充与 SoTA 的对比"，
  不要泛泛而谈"改进方法部分"）
- 分数（1-5）必须基于论文 *实际可见* 的内容

【实验可复现性检查（如论文包含实验）】
- 是否有完整的 train/eval 脚本或实验流程描述？
- 是否设置了随机种子（random seed）？
- 是否记录了关键超参数？
- baseline 对比是否有明确来源说明（引用或自实现）？
- 数据集是否有公开引用或链接？

【严格控制幻觉】
- 只评估论文 *实际* 包含的章节、方法、实验；不要凭空补充论文里没有的引用或结果
- suggested_edits 要具体到章节或公式（"在 Section 4.2 补充与 SoTA 的对比"，
  不要泛泛而谈"改进方法部分"）
- 分数（1-5）必须基于论文 *实际可见* 的内容

【四维度评分（每项 1-5，越高越好）】
- novelty: 相对于已有工作的新意
- soundness: 技术严谨性（理论 + 实验）
- clarity: 表述清晰度（结构 / 语言 / 图表）
- significance: 影响力（应用价值 / 学术价值）

【推荐意见】
- "accept": 四维均 ≥ 4，可直接接收
- "revise": 总体可发但有显著缺陷，建议大修或小修
- "reject": 任一维度 < 2 或总体 < 2.5，建议拒稿

【输出 schema（严格 JSON，无任何其他文字）】
{
  "scores": {
    "novelty": 1-5,
    "soundness": 1-5,
    "clarity": 1-5,
    "significance": 1-5
  },
  "comments": {
    "major": ["主要问题 1 (≤80字)", ...],
    "minor": ["次要问题 1 (≤60字)", ...]
  },
  "reproducibility": {
    "has_train_script": true|false,
    "has_random_seed": true|false,
    "has_hyperparams": true|false,
    "has_baseline_source": true|false,
    "has_dataset_reference": true|false,
    "score": 1-5
  },
  "recommendation": "accept|revise|reject",
  "suggested_edits": [
    {"target": "Section X / Figure Y / Table Z / Algorithm N", "change": "具体修改建议 (≤80字)"},
    ...
  ],
  "confidence": 1-5
}
"""


@AgentFactory.register("peer_review_agent")
class PeerReviewAgent(BaseAgent):
    """模拟同行评议的 Agent。"""

    name = "peer_review_agent"
    label = "模拟审稿人"
    description = "对生成的论文做四维度评分 + 接受/修订/拒稿建议 + 具体修改"
    default_model = ""

    # 触发重写的阈值（任一维度低于此值 → recommend revise）
    REVISE_THRESHOLD = 3

    def get_system_prompt(self) -> str:
        return PEER_REVIEW_SYSTEM

    async def execute(
        self,
        task_input: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行同行评议。

        Args:
            task_input: 包含 ``latex_code`` 或 ``chapter_summaries``；可选 ``template_id``。
            context: 上下文。

        Returns:
            {
                "scores": {novelty, soundness, clarity, significance},
                "overall_score": 1-5（均值）,
                "comments": {major, minor},
                "recommendation": "accept"|"revise"|"reject",
                "suggested_edits": [...],
                "confidence": 1-5,
                "raw_text": str,
                "error": None|str,
            }
        """
        latex_code = task_input.get("latex_code", "")
        chapter_summaries = task_input.get("chapter_summaries", [])
        template_id = task_input.get("template_id", "math_modeling")
        threshold = self.get_acceptance_threshold(template_id)

        # 用模板的 acceptance_threshold（百分制）作为质量门槛辅助建议
        # 但内部推荐意见仍按 1-5 分制
        try:
            user_prompt = self._build_user_prompt(latex_code, chapter_summaries, threshold)
            raw_text = await self._call_llm_review(user_prompt)
            review = self._parse_review(raw_text)
            return {
                "scores": review["scores"],
                "overall_score": review["overall_score"],
                "comments": review["comments"],
                "recommendation": review["recommendation"],
                "suggested_edits": review["suggested_edits"],
                "confidence": review["confidence"],
                "raw_text": raw_text,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error(f"peer_review_agent failed: {exc}")
            raise RuntimeError(f"论文评审失败：LLM 调用异常 ({exc})") from exc

    @staticmethod
    def get_acceptance_threshold(template_id: str) -> int:
        """返回模板的章节百分制门槛，用于辅助判定。"""
        try:
            tpl = _load_template_from_registry(template_id)
            if tpl and tpl.acceptance_threshold:
                return tpl.acceptance_threshold
        except Exception:  # noqa: BLE001
            pass
        return 75

    # ---------- 内部方法 ----------

    @staticmethod
    def _build_user_prompt(latex_code: str, chapter_summaries: List[Dict[str, Any]], threshold: int) -> str:
        parts: List[str] = [
            f"【模板质量门槛（百分制）】{threshold}",
            "",
        ]
        if latex_code:
            parts.append("【LaTeX 源码（节选，前 4000 字）】")
            parts.append(wrap_user_content(latex_code[:4000], "latex_code"))
            parts.append("")
        if chapter_summaries:
            parts.append("【章节摘要】")
            for cs in chapter_summaries[:20]:
                title = cs.get("title") or cs.get("id") or "?"
                summary = (cs.get("summary") or cs.get("content") or "")[:300]
                parts.append(f"- {title}: {summary}")
            parts.append("")
        parts.append(
            "【请按系统提示词定义的 schema 输出 JSON，"
            "不要包含任何文字解释，只输出 JSON。】"
        )
        return "\n".join(parts)

    async def _call_llm_review(self, user_prompt: str) -> str:
        try:
            messages = [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": user_prompt},
            ]
            response = await self.call_llm(messages=messages, temperature=0.2)
            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
            if isinstance(response, str):
                return response
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"call_llm path failed: {exc}")
        # 兜底：返回中性评分
        return json.dumps({
            "scores": {"novelty": 3, "soundness": 3, "clarity": 3, "significance": 3},
            "comments": {"major": [], "minor": []},
            "recommendation": "revise",
            "suggested_edits": [],
            "confidence": 1,
        }, ensure_ascii=False)

    def _parse_review(self, raw_text: str) -> Dict[str, Any]:
        if not raw_text:
            raw_text = "{}"
        match = re.search(r"\{[\s\S]*\}", raw_text)
        if not match:
            return self._empty_review()
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return self._empty_review()

        scores = data.get("scores", {}) or {}
        try:
            novelty = int(scores.get("novelty", 3))
            soundness = int(scores.get("soundness", 3))
            clarity = int(scores.get("clarity", 3))
            significance = int(scores.get("significance", 3))
        except (ValueError, TypeError):
            return self._empty_review()

        # 强制范围 1-5
        clamp = lambda x: max(1, min(5, x))
        novelty, soundness, clarity, significance = (
            clamp(novelty), clamp(soundness), clamp(clarity), clamp(significance)
        )
        overall = round((novelty + soundness + clarity + significance) / 4, 2)

        # 强制 recommendation
        rec = (data.get("recommendation") or "revise").lower()
        if rec not in ("accept", "revise", "reject"):
            rec = "revise"
        if rec == "accept" and (novelty < 4 or soundness < 4 or clarity < 4 or significance < 4):
            rec = "revise"
        if rec == "reject" and overall >= 2.5:
            rec = "revise"

        return {
            "scores": {
                "novelty": novelty,
                "soundness": soundness,
                "clarity": clarity,
                "significance": significance,
            },
            "overall_score": overall,
            "comments": {
                "major": list(data.get("comments", {}).get("major", []) or []),
                "minor": list(data.get("comments", {}).get("minor", []) or []),
            },
            "reproducibility": data.get("reproducibility", {
                "has_train_script": False,
                "has_random_seed": False,
                "has_hyperparams": False,
                "has_baseline_source": False,
                "has_dataset_reference": False,
                "score": 3,
            }),
            "recommendation": rec,
            "suggested_edits": list(data.get("suggested_edits", []) or []),
            "confidence": clamp(int(data.get("confidence", 3))),
        }

    @staticmethod
    def _empty_review() -> Dict[str, Any]:
        return {
            "scores": {"novelty": 3, "soundness": 3, "clarity": 3, "significance": 3},
            "overall_score": 3.0,
            "comments": {"major": [], "minor": []},
            "reproducibility": {
                "has_train_script": False,
                "has_random_seed": False,
                "has_hyperparams": False,
                "has_baseline_source": False,
                "has_dataset_reference": False,
                "score": 3,
            },
            "recommendation": "revise",
            "suggested_edits": [],
            "confidence": 1,
        }
