"""合规审查Agent — 金融报告合规检查

扫描金融分析报告，检测投顾话术并清理违规内容（不再追加免责声明）。
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

@AgentFactory.register("compliance_agent")
class ComplianceAgent(BaseAgent):
    name = "compliance_agent"
    label = "合规审查专家"
    description = "金融报告合规检查，检测投顾话术并清理违规内容"
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

        # 清理违规内容（违规话术替换为 [已删除] 标记）
        cleaned_text = self._clean_violations(report_text, violations)

        # 注：不再追加免责声明。用户硬约束：产出 PDF 不得出现任何 "AI 生成" 字眼；
        # 此前免责声明含 "本报告由AI辅助生成" 且为 Markdown 追加进 LaTeX 源会渲染错，
        # 故整段移除。disclaimer_added 保留为 False 以维持返回结构兼容。

        return {
            "passed": len(violations) == 0,
            "violations": [{"pattern": v[0], "category": v[1], "text": v[2]} for v in violations],
            "disclaimer_added": False,
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
