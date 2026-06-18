"""实验结果聚合器 —— 把 ExperimentRunner 的原始输出整理成论文可用的表格/图表。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .experiment_runner import ExperimentBatchResult, ExperimentRunResult

logger = logging.getLogger(__name__)


@dataclass
class AggregatedExperimentResult:
    """聚合后的实验结果。"""

    success: bool = False
    main_metrics: Dict[str, Any] = field(default_factory=dict)
    baseline_table: List[Dict[str, Any]] = field(default_factory=list)
    ablation_table: List[Dict[str, Any]] = field(default_factory=list)
    best_baseline: Optional[str] = None
    best_metric: Optional[str] = None
    figures: List[str] = field(default_factory=list)
    latex_table: str = ""
    markdown_table: str = ""
    summary_text: str = ""
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "main_metrics": self.main_metrics,
            "baseline_table": self.baseline_table,
            "ablation_table": self.ablation_table,
            "best_baseline": self.best_baseline,
            "best_metric": self.best_metric,
            "figures": self.figures,
            "latex_table": self.latex_table,
            "markdown_table": self.markdown_table,
            "summary_text": self.summary_text,
            "errors": self.errors,
        }


class ExperimentResultAggregator:
    """实验结果聚合器。"""

    def __init__(self, primary_metric: str = "accuracy", higher_is_better: bool = True):
        self.primary_metric = primary_metric
        self.higher_is_better = higher_is_better

    def aggregate(self, result: ExperimentBatchResult) -> AggregatedExperimentResult:
        """聚合一次批量实验的结果。"""
        aggregated = AggregatedExperimentResult()
        aggregated.success = result.success
        aggregated.figures = result.figures
        aggregated.errors = result.errors

        # 主实验指标
        if result.main:
            aggregated.main_metrics = result.main.metrics

        # baseline 表格
        for run in result.baselines:
            aggregated.baseline_table.append(
                {
                    "name": run.name,
                    "success": run.success,
                    "metrics": run.metrics,
                    "duration_sec": run.duration_sec,
                }
            )

        # ablation 表格
        for run in result.ablations:
            aggregated.ablation_table.append(
                {
                    "name": run.name,
                    "success": run.success,
                    "metrics": run.metrics,
                    "duration_sec": run.duration_sec,
                }
            )

        # 找出最佳 baseline
        best_value = None
        for row in aggregated.baseline_table:
            value = row["metrics"].get(self.primary_metric)
            if value is None:
                continue
            try:
                value = float(value)
            except (ValueError, TypeError):
                continue
            if best_value is None or (
                self.higher_is_better and value > best_value
            ) or (not self.higher_is_better and value < best_value):
                best_value = value
                aggregated.best_baseline = row["name"]
                aggregated.best_metric = f"{self.primary_metric}={value:.4f}"

        # 生成表格
        aggregated.markdown_table = self._build_markdown_table(aggregated)
        aggregated.latex_table = self._build_latex_table(aggregated)
        aggregated.summary_text = self._build_summary_text(aggregated)

        return aggregated

    # ------------------------------------------------------------------
    # 表格生成
    # ------------------------------------------------------------------

    def _build_markdown_table(self, aggregated: AggregatedExperimentResult) -> str:
        """生成 Markdown 对比表格。"""
        lines: List[str] = []
        rows = []

        if aggregated.main_metrics:
            rows.append({"Method": "Our Method", **aggregated.main_metrics})

        for row in aggregated.baseline_table:
            rows.append({"Method": row["name"], **row["metrics"]})

        if not rows:
            return ""

        # 收集所有列
        columns = ["Method"]
        for row in rows:
            for key in row:
                if key != "Method" and key not in columns:
                    columns.append(key)

        header = "| " + " | ".join(columns) + " |"
        separator = "|" + "|".join([" --- " for _ in columns]) + "|"
        lines.append(header)
        lines.append(separator)

        for row in rows:
            values = []
            for col in columns:
                val = row.get(col, "-")
                if isinstance(val, float):
                    val = f"{val:.4f}"
                values.append(str(val))
            lines.append("| " + " | ".join(values) + " |")

        return "\n".join(lines)

    def _build_latex_table(self, aggregated: AggregatedExperimentResult) -> str:
        """生成 LaTeX 对比表格。"""
        rows = []
        if aggregated.main_metrics:
            rows.append({"Method": "Our Method", **aggregated.main_metrics})
        for row in aggregated.baseline_table:
            rows.append({"Method": row["name"], **row["metrics"]})

        if not rows:
            return ""

        columns = ["Method"]
        for row in rows:
            for key in row:
                if key != "Method" and key not in columns:
                    columns.append(key)

        lines = [
            "\\begin{table}[htbp]",
            "\\centering",
            "\\caption{Comparison with Baselines}",
            f"\\begin{{tabular}}{{{'l' + 'c' * (len(columns) - 1)}}}",
            "\\toprule",
            " & ".join(columns) + " \\\\",
            "\\midrule",
        ]

        for row in rows:
            values = []
            for col in columns:
                val = row.get(col, "-")
                if isinstance(val, float):
                    val = f"{val:.4f}"
                values.append(str(val))
            lines.append(" & ".join(values) + " \\\\")

        lines.extend([
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
        ])

        return "\n".join(lines)

    def _build_summary_text(self, aggregated: AggregatedExperimentResult) -> str:
        """生成一段自然语言总结。"""
        parts: List[str] = []

        if not aggregated.success:
            parts.append("实验执行过程中出现错误，结果可能不完整。")
            if aggregated.errors:
                parts.append(f"错误信息：{'; '.join(aggregated.errors[:3])}")
            return " ".join(parts)

        main_value = aggregated.main_metrics.get(self.primary_metric)
        if main_value is not None:
            parts.append(f"主方法在 {self.primary_metric} 上达到 {main_value}。")

        if aggregated.best_baseline and aggregated.best_metric:
            parts.append(f"最强基线 {aggregated.best_baseline} 的 {aggregated.best_metric}。")
            main_val = self._to_float(aggregated.main_metrics.get(self.primary_metric))
            best_val = self._to_float(
                next(
                    (r["metrics"].get(self.primary_metric) for r in aggregated.baseline_table if r["name"] == aggregated.best_baseline),
                    None,
                )
            )
            if main_val is not None and best_val is not None:
                if self.higher_is_better:
                    improvement = ((main_val - best_val) / best_val * 100) if best_val != 0 else 0
                    parts.append(f"相比最强基线提升 {improvement:.2f}%。")
                else:
                    reduction = ((best_val - main_val) / best_val * 100) if best_val != 0 else 0
                    parts.append(f"相比最强基线降低 {reduction:.2f}%。")

        if aggregated.ablation_table:
            parts.append(f"消融实验共 {len(aggregated.ablation_table)} 组，验证了各组件贡献。")

        return " ".join(parts)

    def _to_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # 持久化辅助
    # ------------------------------------------------------------------

    def save(self, aggregated: AggregatedExperimentResult, output_path: Path) -> None:
        """保存聚合结果到 JSON。"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(aggregated.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def get_result_aggregator(
    primary_metric: str = "accuracy",
    higher_is_better: bool = True,
) -> ExperimentResultAggregator:
    """获取默认聚合器。"""
    return ExperimentResultAggregator(primary_metric=primary_metric, higher_is_better=higher_is_better)
