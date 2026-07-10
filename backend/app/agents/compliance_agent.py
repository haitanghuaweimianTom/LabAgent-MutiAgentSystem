"""合规审查Agent — 金融报告合规检查

扫描金融分析报告，检测投顾话术，自动添加免责声明。
定位为"客观数据处理工具"，而非"投资顾问"。
"""

import logging
import re
from typing import Any, Dict, List

from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)

# 违规投顾话术模式
COMPLIANCE_PATTERNS = [
    # 明确的投资建议
    (r"建议[买卖][入出]?[该这只]?", "明确投资建议"),
    (r"推荐[买卖][入出]?", "明确投资建议"),
    (r"目标价[为是]\s*\d+", "目标价预测"),
    (r"买入价[为是]\s*\d+", "买入价建议"),
    (r"止损[价位在]\s*\d+", "止损建议"),
    (r"预计[涨上]涨?\s*\d+%", "收益预测"),
    (r"预期[回报收益]\s*\d+%", "收益预测"),
    (r"保证[正稳]?[定收益]", "保证收益"),
    (r"稳[定赚]赚?", "保证收益"),
    (r"必[将涨]", "确定性预测"),
    (r"肯定[会将]", "确定性预测"),
    # 收益承诺
    (r"年化[收益回报率]*\s*\d+%", "收益承诺"),
    (r"[无零]风险", "风险承诺"),
    (r"保[本底]", "保本承诺"),
    # 操纵性语言
    (r"立即[买卖]", "操纵性语言"),
    (r"赶紧[买卖]", "操纵性语言"),
    (r"最后[机入]", "操纵性语言"),
    (r"错过[就没]", "操纵性语言"),
]

# 免责声明模板
DISCLAIMER_ZH = """
## 免责声明

本报告由AI辅助生成，仅供学术研究和学习参考，不构成任何投资建议。

1. 本报告中的分析基于历史数据和量化模型，过去的表现不代表未来收益。
2. 投资有风险，入市需谨慎。任何投资决策应基于个人风险承受能力和专业财务顾问的建议。
3. 本报告中的数据来源已在文中标注，数据的准确性和完整性依赖于原始数据源。
4. 本系统定位为"客观数据处理工具"，不从事证券投资咨询业务。
5. 报告中可能存在的模型局限性和假设条件已在相应章节说明。

生成时间：{timestamp}
"""

DISCLAIMER_EN = """
## Disclaimer

This report is AI-assisted and for academic research/educational purposes only. It does not constitute investment advice.

1. Analysis is based on historical data and quantitative models. Past performance does not guarantee future results.
2. Investing involves risk. Consult a qualified financial advisor before making investment decisions.
3. Data sources are cited in the report. Accuracy depends on original data providers.
4. This system is an "objective data processing tool", not an investment advisor.
5. Model limitations and assumptions are described in relevant sections.

Generated: {timestamp}
"""


@AgentFactory.register("compliance_agent")
class ComplianceAgent(BaseAgent):
    name = "compliance_agent"
    label = "合规审查专家"
    description = "金融报告合规检查，检测投顾话术，添加免责声明"
    default_model = ""

    def get_system_prompt(self) -> str:
        return "你是一个金融合规审查专家，负责检测报告中的违规投顾话术。"

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """审查金融报告合规性

        Args:
            task_input: {
                "report_text": str,  # 报告文本内容
                "language": str,     # "zh" | "en"
            }
            context: 上下文信息
        """
        report_text = task_input.get("report_text", "")
        language = task_input.get("language", "zh")

        if not report_text:
            return {
                "passed": True,
                "violations": [],
                "disclaimer_added": False,
                "cleaned_text": report_text,
            }

        # 检测违规内容
        violations = self._detect_violations(report_text)

        # 生成免责声明
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        disclaimer = (DISCLAIMER_ZH if language == "zh" else DISCLAIMER_EN).format(
            timestamp=timestamp
        )

        # 清理违规内容
        cleaned_text = self._clean_violations(report_text, violations)

        # 追加免责声明
        cleaned_text = cleaned_text + "\n\n" + disclaimer

        return {
            "passed": len(violations) == 0,
            "violations": [{"pattern": v[0], "category": v[1], "text": v[2]} for v in violations],
            "disclaimer_added": True,
            "cleaned_text": cleaned_text,
        }

    def _detect_violations(self, text: str) -> List[tuple]:
        """检测违规内容，返回 [(匹配文本, 类别, 上下文)]"""
        violations = []
        for pattern, category in COMPLIANCE_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                # 获取匹配上下文（前后各50字符）
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context_text = text[start:end].replace("\n", " ")
                violations.append((match.group(), category, context_text))
        return violations

    def _clean_violations(self, text: str, violations: List[tuple]) -> str:
        """清理违规内容（替换为[已删除]标记）"""
        cleaned = text
        for match_text, category, _ in reversed(violations):
            cleaned = cleaned.replace(match_text, f"[已删除: {category}]")
        return cleaned
