"""金融分析师 Agent —— 金融分析报告的方法/模型设计专家。

定位：在 financial_analysis 模板中替代通用 modeler_agent，
负责建立金融数学、金融工程领域的模型，而不是数学建模竞赛模型。

核心职责：
1. 分析金融问题本质（定价、风险、组合优化、衍生品、时间序列、行为金融等）
2. 选择合适的金融数学/计量经济学/金融工程工具
3. 建立可解释的模型，明确假设、变量、数据来源
4. 设计风险分析、敏感性分析、回测方案
5. 绝对禁止编造股价、收益率、财务数据、监管政策
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentFactory
from ..core.security import wrap_user_content

logger = logging.getLogger(__name__)


FINANCIAL_ANALYST_SYSTEM = """你是金融工程 / 金融数学领域的资深分析师。
你的任务是为给定的金融分析问题建立严谨的量化模型，
并输出结构化、可被论文写作 Agent 直接使用的材料。

## 核心原则

1. **domain correctness**：必须使用金融数学/金融工程/计量经济学的语言和工具，例如：
   - 资产定价：CAPM、APT、风险中性定价、折现现金流
   - 风险管理：VaR、ES/CVaR、压力测试、信用评级迁移、GARCH 族波动率
   - 投资组合：马科维茨均值-方差、Black-Litterman、因子模型、组合优化
   - 衍生品：BS 模型、二叉树、蒙特卡洛模拟、希腊字母
   - 时间序列：ARIMA、GARCH、VAR、协整、事件研究
   - 行为金融/市场微观结构：仅在合适时使用

2. **no fabrication**：绝对禁止以下行为：
   - 编造股价、收益率、财务指标、宏观经济数据
   - 编造不存在的监管政策、市场事件
   - 编造投资组合回测收益
   - 编造不存在的公司、基金、指数
   - 如果示例需要数据，必须说明"需使用真实历史数据"或"使用公开数据集如 Yahoo Finance / Wind / 国泰安"

3. **data-driven**：模型必须说明：
   - 需要哪些数据（字段、频率、来源）
   - 数据预处理步骤（缺失值、异常值、标准化、对齐）
   - 如果无数据，应说明如何获取，而不是假设数据存在

4. **risk awareness**：必须包含：
   - 模型假设和适用边界
   - 模型风险（model risk）
   - 敏感性分析/压力测试设计
   - 局限性

5. **data provenance**：任何股价、收益率、财务指标必须说明数据来源（如 Yahoo Finance、Bloomberg、交易所官网、公司年报、Wind、CSMAR）。不得使用无来源的数字。

6. **no forward-looking assumptions**：禁止假设未来收益。所有回测必须基于真实历史数据，回测区间、基准指数、交易成本必须真实可查。

7. **explicit placeholder**：无实时数据时，使用显式占位符，例如"[需使用真实历史数据：请提供 2018-01-01 至 2023-12-31 的日收盘价]"，禁止用占位符替代后暗中补全虚假数字。

8. **no fictitious entities**：禁止编造不存在的公司、基金、指数、监管政策。若需示例，仅使用真实存在的实体（如沪深300、标普500、Apple Inc.、易方达蓝筹精选），并注明来源。

## 输入信息

- problem_text：金融问题描述
- analyzer_result：问题分析结果
- research_result：文献/行业报告搜集结果
- data_result（可选）：已上传数据分析结果

## 输出 schema（严格 JSON，无任何其他文字）

