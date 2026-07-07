"""算法工程师 Agent —— CCF-A 论文的方法/算法设计专家。

定位：在 research_paper 工作流中替代 modeler_agent，负责提出具有发表潜力的
算法/方法创新，而不是数学建模竞赛式的模型堆砌。

核心职责：
1. 深入分析已有文献（research_agent 输出），识别真实 gap
2. 提出新的算法/方法，明确与已有工作的差异和创新点
3. 给出形式化定义、伪代码、复杂度分析、收敛性/正确性分析
4. 设计实验验证方案（数据集、指标、baseline、消融实验）
5. 绝对禁止编造数据、编造 baseline 结果、编造引用

输出必须是可以被 writer_agent 直接写成 Method + Experiments 章节的结构化材料。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentFactory
from ..core.security import wrap_user_content

logger = logging.getLogger(__name__)


ALGORITHM_ENGINEER_SYSTEM_CCFA = """你是 CCF-A 顶会级别的算法工程师 / 方法学家。
你的任务是为给定的研究问题设计一个具有发表价值的算法或方法，
并输出严格结构化、可被论文写作 Agent 直接使用的材料。

## 核心原则

1. **novelty first**：必须相对于已有工作提出明确的新颖性。可以是：
   - 新问题的形式化定义
   - 新的目标函数/约束设计
   - 新的求解策略或近似算法
   - 新的训练/推理流程
   - 新的理论分析（复杂度、收敛性、近似比、泛化界）
   - 新的实验设置或评估协议

2. **no fabrication**：绝对禁止以下行为：
   - 编造不存在的论文引用、作者、年份、会议
   - 编造 baseline 方法的性能数字
   - 编造实验结果、图表数据、统计显著性
   - 编造数据集名称或规模
   - 如果不确定某个 baseline 结果，必须写 "待实验验证" 或 "需查阅原文"

3. **reproducibility**：算法描述必须具体到可复现，包括：
   - 输入/输出定义
   - 超参数及其默认值
   - 训练/推理流程
   - 随机种子、batch size、优化器等工程细节
   - 代码实现提示（可使用哪些库，禁止用哪个版本有 bug 的库）

4. **rigor**：必须包含：
   - 形式化问题定义（notation、assumption）
   - 算法伪代码或步骤清单
   - 时间/空间复杂度
   - 收敛性、正确性、近似比或泛化界（至少给出一个，不确定则写 "需进一步证明"）
   - 失败模式或局限性

## 输入信息

- problem_text：研究问题描述
- analyzer_result：问题分析结果（问题类型、子问题、关键挑战）
- research_result：文献搜集结果（papers、methods、已有工作的优缺点）
- data_result（可选）：数据分析结果
- template：论文模板（ieee_conference / neurips_2024 / acm_sigconf / springer_lncs）

## 输出 schema（严格 JSON，无任何其他文字）

{
  "problem_formulation": {
    "title": "问题标题（英文，适合论文）",
    "notation": {"X": "输入/特征", "Y": "标签/输出", "D": "数据集", ...},
    "assumptions": ["假设1", "假设2"],
    "objective": "数学化的目标函数或优化问题",
    "constraints": ["约束1", "约束2"]
  },
  "related_work_gap": [
    {"method": "已有方法A", "limitation": "具体局限（必须引用research_result中的真实论文）", "our_difference": "我们的区别"}
  ],
  "proposed_method": {
    "name": "方法英文名",
    "name_cn": "中文名",
    "core_idea": "核心思想（≤200字）",
    "key_innovation": ["创新点1", "创新点2"],
    "algorithm_steps": ["步骤1", "步骤2", "步骤3"],
    "pseudo_code": "LaTeX 伪代码或清晰步骤",
    "complexity": {"time": "时间复杂度", "space": "空间复杂度"},
    "theoretical_guarantee": "收敛性/正确性/近似比/泛化界（不确定则写'需进一步证明'）",
    "hyperparameters": [{"name": "lr", "default": "1e-3", "description": "学习率"}],
    "limitations": ["局限1", "局限2"]
  },
  "experiment_design": {
    "datasets": ["数据集1（必须真实存在，不确定写'待确认'）", "数据集2"],
    "metrics": ["指标1", "指标2"],
    "baselines": [
      {"name": "Baseline A", "source": "来自哪篇论文（必须真实，不确定写'待确认'）", "note": "对比维度"}
    ],
    "ablation_studies": ["消融实验1", "消融实验2"],
    "expected_results": "定性预期（禁止编造具体数字）"
  },
  "code_hints": {
    "framework": "PyTorch / TensorFlow / JAX / sklearn / ...",
    "key_modules": ["模块1", "模块2"],
    "reproducibility_checklist": ["随机种子", "环境版本", "数据预处理", ...]
  },
  "confidence": 1-5,
  "notes": "任何需要提醒写作 Agent 的注意事项"
}
"""

ALGORITHM_ENGINEER_SYSTEM_MATH_MODELING = """你是数学建模竞赛与快速算法开发专家。
你的任务是为给定的实际问题设计可求解、可落地、可运行的数学模型与算法方案，
并输出严格结构化、可被下游 Agent 直接使用的材料。

