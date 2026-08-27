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
        # CCF-A 顶会专用的"严谨性"批判维度。
        # 该维度直接对应 ICML/NeurIPS/IEEE/ACM 评审常见拒稿点（见审稿意见）：
        # 线性标定无因果识别、无样本外回测、无基线对比、无消融/敏感性、
        # 忽视异质性与网络传染、定义未形式化、代码不可复现。
        # 由 PaperGenerator 在 CCF-A 模板的 method/experiments/appendix 等章节
        # 生成后强制触发，并与模板的 rigor_checklist 联合打分。
        "ccf_a_rigor": [
            ("因果识别", "是否提供因果识别或显式区分'已识别'与'假设'部分，处理内生性/反向因果；而非仅线性标定弹性"),
            ("样本外验证", "是否包含样本外回测/验证并报告 RMSE/MAE/CRPS；场景引擎若无预测验证应大幅扣分"),
            ("基线对比", "是否对比至少 5 个基线，含系统性风险/网络基线（DebtRank/SDECM、扩散谱、ABM）；而非自说自话"),
            ("消融与敏感性", "是否做消融实验(>=3 组件)与敏感性分析(tornado/结果对先验弹性)；而非仅报告点路径"),
            ("异质性建模", "是否建模异质性(层级/面板)并报告跨单元离散度；而非仅全国/全局聚合"),
            ("反馈环", "是否编码内生反馈环(如信贷供给->需求->价格)并验证方向与量级(SVAR/结构块)"),
            ("网络传染层", "系统性风险为内核时是否加网络损失传染层(DebtRank/SDECM/扩散谱 PDE/TGNN)并与聚合块对比"),
            ("定义形式化", "是否形式化所有构造量(如'土地净收入'、政策乘数)并给出原始输入到使用值的对账表"),
            ("复现性", "是否公开完整代码、参数先验/协方差、分布、相关性、随机种子"),
            ("局限陈述", "是否诚实陈述未被建模的渠道(recognition 实践、重组、表外等)与 threats to validity"),
        ],
    }

    def __init__(self, call_llm: Callable[[str, Optional[str]], str]):
        """
        Args:
            call_llm: LLM调用函数，签名 (prompt, system_prompt) -> str
        """
        self.call_llm = call_llm

    def _extract_json(self, text: str) -> dict:
        """从LLM响应中提取JSON对象。

        处理：markdown代码块、前后多余文本、字符串内的花括号、字符串内的裸引号。
        """
        # 1. 去除 markdown 代码块
        text = re.sub(r'```(?:json)?\s*\n', '', text)
        text = text.strip()

        # 2. 找到第一个 { 和最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON found in response")

        raw = text[start:end+1]

        # 3. 先尝试直接解析
        normalized = raw.replace("'", '"')
        normalized = re.sub(r',\s*([}\]])', r'\1', normalized)
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            pass

        # 4. 修复字符串内的裸双引号后再试
        fixed = self._fix_unescaped_quotes(normalized)
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            raise ValueError(f"无法解析有效的 JSON 对象: {e}")

    def _fix_unescaped_quotes(self, raw: str) -> str:
        """修复JSON字符串值内的裸双引号。

        策略：
        - key 的引号后面跟 `:` → 正常闭合
        - value 的引号后面跟 `,` `}` `]` → 正常闭合
        - value 内的裸 `"` 后面跟的不是这些字符 → 转义
        """
        chars = list(raw)
        n = len(chars)
        i = 0
        result = []

        while i < n:
            c = chars[i]
            if c != '"':
                result.append(c)
                i += 1
                continue

            # 遇到 "：收集字符串内容
            result.append('"')
            i += 1
            content = []

            while i < n:
                c = chars[i]
                if c == '\\' and i + 1 < n:
                    content.append(c)
                    content.append(chars[i+1])
                    i += 2
                    continue
                if c == '"':
                    # 看后面的非空白字符，判断是否为字符串结束
                    j = i + 1
                    while j < n and chars[j] in (' ', '\t', '\n', '\r'):
                        j += 1
                    next_ch = chars[j] if j < n else ''

                    # key 引号后跟 : 或 value 引号后跟 ,}] → 正常闭合
                    if next_ch in (':', ',', '}', ']', ''):
                        result.append(''.join(content))
                        result.append('"')
                        i += 1
                        break
                    else:
                        # 字符串内的裸引号 → 转义
                        content.append('\\"')
                        i += 1
                else:
                    content.append(c)
                    i += 1

        return ''.join(result)

    def critique(
        self,
        content: str,
        content_type: str,
        context: Optional[str] = None,
        checklist: Optional[List[str]] = None,
    ) -> CritiqueResult:
        """
        对内容进行多维度批判评估

        Args:
            content: 待评估的内容
            content_type: 内容类型 (analysis/modeling/algorithm/paper_chapter/ccf_a_rigor)
            context: 额外上下文（如题目描述）
            checklist: 可选的硬性检查清单（如 CCF-A 模板的 rigor_checklist）。
                传入时，评审需逐条核对是否满足，未满足条目应给出低分与具体修改建议。
                对 ccf_a_rigor 维度尤其重要——它把模板要求转化为可拒稿的硬约束。

        Returns:
            CritiqueResult: 批判结果
        """
        dimensions = self.DIMENSIONS.get(content_type, self.DIMENSIONS["paper_chapter"])

        dim_text = "\n".join([f"{i+1}. {name}：{desc}" for i, (name, desc) in enumerate(dimensions)])

        checklist_block = ""
        if checklist:
            checklist_items = "\n".join([f"  C{i+1}. {item}" for i, item in enumerate(checklist)])
            checklist_block = f"""
【硬性检查清单 — 逐条核对，未满足必须扣分并给出修改建议】
{checklist_items}

评分约束：若任一硬性条目未满足，对应维度不得超过 6 分；整体 overall_score 不得超过 7 分。
"""

        prompt = f"""请对以下内容进行严格的批判性评估。

{context if context else ''}
{checklist_block}
【待评估内容】
{content[:4000]}

【评估维度】
{dim_text}

要求：
1. 对每个维度给出 1-10 分的评分（10分为完美）
2. 给出具体的评论，指出具体的不足之处
3. 给出 2-3 条可操作的改进建议

输出严格的JSON格式，不要任何markdown代码块或其他文字：
{{"overall_score": 7.5, "critiques": [{{"dimension": "思考深度", "score": 7, "comment": "...", "suggestions": ["...", "..."]}}]}}"""

        try:
            if content_type == "ccf_a_rigor":
                sys_prompt = (
                    "你是一位 CCF-A 顶会（ICML/NeurIPS/IEEE/ACM）资深领域主席。"
                    "你以拒稿常见原因（线性标定无因果识别、无样本外回测、无基线对比、"
                    "无消融/敏感性、忽视异质性与网络传染、定义未形式化、代码不可复现）"
                    "为硬性审查标准。你必须只输出JSON，不要任何其他文字。"
                )
            else:
                sys_prompt = "你是一位严格的学术评审专家。你必须只输出JSON，不要任何其他文字。"
            response = self.call_llm(prompt, sys_prompt)
            data = self._extract_json(response)

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

        prompt = f"""请基于以下要求，重新撰写本论文章节的高质量内容。

{context if context else ''}

【要求】
{suggestions_text}

【原始主题】
{content[:2000]}

重要约束：
1. 直接输出改进后的完整内容，不要提及"原版本"或"之前的问题"
2. 不要解释你做了什么改进，只输出最终内容
3. 内容必须比原始版本更加充实、深入、严谨
4. 确保所有数学公式使用 LaTeX 格式，公式编号连续
5. 严禁输出题目原文、摘要或其他章节的标题
6. 只输出本章的正文内容，不要输出章节标题"""

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
        checklist: Optional[List[str]] = None,
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
            checklist: 硬性检查清单（CCF-A rigor_checklist），逐条核对

        Returns:
            str: 最终改进后的内容
        """
        current = content

        for i in range(max_iterations):
            print(f"    [Critique] 第 {i+1}/{max_iterations} 轮评估...")
            critique = self.critique(current, content_type, context, checklist=checklist)
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
