"""Neuro-Symbolic Auditor — 用符号逻辑和统计学验证实验结果

不依赖LLM的感性判断，而是用确定性算法验证：
- 表格加总一致性
- 百分比之和是否为100%
- 指标范围检查（准确率≤1.0等）
- 对比一致性（声称A优于B但A的指标更低）
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AuditFinding:
    """审计发现"""
    severity: str  # "error" | "warning" | "info"
    category: str  # "sum_mismatch" | "percentage" | "range" | "comparison" | "consistency"
    message: str
    location: str = ""  # 表格名/章节名
    expected: Optional[float] = None
    actual: Optional[float] = None


@dataclass
class AuditReport:
    """审计报告"""
    findings: List[AuditFinding] = field(default_factory=list)
    passed: bool = True
    score: float = 100.0  # 0-100

    def add(self, finding: AuditFinding):
        self.findings.append(finding)
        if finding.severity == "error":
            self.passed = False
            self.score -= 15
        elif finding.severity == "warning":
            self.score -= 5
        self.score = max(0, self.score)


def check_table_sums(
    data: Dict[str, List[float]],
    tolerance: float = 0.01,
) -> List[AuditFinding]:
    """检查表格列加总一致性

    Args:
        data: {列名: [数值列表]}
        tolerance: 允许的误差

    Returns:
        发现列表
    """
    findings = []
    for col_name, values in data.items():
        if len(values) < 2:
            continue
        # 检查是否有"总计"行（最后一个元素可能是总计）
        total = sum(values[:-1])
        last = values[-1]
        if abs(total - last) > tolerance and abs(total - last) / max(abs(last), 1e-10) > 0.01:
            findings.append(AuditFinding(
                severity="error",
                category="sum_mismatch",
                message=f"列 '{col_name}' 加总不一致: 各行之和={total:.4f}, 总计={last:.4f}, 差异={abs(total-last):.4f}",
                location=col_name,
                expected=total,
                actual=last,
            ))
    return findings


def check_percentages(
    percentages: List[float],
    tolerance: float = 0.5,
) -> List[AuditFinding]:
    """检查百分比之和是否接近100%"""
    findings = []
    if not percentages:
        return findings
    total = sum(percentages)
    if abs(total - 100.0) > tolerance:
        findings.append(AuditFinding(
            severity="error" if abs(total - 100.0) > 5 else "warning",
            category="percentage",
            message=f"百分比之和={total:.2f}%, 期望≈100%, 差异={abs(total-100.0):.2f}%",
            expected=100.0,
            actual=total,
        ))
    return findings


def check_metric_ranges(
    metrics: Dict[str, Tuple[float, float, float]],
) -> List[AuditFinding]:
    """检查指标是否在合理范围内

    Args:
        metrics: {指标名: (值, 最小值, 最大值)}
    """
    findings = []
    range_rules = {
        "accuracy": (0.0, 1.0),
        "precision": (0.0, 1.0),
        "recall": (0.0, 1.0),
        "f1": (0.0, 1.0),
        "f1_score": (0.0, 1.0),
        "auc": (0.0, 1.0),
        "r2": (-1.0, 1.0),
        "r_squared": (-1.0, 1.0),
        "sharpe": (-5.0, 10.0),
        "max_drawdown": (-1.0, 0.0),  # 通常为负数
        "return_rate": (-1.0, 10.0),
    }

    for metric_name, (value, _, _) in metrics.items():
        name_lower = metric_name.lower()
        for rule_name, (lo, hi) in range_rules.items():
            if rule_name in name_lower:
                if value < lo or value > hi:
                    findings.append(AuditFinding(
                        severity="error",
                        category="range",
                        message=f"指标 '{metric_name}'={value:.4f} 超出合理范围 [{lo}, {hi}]",
                        expected=(lo + hi) / 2,
                        actual=value,
                    ))
                break
    return findings


def check_comparison_claims(
    claims: List[Dict[str, Any]],
) -> List[AuditFinding]:
    """检查对比声明的一致性

    claims: [{"method_a": "XXX", "method_b": "YYY", "metric": "accuracy",
              "value_a": 0.95, "value_b": 0.90, "claim": "A优于B"}]
    """
    findings = []
    for claim in claims:
        value_a = claim.get("value_a")
        value_b = claim.get("value_b")
        claim_text = claim.get("claim", "")
        metric = claim.get("metric", "")

        if value_a is None or value_b is None:
            continue

        # 对于大多数指标，值越高越好
        higher_is_better = metric.lower() not in ("error", "loss", "mse", "mae", "rmse", "max_drawdown")

        if higher_is_better:
            if "优于" in claim_text or "better" in claim_text.lower():
                if value_a < value_b:
                    findings.append(AuditFinding(
                        severity="error",
                        category="comparison",
                        message=f"对比声明矛盾: 声称'{claim.get('method_a','?')}'优于'{claim.get('method_b','?')}' "
                                f"({metric}: {value_a} < {value_b})",
                        expected=value_a,
                        actual=value_b,
                    ))
        else:
            if "优于" in claim_text or "better" in claim_text.lower():
                if value_a > value_b:
                    findings.append(AuditFinding(
                        severity="error",
                        category="comparison",
                        message=f"对比声明矛盾: 声称'{claim.get('method_a','?')}'优于'{claim.get('method_b','?')}' "
                                f"({metric}: {value_a} > {value_b}, 越低越好)",
                        expected=value_a,
                        actual=value_b,
                    ))
    return findings


def check_numerical_consistency(
    numbers: Dict[str, float],
) -> List[AuditFinding]:
    """检查数值一致性（如：总数=各部分之和）"""
    findings = []

    # 检查常见的一致性关系
    # 例如：train_ratio + test_ratio + val_ratio ≈ 1.0
    ratio_keys = [k for k in numbers if "ratio" in k.lower() or "ratio" in k.lower()]
    if len(ratio_keys) >= 2:
        ratio_sum = sum(numbers[k] for k in ratio_keys)
        if abs(ratio_sum - 1.0) > 0.01:
            findings.append(AuditFinding(
                severity="warning",
                category="consistency",
                message=f"比率之和={ratio_sum:.4f}, 期望≈1.0 (涉及: {', '.join(ratio_keys)})",
                expected=1.0,
                actual=ratio_sum,
            ))

    return findings


def audit_experiment_results(
    tables: Optional[Dict[str, List[float]]] = None,
    percentages: Optional[List[float]] = None,
    metrics: Optional[Dict[str, Tuple[float, float, float]]] = None,
    comparison_claims: Optional[List[Dict[str, Any]]] = None,
    numbers: Optional[Dict[str, float]] = None,
) -> AuditReport:
    """综合审计实验结果

    Args:
        tables: 表格数据 {列名: [数值]}
        percentages: 百分比列表
        metrics: 指标 {名: (值, min, max)}
        comparison_claims: 对比声明列表
        numbers: 数值一致性检查 {名: 值}

    Returns:
        审计报告
    """
    report = AuditReport()

    if tables:
        for finding in check_table_sums(tables):
            report.add(finding)

    if percentages:
        for finding in check_percentages(percentages):
            report.add(finding)

    if metrics:
        for finding in check_metric_ranges(metrics):
            report.add(finding)

    if comparison_claims:
        for finding in check_comparison_claims(comparison_claims):
            report.add(finding)

    if numbers:
        for finding in check_numerical_consistency(numbers):
            report.add(finding)

    report.score = max(0, report.score)
    return report
