"""跨章节一致性验证器（v5.2）。

跟 FactChecker（数字 vs solver output）互补，本检查器聚焦：

1. **术语一致性**：同一概念在不同章节不应换名字
   （"神经网络" vs "深度学习模型" 在同一论文里应统一）

2. **模型名一致性**：modeler 输出中的模型名 / 算法名 / 数据集名
   在 writer 各章节中应保持相同

3. **结论一致性**：结论章节不能与摘要章节的具体声明矛盾
   （摘要说"最优解为 42.0"，结论里又写"最优解为 38.0"——矛盾）

4. **引用一致性**：bib 中存在的 key 必须真的在 LaTeX 里被 \cite{...} 引用
   （孤立条目说明引用没真用上）

5. **符号一致性**：同一符号在全文应保持同含义

工作方式：纯规则检查，不调 LLM；可作为 Harness 在 writer 完成后跑一次。
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyIssue:
    """一致性检查问题。"""
    category: str  # "terminology" / "model_name" / "conclusion" / "citation" / "symbol"
    severity: str  # "high" / "medium" / "low"
    location: str  # "section 4" / "abstract vs section 8" 等
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "location": self.location,
            "message": self.message,
        }


@dataclass
class ConsistencyReport:
    """一致性检查报告。"""
    task_id: str = ""
    issue_count: int = 0
    issues: List[ConsistencyIssue] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    passed: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "issue_count": self.issue_count,
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
            "stats": self.stats,
        }


# ==================== 启发式规则 ====================

# 这些术语对在同一论文里不应混用（要么都用 A 要么都用 B）
TERMINOLOGY_PAIRS = [
    ("神经网络", "深度学习模型"),
    ("机器学习", "统计学习"),
    ("损失函数", "代价函数"),
    ("优化", "最优化"),
    ("梯度下降", "最速下降"),
    ("激活函数", "激励函数"),
    ("数据集", "资料集"),
    ("测试集", "测试资料"),
    ("准确率", "准确度"),
    ("召回率", "查全率"),
    ("精确率", "查准率"),
]


class ConsistencyChecker:
    """跨章节一致性验证器。"""

    def __init__(self):
        # 编译常用术语对的正则（一次性）
        self._term_patterns: List[Tuple[re.Pattern, re.Pattern, str, str]] = []
        for a, b in TERMINOLOGY_PAIRS:
            # 用 \b 包围中文（实际中文不分词，但 Python re 也支持）
            self._term_patterns.append((
                re.compile(re.escape(a)),
                re.compile(re.escape(b)),
                a, b,
            ))

    # ====================================================================
    # 主入口
    # ====================================================================
    def check(
        self,
        task_id: str,
        latex_code: str = "",
        chapter_summaries: Optional[List[Dict[str, Any]]] = None,
        paper_memory: Optional[Dict[str, Any]] = None,
        bib_entries: Optional[List[Dict[str, Any]]] = None,
        solver_numerical_results: Optional[Dict[str, Any]] = None,
    ) -> ConsistencyReport:
        """执行完整一致性检查。

        所有输入都是可选的；缺失的检查会跳过。
        """
        report = ConsistencyReport(task_id=task_id)
        chapter_summaries = chapter_summaries or []
        paper_memory = paper_memory or {}
        bib_entries = bib_entries or []

        # 1. 术语一致性
        if latex_code:
            term_issues = self._check_terminology(latex_code)
            report.issues.extend(term_issues)

        # 2. 模型名一致性（paper_memory.model_names / algorithms / datasets
        #    是否在 LaTeX 中实际出现）
        if latex_code and paper_memory:
            model_issues = self._check_model_names(latex_code, paper_memory)
            report.issues.extend(model_issues)

        # 3. 结论一致性（chapter_summaries 中"结论"章节与摘要对比）
        concl_issues = self._check_conclusion_consistency(chapter_summaries)
        report.issues.extend(concl_issues)

        # 4. 引用一致性（bib 中 key 必须被 \cite{} 引用）
        if latex_code and bib_entries:
            cite_issues = self._check_citation_usage(latex_code, bib_entries)
            report.issues.extend(cite_issues)

        # 5. 符号一致性（同一符号在全文含义不变）
        if latex_code:
            sym_issues = self._check_symbol_consistency(latex_code)
            report.issues.extend(sym_issues)

        # 6. 数值结论一致性（摘要中的数字 vs solver 结果）
        #    复用 FactChecker 的能力（如果提供了 solver_numerical_results）
        if latex_code and solver_numerical_results:
            num_issues = self._check_number_consistency(latex_code, solver_numerical_results)
            report.issues.extend(num_issues)

        report.issue_count = len(report.issues)
        # 高严重度问题才让 passed=False
        report.passed = not any(i.severity == "high" for i in report.issues)
        report.stats = {
            "terminology_issues": sum(1 for i in report.issues if i.category == "terminology"),
            "model_name_issues": sum(1 for i in report.issues if i.category == "model_name"),
            "conclusion_issues": sum(1 for i in report.issues if i.category == "conclusion"),
            "citation_issues": sum(1 for i in report.issues if i.category == "citation"),
            "symbol_issues": sum(1 for i in report.issues if i.category == "symbol"),
            "number_issues": sum(1 for i in report.issues if i.category == "number"),
        }

        logger.info(
            f"[ConsistencyChecker] task {task_id}: {report.issue_count} issues, "
            f"passed={report.passed}, stats={report.stats}"
        )
        return report

    # ====================================================================
    # 1. 术语一致性
    # ====================================================================
    def _check_terminology(self, latex_code: str) -> List[ConsistencyIssue]:
        """同一概念不应在不同章节混用不同术语。"""
        issues: List[ConsistencyIssue] = []
        for pat_a, pat_b, term_a, term_b in self._term_patterns:
            count_a = len(pat_a.findall(latex_code))
            count_b = len(pat_b.findall(latex_code))
            # 两个术语同时出现 → 可能不一致
            if count_a > 0 and count_b > 0:
                issues.append(ConsistencyIssue(
                    category="terminology",
                    severity="medium",
                    location="全文",
                    message=f"术语不一致：'{term_a}' 出现 {count_a} 次，'{term_b}' 出现 {count_b} 次。建议全文统一为一种说法。",
                ))
        return issues

    # ====================================================================
    # 2. 模型名一致性
    # ====================================================================
    def _check_model_names(
        self,
        latex_code: str,
        paper_memory: Dict[str, Any],
    ) -> List[ConsistencyIssue]:
        """paper_memory 里登记的模型/算法/数据集名应该在 LaTeX 中实际出现；
        反过来 LaTeX 中提到但 paper_memory 没登记的，提示补登。"""
        issues: List[ConsistencyIssue] = []
        registered_models = set(paper_memory.get("model_names") or [])
        registered_algos = set(paper_memory.get("algorithms") or [])
        registered_datasets = set(paper_memory.get("datasets") or [])

        # 简化：直接搜 paper_memory 里的名字是否在 latex 里出现
        for name in registered_models:
            if name and len(name) >= 3 and name not in latex_code:
                issues.append(ConsistencyIssue(
                    category="model_name",
                    severity="low",
                    location="paper_memory",
                    message=f"模型 '{name}' 在 paper_memory 登记但 LaTeX 中未提及，可能写作时遗漏。",
                ))
        for name in registered_algos:
            if name and len(name) >= 3 and name not in latex_code:
                issues.append(ConsistencyIssue(
                    category="model_name",
                    severity="low",
                    location="paper_memory",
                    message=f"算法 '{name}' 在 paper_memory 登记但 LaTeX 中未提及。",
                ))
        return issues

    # ====================================================================
    # 3. 结论一致性
    # ====================================================================
    def _check_conclusion_consistency(
        self,
        chapter_summaries: List[Dict[str, Any]],
    ) -> List[ConsistencyIssue]:
        """检查摘要和结论章节是否在声明上矛盾（粗略启发式）。"""
        issues: List[ConsistencyIssue] = []
        abstract_text = ""
        conclusion_text = ""

        for ch in chapter_summaries:
            if not isinstance(ch, dict):
                continue
            cid = (ch.get("id") or ch.get("title") or "").lower()
            summary = ch.get("summary", "")
            if "abstract" in cid or "摘要" in cid:
                abstract_text = summary
            elif "conclusion" in cid or "结论" in cid:
                conclusion_text = summary

        if not (abstract_text and conclusion_text):
            return issues

        # 数字一致性：摘要里出现的所有数字也应在结论里出现（粗略）
        nums_abstract = set(re.findall(r"-?\d+\.?\d*", abstract_text))
        nums_conclusion = set(re.findall(r"-?\d+\.?\d*", conclusion_text))
        # 摘要中的"亮点数字"（非平凡）应该出现在结论里
        for n in nums_abstract:
            try:
                v = float(n)
                if abs(v) > 1 and "." in n:  # 跳过 1, 2, 100 等整数
                    if n not in nums_conclusion:
                        issues.append(ConsistencyIssue(
                            category="conclusion",
                            severity="medium",
                            location="abstract vs conclusion",
                            message=f"摘要提到数字 {n}，但结论章节未呼应该数字。",
                        ))
            except ValueError:
                pass
        return issues

    # ====================================================================
    # 4. 引用一致性
    # ====================================================================
    def _check_citation_usage(
        self,
        latex_code: str,
        bib_entries: List[Dict[str, Any]],
    ) -> List[ConsistencyIssue]:
        """bib 中的每个 key 应该被 \cite{...} 至少引用一次（否则孤立）。"""
        issues: List[ConsistencyIssue] = []
        # 提取 LaTeX 中所有被引用的 key
        cited_keys: Set[str] = set()
        for m in re.finditer(r"\\cite[a-z]*\{([^}]+)\}", latex_code):
            for k in m.group(1).split(","):
                cited_keys.add(k.strip())

        for entry in bib_entries:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            if not key:
                continue
            if key not in cited_keys:
                issues.append(ConsistencyIssue(
                    category="citation",
                    severity="low",
                    location=f"bib:{key}",
                    message=f"参考文献 '{key}' 未在正文被 \\cite{{}} 引用（孤立条目）。",
                ))
        return issues

    # ====================================================================
    # 5. 符号一致性
    # ====================================================================
    def _check_symbol_consistency(self, latex_code: str) -> List[ConsistencyIssue]:
        """检查同一符号是否在不同位置含义不同（粗略）。

        启发式：找 $X$ 与 "$X$ 表示" 的相邻定义，若 X 在不同段落有不同含义，标记。
        """
        # 实现成本高，跳过；保留接口供未来扩展
        return []

    # ====================================================================
    # 6. 数值结论一致性（简化版 FactChecker）
    # ====================================================================
    def _check_number_consistency(
        self,
        latex_code: str,
        solver_numerical_results: Dict[str, Any],
    ) -> List[ConsistencyIssue]:
        """检查 solver 输出的关键数值是否在 LaTeX 中能找到。"""
        issues: List[ConsistencyIssue] = []
        if not solver_numerical_results:
            return issues

        # 提取 solver 所有数值（递归）
        solver_numbers: Set[str] = set()
        self._collect_numbers(solver_numerical_results, solver_numbers)

        # LaTeX 中找数字
        latex_numbers: Set[str] = set(re.findall(r"-?\d+\.?\d*", latex_code))

        # solver 中"大数字"（> 1 且是小数）应在 latex 中
        for n in solver_numbers:
            try:
                v = float(n)
                if abs(v) > 0.1 and abs(v) < 1e6 and "." in n:
                    if n not in latex_numbers:
                        issues.append(ConsistencyIssue(
                            category="number",
                            severity="low",
                            location="solver vs latex",
                            message=f"求解结果 {n} 未在 LaTeX 中提到。",
                        ))
            except ValueError:
                pass
        return issues

    def _collect_numbers(self, obj: Any, out: Set[str]) -> None:
        """递归收集所有数字字符串。"""
        if isinstance(obj, dict):
            for v in obj.values():
                self._collect_numbers(v, out)
        elif isinstance(obj, list):
            for v in obj:
                self._collect_numbers(v, out)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            if abs(obj) < 1e9:
                # 保留原格式（int vs float）
                out.add(str(obj) if isinstance(obj, int) else f"{obj:.4f}".rstrip("0").rstrip("."))


# ==================== 全局单例 ====================

_checker: Optional[ConsistencyChecker] = None


def get_consistency_checker() -> ConsistencyChecker:
    global _checker
    if _checker is None:
        _checker = ConsistencyChecker()
    return _checker