{
  "problem_formulation": {
    "domain": "资产定价/风险管理/投资组合/衍生品/时间序列/其他",
    "title": "英文标题（适合报告）",
    "research_question": "具体研究问题",
    "key_variables": {"r": "无风险利率", "S": "标的资产价格", "sigma": "波动率", ...},
    "assumptions": ["假设1", "假设2"]
  },
  "financial_model": {
    "name": "模型英文名",
    "name_cn": "中文名",
    "category": "金融数学/金融工程/计量经济学/机器学习金融应用",
    "core_idea": "核心思想（≤200字）",
    "model_specification": "数学公式或模型设定（LaTeX）",
    "parameters": [
      {"name": "mu", "meaning": "预期收益率", "estimation": "历史均值估计"}
    ],
    "algorithm_steps": ["步骤1", "步骤2", "步骤3"],
    "complexity": {"time": "时间复杂度", "space": "空间复杂度"}
  },
  "data_requirements": {
    "required_data": ["字段1（如：日收盘价）", "字段2（如：成交量）"],
    "frequency": "日度/周度/月度/季度/年度",
    "sources": ["Yahoo Finance", "Wind", "国泰安 CSMAR", "Bloomberg", "公开年报"],
    "preprocessing": ["缺失值处理", "异常值检测", "收益率计算", "对齐交易日"]
  },
  "risk_analysis": {
    "model_risks": ["风险1", "风险2"],
    "sensitivity_design": ["敏感性分析1", "压力测试1"],
    "limitations": ["局限1", "局限2"]
  },
  "backtest_design": {
    "strategy": "回测策略描述",
    "metrics": ["年化收益率", "夏普比率", "最大回撤", "Calmar 比率", "VaR(95%)"],
    "benchmark": "基准指数或组合（必须真实存在）",
    "period": "建议回测区间",
    "transaction_costs": "是否考虑交易成本、滑点"
  },
  "code_hints": {
    "python_libraries": ["numpy", "pandas", "statsmodels", "arch", "pyfolio / quantstats"],
    "key_functions": ["函数1", "函数2"]
  },
  "confidence": 1-5,
  "notes": "注意事项"
}
"""


@AgentFactory.register("financial_analyst_agent")
class FinancialAnalystAgent(BaseAgent):
    """金融分析报告的方法/模型设计专家。"""

    name = "financial_analyst_agent"
    label = "金融分析师"
    description = "建立金融数学、金融工程领域的量化模型"
    default_model = ""

    def get_system_prompt(self) -> str:
        return FINANCIAL_ANALYST_SYSTEM

    def _build_user_prompt(
        self,
        problem_text: str,
        analyzer_result: Dict[str, Any],
        research_result: Dict[str, Any],
        data_result: Optional[Dict[str, Any]],
    ) -> str:
        papers = research_result.get("papers", []) or []
        methods = research_result.get("methods", []) or []
        paper_summaries = []
        for i, p in enumerate(papers[:8]):
            title = p.get("title", "")
            year = p.get("year", "")
            venue = p.get("venue", "")
            abstract = (p.get("abstract") or "")[:180]
            paper_summaries.append(
                f"[{i+1}] {title} ({year}, {venue})\n    {abstract}"
            )

        method_summaries = []
        for i, m in enumerate(methods[:6]):
            name = m.get("name", "")
            desc = (m.get("description") or "")[:130]
            method_summaries.append(f"- {name}: {desc}")

        wrapped_problem = wrap_user_content(problem_text, "problem")
        return f"""## 金融分析问题
{wrapped_problem}

## 问题分析结果
```json
{json.dumps(analyzer_result, ensure_ascii=False, indent=2)}
```

## 相关文献/报告
{chr(10).join(paper_summaries) if paper_summaries else "（无文献）"}

## 相关方法
{chr(10).join(method_summaries) if method_summaries else "（无方法）"}

## 已上传数据分析结果（如有）
```json
{json.dumps(data_result or {}, ensure_ascii=False, indent=2)}
```

请严格按照系统提示中的 JSON schema 输出金融模型设计方案。
禁止编造股价、收益率、财务数据或监管政策。
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
        template = task_input.get("template") or context.get("template", "")

        if not problem_text:
            return {"error": "缺少问题描述", "financial_model": {}}

        user_prompt = self._build_user_prompt(
            problem_text, analyzer_result, research_result, data_result
        )

        try:
            response = await self.call_llm(
                messages=[
                    {"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                context=context,
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self.extract_json(content) or {}

            if not parsed:
                return {
                    "error": "无法解析金融模型输出",
                    "raw_text": content[:2000],
                    "financial_model": {},
                }

            parsed["agent_name"] = self.name
            if template and "template" not in parsed:
                parsed["template"] = template
            return parsed
        except Exception as exc:
            logger.error(f"FinancialAnalystAgent failed: {exc}")
            return {"error": str(exc), "financial_model": {}}
