"""
Problem Ideation (AI-Scientist-inspired)
=========================================

Before problem decomposition, generate creative research angles and
cross-domain method borrowing ideas to enrich the analysis.

Inspired by SakanaAI's AI-Scientist-v2 perform_ideation_temp_free.py,
which generates novel research proposals before experiment design.
"""

import json
from typing import Dict, List, Any, Optional, Callable


class ProblemIdeation:
    """
    Generates diverse research angles for a mathematical modeling problem.

    Each idea includes:
    - A high-level research direction
    - Suggested methods (including cross-domain borrowing)
    - Novelty assessment
    - Concrete experiments/approaches
    """

    def __init__(self, call_llm: Callable[[str, Optional[str]], str]):
        self.call_llm = call_llm

    def generate_ideas(
        self,
        problem_text: str,
        data_descriptions: str = "",
        num_ideas: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Generate diverse research ideas for the given problem.

        Returns list of dicts: {title, high_level_idea, approach, novelty, cross_domain, experiments}
        """
        system_prompt = (
            "你是一位跨学科研究专家，擅长从多个角度分析数学建模问题，"
            "并能从其他领域借鉴方法。请生成多样化的研究方向建议。"
        )

        prompt = f"""请对以下数学建模问题生成 {num_ideas} 个不同的研究方向和创意视角。

【赛题内容】
{problem_text[:3000]}

{f'【数据文件描述】\n{data_descriptions[:1000]}' if data_descriptions else ''}

对于每个研究方向，请包含以下内容：
1. **标题**：简短描述该研究方向
2. **核心思路**：该方向的主要想法（200字）
3. **方法建议**：推荐使用的具体方法和技术
4. **跨学科借鉴**：从其他领域（如物理学、生物学、经济学、计算机科学、工程学等）借鉴的方法
5. **新颖性评估**：为什么这个方向有趣/有价值
6. **具体实验/步骤**：可操作的研究步骤（3-5步）

要求：
- 每个方向应该明显不同，不要重复
- 至少包含1-2个非传统/创意性的角度
- 方法建议应该具体、可操作
- 跨学科借鉴要说明为什么该领域的方法适用于当前问题

输出严格的JSON格式数组，每个元素包含：
{{
  "title": "方向标题",
  "high_level_idea": "核心思路描述",
  "approach": "方法建议",
  "novelty": "新颖性评估",
  "cross_domain": "跨学科借鉴说明",
  "experiments": ["步骤1", "步骤2", "步骤3"]
}}"""

        result = self.call_llm(prompt, system_prompt)
        return self._parse_ideas(result, num_ideas)

    def format_for_analysis(self, ideas: List[Dict[str, Any]]) -> str:
        """Format ideas for injection into the problem analysis prompt."""
        if not ideas:
            return "未生成研究视角建议。"

        parts = ["以下是从多个研究视角生成的创意方向，供综合分析时参考：\n"]
        for i, idea in enumerate(ideas, 1):
            parts.append(
                f"**视角{i}: {idea.get('title', '未知')}**\n"
                f"- 核心思路: {idea.get('high_level_idea', '')[:200]}\n"
                f"- 方法: {idea.get('approach', '')[:200]}\n"
                f"- 跨学科借鉴: {idea.get('cross_domain', '')[:200]}\n"
                f"- 新颖性: {idea.get('novelty', '')[:150]}\n"
                f"- 具体步骤: {'; '.join(idea.get('experiments', [])[:3])}\n"
            )
        return "\n".join(parts)

    def _parse_ideas(self, text: str, expected: int) -> List[Dict[str, Any]]:
        """Parse LLM output into idea dicts."""
        try:
            # Try to extract JSON array
            import re
            json_match = re.search(r'\[.*\]', text, re.DOTALL)
            if json_match:
                ideas = json.loads(json_match.group())
                if isinstance(ideas, list):
                    return ideas[:expected]
            # Fallback: try full text as JSON
            ideas = json.loads(text)
            if isinstance(ideas, list):
                return ideas[:expected]
        except Exception:
            pass

        # If parsing fails, create a single idea from the raw text
        return [
            {
                "title": "综合分析视角",
                "high_level_idea": text[:500],
                "approach": "",
                "novelty": "",
                "cross_domain": "",
                "experiments": [],
            }
        ]
