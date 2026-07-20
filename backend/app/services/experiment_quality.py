"""实验质量评估 —— 用真实 metrics / 失败率 / 缺表项驱动迭代。

替代原先「字段是否存在」的浅判据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExperimentQualityReport:
    needs_iteration: bool
    score: float  # 0-1
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    feedback: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "needs_iteration": self.needs_iteration,
            "score": self.score,
            "reasons": self.reasons,
            "metrics": self.metrics,
            "feedback": self.feedback,
        }


def _as_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:
            return {}
    return {}


def _count_failures(experiment_output: Dict[str, Any]) -> Dict[str, int]:
    raw = _as_dict(experiment_output.get("raw_batch"))
    errors = experiment_output.get("errors") or []
    scripts = raw.get("scripts") or raw.get("results") or []
    failed = 0
    total = 0
    if isinstance(scripts, list):
        for s in scripts:
            if not isinstance(s, dict):
                continue
            total += 1
            if not s.get("success", s.get("ok", True)):
                failed += 1
    if isinstance(errors, list):
        failed = max(failed, len(errors))
    return {"failed": failed, "total": max(total, failed), "error_count": len(errors) if isinstance(errors, list) else 0}


def _has_numeric_metrics(obj: Any) -> bool:
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return True
    if isinstance(obj, dict):
        return any(_has_numeric_metrics(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_numeric_metrics(v) for v in obj)
    return False


def evaluate_experiment_quality(
    experiment_output: Optional[Dict[str, Any]],
    *,
    min_baselines: int = 2,
    require_ablation: bool = True,
    max_failure_rate: float = 0.5,
    min_score_to_pass: float = 0.55,
) -> ExperimentQualityReport:
    """评估实验输出质量，决定是否继续迭代。"""
    output = experiment_output if isinstance(experiment_output, dict) else {}
    reasons: List[str] = []
    score = 1.0
    metrics: Dict[str, Any] = {}

    executed = bool(output.get("executed", False))
    metrics["executed"] = executed
    if not executed:
        # 未执行：若只有 plan，不强制迭代（避免死循环），但给低分反馈
        return ExperimentQualityReport(
            needs_iteration=False,
            score=0.2,
            reasons=["实验未实际执行"],
            metrics=metrics,
            feedback="实验设计完成但未执行；若环境允许请执行 train/eval 脚本",
        )

    failures = _count_failures(output)
    metrics.update(failures)
    total = max(failures["total"], 1)
    failure_rate = failures["failed"] / total
    metrics["failure_rate"] = round(failure_rate, 3)
    if failure_rate > max_failure_rate:
        reasons.append(f"脚本失败率过高 ({failure_rate:.0%} > {max_failure_rate:.0%})")
        score -= 0.35

    # baseline 对比：要求真实条目 + 至少一个数值
    baseline = output.get("baseline_comparison") or {}
    if isinstance(baseline, list):
        baseline_items = baseline
    else:
        baseline_items = (
            baseline.get("methods")
            or baseline.get("results")
            or baseline.get("comparisons")
            or ([] if not baseline else [baseline])
        )
    baseline_count = len(baseline_items) if isinstance(baseline_items, list) else 0
    metrics["baseline_count"] = baseline_count
    has_baseline_numbers = _has_numeric_metrics(baseline)
    metrics["baseline_has_numbers"] = has_baseline_numbers
    if baseline_count < min_baselines or not has_baseline_numbers:
        reasons.append(
            f"baseline 对比不足（条目={baseline_count}，需≥{min_baselines}且含真实数值）"
        )
        score -= 0.25

    # ablation
    ablation = output.get("ablation_study") or output.get("ablation") or {}
    if isinstance(ablation, list):
        ablation_items = ablation
    else:
        ablation_items = (
            ablation.get("components")
            or ablation.get("results")
            or ([] if not ablation else [ablation])
        )
    ablation_count = len(ablation_items) if isinstance(ablation_items, list) else 0
    has_ablation_numbers = _has_numeric_metrics(ablation)
    metrics["ablation_count"] = ablation_count
    metrics["ablation_has_numbers"] = has_ablation_numbers
    if require_ablation and (ablation_count < 1 or not has_ablation_numbers):
        reasons.append("缺少带真实数值的 ablation study")
        score -= 0.2

    # 聚合 metrics
    aggregated = _as_dict(output.get("aggregated"))
    primary_metrics = (
        aggregated.get("primary_metrics")
        or aggregated.get("metrics")
        or output.get("metrics")
        or {}
    )
    metrics["has_primary_metrics"] = _has_numeric_metrics(primary_metrics)
    if not metrics["has_primary_metrics"]:
        reasons.append("缺少主指标数值（accuracy/F1/loss 等）")
        score -= 0.2

    # 错误列表
    if output.get("errors"):
        reasons.append(f"存在 {len(output['errors'])} 条执行错误")
        score -= 0.1

    score = max(0.0, min(1.0, round(score, 3)))
    needs = bool(reasons) and score < min_score_to_pass

    feedback_parts = list(reasons) if reasons else ["实验质量达标"]
    if needs:
        feedback_parts.append("请修复失败脚本、补齐带数值的 baseline 与 ablation，并导出主指标表")

    return ExperimentQualityReport(
        needs_iteration=needs,
        score=score,
        reasons=reasons,
        metrics=metrics,
        feedback="；".join(feedback_parts),
    )