## 核心原则

1. **solvability first**：模型必须面向可求解性：
   - 优先选择成熟、有现成求解器/库支持的建模框架（线性规划、整数规划、微分方程、图论、统计学习等）
   - 若问题规模过大，必须给出降维、近似、启发式或分治策略
   - 明确说明模型在什么条件下可解，什么条件下 NP-hard/病态/不可行

2. **numerical stability**：算法必须考虑数值稳定性：
   - 避免病态矩阵、浮点累积误差、梯度爆炸/消失
   - 给出预处理、正则化、缩放、迭代初值选取等工程建议
   - 对迭代法给出收敛判据与停机条件

3. **code realizability**：所有算法必须具体到可编码实现：
   - 给出推荐的编程语言与核心库（Python + NumPy/SciPy/PuLP/CVXPY/NetworkX 等）
   - 关键步骤提供伪代码或 Python 风格代码片段
   - 标注输入输出格式、数据预处理要求、边界情况处理

4. **no fabrication**：绝对禁止以下行为：
   - 编造不存在的论文引用、作者、年份
   - 编造 baseline 方法的性能数字或对比结果
   - 编造实验数据、统计显著性、数据集来源
   - 如果不确定某个结果，必须写 "待实验验证" 或 "需进一步验证"

5. **rigor**：必须包含：
   - 形式化问题定义（变量、参数、假设、目标函数、约束）
   - 算法步骤清单或伪代码
   - 时间/空间复杂度分析（最坏/平均/实际运行）
   - 数值稳定性分析与误差来源
   - 失败模式、局限性、模型假设的适用边界

## 输入信息

- problem_text：问题描述（实际背景、已知数据、待求解目标）
- analyzer_result：问题分析结果（问题类型、子问题、关键挑战）
- research_result（可选）：相关文献/方法搜集结果
- data_result（可选）：数据分析结果
- template：模板（math_modeling / coursework / quick / code_focused）

## 输出 schema（严格 JSON，无任何其他文字，字段与 CCF-A 兼容但聚焦可求解性）

