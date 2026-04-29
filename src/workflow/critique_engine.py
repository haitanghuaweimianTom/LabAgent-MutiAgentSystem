"""
CritiqueEngine - Actor-Critic-Improvement 质量保障引擎
=======================================================

借鉴 LLM-MM-Agent 的多维批判框架：
- 从多个维度对生成内容进行批判性评估
- 基于批判结果生成改进版本
- 支持循环迭代直到质量达标

核心设计原则（来自 LLM-MM-Agent）：
- 批判时从多个维度拆解评估
- 改进时禁止提及先前版本的缺陷，直接给出新版本
"""

import json
import re
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass


@dataclass
class CritiqueScore:
    """批判评分"""
    dimension: str       # 维度名称
    score: int           # 1-10分
    comment: str         # 具体评论
    suggestions: List[str]  # 改进建议


@dataclass
class CritiqueResult:
    """批判结果"""
    overall_score: float      # 综合得分
    critiques: List[CritiqueScore]
    improved: bool = False    # 是否已改进


class CritiqueEngine:
    """
    Actor-Critic-Improvement 引擎

    使用方式：
        engine = CritiqueEngine(call_llm_func)
        result = engine.critique_and_improve(
            content=content,
            content_type="analysis",
            context=context,
            max_iterations=2
        )
    """

    # 各内容类型的批判维度定义
    DIMENSIONS = {
        "analysis": [
            ("思考深度", "是否深入挖掘问题本质，而非表面描述"),
            ("视角新颖性", "是否提出独特的分析角度或见解"),
            ("逻辑严谨性", "推理过程是否严密，无跳跃或漏洞"),
            ("上下文意识", "是否充分理解并利用题目提供的所有信息"),
            ("结构化程度", "分析是否有清晰的层次和结构"),
        ],
        "modeling": [
            ("准确性与严谨性", "公式是否正确，假设是否合理且明确"),
            ("创新与洞察", "模型是否有新意，是否超越了常规方法"),
            ("实际适用性", "模型是否针对实际问题设计，参数是否可获取"),
            ("完整性", "是否涵盖所有子问题，边界条件是否讨论"),
            ("可解性", "模型是否有明确的求解路径，复杂度是否合理"),
        ],
        "algorithm": [
            ("正确性", "算法步骤是否逻辑正确，能否得到正确结果"),
            ("效率", "时间/空间复杂度是否合理"),
            ("鲁棒性", "对异常输入和边界情况的处理"),
            ("可实现性", "算法是否能在合理时间内编程实现"),
        ],
        "paper_chapter": [
            ("内容充实度", "是否有足够的细节、推导和解释，而非空话套话"),
            ("逻辑连贯性", "段落之间、章节之间是否衔接自然"),
            ("数据准确性", "引用的数据是否与计算结果一致"),
            ("学术规范性", "公式编号、术语使用、引用格式是否规范"),
            ("深度分析", "是否超越表面描述，给出深入的分析和见解"),
        ],
    }

    def __init__(self, call_llm: Callable[[str, Optional[str]], str]):
        """
        Args:
            call_llm: LLM调用函数，签名 (prompt, system_prompt) -> str
        """
        self.call_llm = call_llm

    def critique(
        self,
        content: str,
        content_type: str,
        context: Optional[str] = None,
    ) -> CritiqueResult:
        """
        对内容进行多维度批判评估

        Args:
            content: 待评估的内容
            content_type: 内容类型 (analysis/modeling/algorithm/paper_chapter)
            context: 额外上下文（如题目描述）

        Returns:
            CritiqueResult: 批判结果
        """
        dimensions = self.DIMENSIONS.get(content_type, self.DIMENSIONS["paper_chapter"])

        dim_text = "\n".join([f"{i+1}. {name}：{desc}" for i, (name, desc) in enumerate(dimensions)])

        prompt = f"""请对以下内容进行严格的批判性评估。

{context if context else ''}

【待评估内容】
{content[:5000]}

【评估维度】
{dim_text}

要求：
1. 对每个维度给出 1-10 分的评分（10分为完美）
2. 给出具体的评论，指出具体的不足之处（引用原文）
3. 给出 2-3 条可操作的改进建议

输出严格的 JSON 格式：
{{"overall_score": 7.5, "critiques": [{{"dimension": "思考深度", "score": 7, "comment": "...", "suggestions": ["..."]}}]}}"""

        try:
            response = self.call_llm(prompt, "你是一位严格的学术评审专家。")
            # 提取 JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response)

            critiques = []
            for c in data.get("critiques", []):
                critiques.append(CritiqueScore(
                    dimension=c.get("dimension", ""),
                    score=c.get("score", 5),
                    comment=c.get("comment", ""),
                    suggestions=c.get("suggestions", []),
                ))

            overall = data.get("overall_score", 7.0)
            return CritiqueResult(overall_score=overall, critiques=critiques)

        except Exception as e:
            print(f"[Critique] 批判过程出错: {e}")
            # 返回默认中等评分
            return CritiqueResult(
                overall_score=7.0,
                critiques=[CritiqueScore(
                    dimension="综合评估",
                    score=7,
                    comment="自动评估（批判过程出错）",
                    suggestions=["请人工检查内容质量"]
                )]
            )

    def improve(
        self,
        content: str,
        critique_result: CritiqueResult,
        content_type: str,
        context: Optional[str] = None,
        min_chars: int = 0,
    ) -> str:
        """
        基于批判结果生成改进版本

        关键约束（来自 LLM-MM-Agent）：禁止提及先前版本的缺陷，直接给出新版本

        Args:
            content: 原始内容
            critique_result: 批判结果
            content_type: 内容类型
            context: 额外上下文
            min_chars: 最少字数要求

        Returns:
            str: 改进后的内容
        """
        # 提取关键改进建议
        suggestions = []
        for c in critique_result.critiques:
            if c.score < 8:
                suggestions.extend(c.suggestions)

        if not suggestions:
            return content

        suggestions_text = "\n".join([f"- {s}" for s in suggestions[:5]])

        prompt = f"""请基于以下要求，重新撰写一篇高质量的内容。

{context if context else ''}

【要求】
{suggestions_text}

【原始主题】
{content[:2000]}

重要约束：
1. 直接输出改进后的完整内容，不要提及"原版本"或"之前的问题"
2. 不要解释你做了什么改进，只输出最终内容
3. 内容必须比原始版本更加充实、深入、严谨
4. 确保所有数学公式使用 LaTeX 格式，公式编号连续"""

        if min_chars > 0:
            prompt += f"\n5. 内容至少 {min_chars} 个中文字符"

        try:
            improved = self.call_llm(prompt, "你是一位优秀的学术写作专家。")
            return improved
        except Exception as e:
            print(f"[Critique] 改进过程出错: {e}")
            return content

    def critique_and_improve(
        self,
        content: str,
        content_type: str,
        context: Optional[str] = None,
        max_iterations: int = 2,
        score_threshold: float = 8.0,
        min_chars: int = 0,
    ) -> str:
        """
        执行完整的 Critique-Improvement 循环

        Args:
            content: 初始内容
            content_type: 内容类型
            context: 额外上下文
            max_iterations: 最大迭代次数
            score_threshold: 评分阈值，超过则停止迭代
            min_chars: 最少字数要求

        Returns:
            str: 最终改进后的内容
        """
        current = content

        for i in range(max_iterations):
            print(f"    [Critique] 第 {i+1}/{max_iterations} 轮评估...")
            critique = self.critique(current, content_type, context)
            print(f"    [Critique] 综合评分: {critique.overall_score:.1f}/10")

            # 打印各维度评分
            for c in critique.critiques:
                print(f"      - {c.dimension}: {c.score}/10")

            if critique.overall_score >= score_threshold:
                print(f"    [Critique] 评分达标，停止迭代")
                break

            print(f"    [Critique] 评分未达标，生成改进版本...")
            current = self.improve(current, critique, content_type, context, min_chars)

        return current
