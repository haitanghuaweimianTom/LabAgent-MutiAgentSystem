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
        force_structural: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Generate diverse research ideas for the given problem.

        Args:
            force_structural: 若为 True（CCF-A 模板），强制要求 >=1 个想法采用
                网络结构化方法（DebtRank/SDECM/扩散谱/TGNN/ABM/系统动力学），
                >=1 个采用因果识别/反馈环方法，避免 5 个全是通用视角。

        Returns list of dicts: {title, high_level_idea, approach, novelty, cross_domain, experiments}
        """
        system_prompt = (
            "你是一位跨学科研究专家，擅长从多个角度分析数学建模问题，"
            "并能从其他领域借鉴方法。请生成多样化的研究方向建议。"
        )

        structural_clause = ""
        if force_structural:
            structural_clause = """
【CCF-A 强制结构化要求 — 必须满足】
- 至少 1 个想法必须采用网络结构化方法（DebtRank / SDECM / 扩散谱 PDE / TGNN / ABM 传染 / 系统动力学之一），并说明拓扑/损失传染机制
- 至少 1 个想法必须涉及因果识别或内生反馈环（如 SVAR、IV、面板 FE、信贷供给↔房价反馈）
- 禁止所有想法都是"线性回归/弹性标定/蒙特卡洛情景"这类纯聚合方法
- 在每个想法的 cross_domain 字段标注其采用的结构化方法类别
"""

        prompt = f"""请对以下数学建模问题生成 {num_ideas} 个不同的研究方向和创意视角。

【赛题内容】
{problem_text[:3000]}

{f'【数据文件描述】\n{data_descriptions[:1000]}' if data_descriptions else ''}
{structural_clause}
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
        ideas = self._parse_ideas(result, num_ideas)
        if force_structural:
            ideas = self._ensure_structural_ideas(ideas)
        return ideas

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

    def _ensure_structural_ideas(self, ideas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """CCF-A 兜底：若 LLM 未产出网络结构化想法，注入一个保底想法。

        审稿意见明确要求"加网络传染层"，故即便 LLM 漏掉也必须有保底。
        """
        structural_keywords = [
            "debtrank", "sdecm", "扩散谱", "diffusion-spectral", "tgnn",
            "abm", "agent-based", "多智能体", "system dynamics", "系统动力学",
            "网络", "network", "拓扑", "topology", "传染", "contagion",
        ]
        causal_keywords = [
            "因果", "causal", "svar", "iv", "工具变量", "反馈", "feedback",
            "内生", "endogen", "面板", "panel", "固定效应",
        ]
        has_structural = any(
            any(kw in (str(i.get("approach", "")) + str(i.get("cross_domain", "")) + str(i.get("title", ""))).lower()
                for kw in structural_keywords)
            for i in ideas
        )
        has_causal = any(
            any(kw in (str(i.get("approach", "")) + str(i.get("cross_domain", ""))).lower()
                for kw in causal_keywords)
            for i in ideas
        )
        if has_structural and has_causal:
            return ideas
        # 注入保底想法
        fallback = {
            "title": "网络结构与内生反馈的传染建模（CCF-A 保底视角）",
            "high_level_idea": (
                "将四环传导链建模为银行-城投-政府的网络拓扑，用 DebtRank/SDECM 量化损失传染，"
                "并引入信贷供给↔房价的内生反馈环，避免单向线性标定。"
            ),
            "approach": (
                "1) 构建银行-城投敞口邻接矩阵，运行 DebtRank 迭代计算系统级损失放大；"
                "2) 用 SDECM 分离资产负债表驱动与拓扑驱动风险；"
                "3) 用扩散谱 PDE 量化代数连通性对传染衰减的影响；"
                "4) SVAR 识别信贷供给冲击对房价的因果效应。"
            ),
            "novelty": "网络拓扑与内生反馈的结合可量化尾部风险，弥补聚合弹性模型的盲区。",
            "cross_domain": "借鉴网络科学(DebtRank)、统计物理(扩散谱)、计量经济学(SVAR)。",
            "experiments": [
                "构建敞口邻接矩阵并计算 DebtRank 系统损失",
                "对比聚合块 vs 网络块的损失放大倍数",
                "SVAR 识别信贷供给→房价的因果脉冲响应",
                "消融：移除反馈环/网络层观察尾部风险变化",
            ],
        }
        return ideas + [fallback]

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