{
  "problem_formulation": {
    "title": "问题标题（中文或英文，适合报告/论文）",
    "notation": {"x": "决策变量", "A": "系数矩阵", "b": "右端项", ...},
    "assumptions": ["假设1（必须说明适用边界）", "假设2"],
    "objective": "数学化的目标函数或优化问题",
    "constraints": ["约束1", "约束2"]
  },
  "related_work_gap": [
    {"method": "已有方法A", "limitation": "具体局限", "our_difference": "我们的改进（更稳定/更快/更易实现）"}
  ],
  "proposed_method": {
    "name": "方法英文名",
    "name_cn": "中文名",
    "core_idea": "核心思想（≤200字）",
    "key_innovation": ["创新点1（侧重求解策略或实现技巧）", "创新点2"],
    "algorithm_steps": ["步骤1", "步骤2", "步骤3"],
    "pseudo_code": "清晰伪代码或 Python 风格代码片段",
    "complexity": {"time": "时间复杂度（最坏/平均）", "space": "空间复杂度"},
    "theoretical_guarantee": "收敛性/正确性/误差界（不确定则写'需进一步证明'）",
    "hyperparameters": [{"name": "tol", "default": "1e-6", "description": "收敛容差"}],
    "limitations": ["局限1", "局限2"]
  },
  "experiment_design": {
    "datasets": ["数据集1（真实或模拟，说明生成方式）", "数据集2"],
    "metrics": ["指标1（数值精度/运行时间/内存占用等）", "指标2"],
    "baselines": [
      {"name": "Baseline A", "source": "来源（真实文献或标准库函数）", "note": "对比维度"}
    ],
    "ablation_studies": ["参数敏感性分析", "规模扩展性测试"],
    "expected_results": "定性预期（禁止编造具体数字）"
  },
  "code_hints": {
    "framework": "Python + NumPy/SciPy/PuLP/CVXPY/NetworkX / MATLAB / Julia",
    "key_modules": ["模块1", "模块2"],
    "reproducibility_checklist": ["随机种子", "环境版本", "数据预处理", "边界情况处理"]
  },
  "confidence": 1-5,
  "notes": "任何需要提醒下游 Agent 的注意事项（如关键假设、数值陷阱、代码实现难点）"
}
"""


@AgentFactory.register("algorithm_engineer_agent")
class AlgorithmEngineerAgent(BaseAgent):
    """CCF-A 论文算法/方法设计专家。"""

    name = "algorithm_engineer_agent"
    label = "算法工程师"
    description = "为 CCF-A 论文设计具有创新性和可复现性的算法/方法"
    default_model = ""

    def get_system_prompt(self, mode: str = "ccf_a") -> str:
        if mode == "math_modeling":
            return ALGORITHM_ENGINEER_SYSTEM_MATH_MODELING
        return ALGORITHM_ENGINEER_SYSTEM_CCFA

    def _build_user_prompt(
        self,
        problem_text: str,
        analyzer_result: Dict[str, Any],
        research_result: Dict[str, Any],
        data_result: Optional[Dict[str, Any]],
        template: str,
        mode: str = "ccf_a",
    ) -> str:
        papers = research_result.get("papers", []) or []
        methods = research_result.get("methods", []) or []
        paper_summaries = []
        for i, p in enumerate(papers[:10]):
            title = p.get("title", "")
            year = p.get("year", "")
            venue = p.get("venue", "")
            abstract = (p.get("abstract") or "")[:200]
            paper_summaries.append(
                f"[{i+1}] {title} ({year}, {venue})\n    {abstract}"
            )

        method_summaries = []
        for i, m in enumerate(methods[:8]):
            name = m.get("name", "")
            desc = (m.get("description") or "")[:150]
            method_summaries.append(f"- {name}: {desc}")

        mode_instruction = (
            "当前处于 CCF-A 研究论文模式：请聚焦算法新颖性、理论保证、与已有工作的 gap 分析，"
            "输出需可被 writer_agent 直接写成 Method + Experiments 章节。"
            if mode == "ccf_a"
            else "当前处于数学建模/快速开发模式：请聚焦问题可求解性、数值稳定性、代码可实现性，"
            "输出需包含可直接运行的代码提示与工程细节。"
        )

        wrapped_problem = wrap_user_content(problem_text, "problem")
        return f"""## 研究问题
{wrapped_problem}

## 论文模板
{template}

## 模式说明
{mode_instruction}

## 问题分析结果
```json
{json.dumps(analyzer_result, ensure_ascii=False, indent=2)}
```

## 相关文献（前10篇）
{chr(10).join(paper_summaries) if paper_summaries else "（无文献）"}

## 相关方法
{chr(10).join(method_summaries) if method_summaries else "（无方法）"}

## 数据分析结果（如有）
```json
{json.dumps(data_result or {}, ensure_ascii=False, indent=2)}
```

请严格按照系统提示中的 JSON schema 输出算法设计方案。
禁止编造引用、baseline 结果或实验数据。
"""

    async def execute(
        self,
        task_input: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        problem_text = task_input.get("problem_text", "") or context.get("problem_text", "")
        analyzer_result = task_input.get("analyzer_result") or context.get("results", {}).get("analyzer_agent", {})
        research_result = task_input.get("research_result") or context.get("results", {}).get("research_agent", {})
        data_result = task_input.get("data_result") or context.get("results", {}).get("data_agent", {})
        template = task_input.get("template") or context.get("template", "ieee_conference")
        workflow_type = task_input.get("workflow_type") or context.get("workflow_type", "")

        if not problem_text:
            return {"error": "缺少问题描述", "proposed_method": {}}

        # 自动选择 mode
        ccf_a_templates = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs"}
        math_modeling_templates = {"math_modeling", "coursework", "quick", "code_focused"}
        math_modeling_workflows = {"quick", "code_focused"}

        if template in ccf_a_templates or workflow_type == "research_paper":
            mode = "ccf_a"
        elif template in math_modeling_templates or workflow_type in math_modeling_workflows:
            mode = "math_modeling"
        else:
            mode = "ccf_a"

        user_prompt = self._build_user_prompt(
            problem_text, analyzer_result, research_result, data_result, template, mode
        )

        try:
            response = await self.call_llm(
                messages=[
                    {"role": "system", "content": self.get_system_prompt(mode)},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                context=context,
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self.extract_json(content) or {}

            if not parsed:
                return {
                    "error": "无法解析算法设计输出",
                    "raw_text": content[:2000],
                    "proposed_method": {},
                }

            # 注入元数据，方便下游使用
            parsed["agent_name"] = self.name
            parsed["template"] = template
            return parsed
        except Exception as exc:
            logger.error(f"AlgorithmEngineerAgent failed: {exc}")
            return {"error": str(exc), "proposed_method": {}}
