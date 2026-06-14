"""论文事实核查（Harness 扩展 Phase 5）。

把 writer 生成的 main.tex 中的数字与 solver 产出的 solves.json/numerical_results
做对比，标记不一致或无法溯源的数字。
"""
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FactCheckIssue:
    def __init__(
        self,
        latex_key: str,
        latex_value: float,
        solve_value: Optional[float],
        relative_diff: Optional[float],
        message: str,
    ):
        self.latex_key = latex_key
        self.latex_value = latex_value
        self.solve_value = solve_value
        self.relative_diff = relative_diff
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "latex_key": self.latex_key,
            "latex_value": self.latex_value,
            "solve_value": self.solve_value,
            "relative_diff": self.relative_diff,
            "message": self.message,
        }


class FactChecker:
    """论文数字与求解结果对账。"""

    NUMBER_RE = re.compile(r"-?\d+\.?\d*(?:[eE][+-]?\d+)?")

    def extract_numbers_from_latex(self, latex_code: str) -> Dict[str, float]:
        r"""从 LaTeX 源码中提取数字，跳过 \cite{} 内部，用上下文片段做 key。"""
        numbers: Dict[str, float] = {}
        if not latex_code:
            return numbers

        # 简单移除 \cite{...} 避免把引用编号/年份当结果
        cleaned = re.sub(r"\\cite(?:p|t)?\{[^}]*\}", "", latex_code)

        for m in self.NUMBER_RE.finditer(cleaned):
            val_str = m.group(0)
            try:
                val = float(val_str)
            except ValueError:
                continue
            start = max(0, m.start() - 20)
            end = min(len(cleaned), m.end() + 20)
            context = cleaned[start:end].replace("\n", " ").strip()
            if context not in numbers:
                numbers[context] = val
        return numbers

    def extract_numbers_from_solves(self, solves: Any) -> Dict[str, float]:
        """递归地从 solves.json / numerical_results 中提取所有数字。"""
        numbers: Dict[str, float] = {}
        self._collect_numbers(solves, "", numbers)
        return numbers

    def _collect_numbers(self, obj: Any, path: str, out: Dict[str, float]) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                self._collect_numbers(v, f"{path}.{k}" if path else k, out)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                self._collect_numbers(v, f"{path}[{i}]", out)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            # 避免把年份/ID 等整数误判：只记录非 huge 数值
            if abs(obj) < 1e9:
                out[path] = float(obj)

    def compare(
        self,
        latex_numbers: Dict[str, float],
        solve_numbers: Dict[str, float],
        threshold: float = 0.05,
    ) -> List[FactCheckIssue]:
        """对比 LaTeX 数字与求解数字，返回不一致列表。"""
        issues: List[FactCheckIssue] = []
        solve_values = list(solve_numbers.values())

        for ctx, lval in latex_numbers.items():
            # 在 solves 中找最接近的值
            best: Optional[Tuple[str, float, float]] = None
            for spath, sval in solve_numbers.items():
                if sval == 0:
                    diff = abs(lval) if lval != 0 else 0
                    rel = diff
                else:
                    rel = abs(lval - sval) / abs(sval)
                if best is None or rel < best[2]:
                    best = (spath, sval, rel)

            if best is None:
                issues.append(FactCheckIssue(ctx, lval, None, None, "在求解结果中找不到对应数字"))
                continue

            spath, sval, rel = best
            if rel > threshold:
                issues.append(
                    FactCheckIssue(
                        ctx, lval, sval, rel,
                        f"LaTeX 数字 {lval} 与求解结果 {spath}={sval} 相对差异 {rel:.2%}，超阈值 {threshold:.2%}",
                    )
                )

        # 反向检查：求解结果中的数字是否出现在论文中
        latex_values = list(latex_numbers.values())
        for spath, sval in solve_numbers.items():
            found = any(
                self._relative_diff(sval, lval) <= threshold for lval in latex_values
            )
            if not found:
                issues.append(
                    FactCheckIssue(
                        "latex_missing", 0.0, sval, None,
                        f"求解结果 {spath}={sval} 未在 LaTeX 中找到",
                    )
                )

        return issues

    @staticmethod
    def _relative_diff(a: float, b: float) -> float:
        if a == 0 and b == 0:
            return 0.0
        if a == 0 or b == 0:
            return abs(a - b)
        return abs(a - b) / max(abs(a), abs(b))

    def check(
        self,
        task_id: str,
        output_dir: Path,
        threshold: float = 0.05,
    ) -> Dict[str, Any]:
        """检查指定任务 output 目录下的 main.tex 与 solves.json。"""
        output_dir = Path(output_dir)
        latex_file = output_dir / "final" / "main.tex"
        solves_file = output_dir / "final" / "solves.json"
        if not solves_file.exists():
            solves_file = output_dir / "solves.json"

        latex_code = ""
        if latex_file.exists():
            latex_code = latex_file.read_text(encoding="utf-8")
        else:
            logger.warning(f"FactChecker: {latex_file} not found")

        solves: Dict[str, Any] = {}
        if solves_file.exists():
            try:
                solves = json.loads(solves_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"FactChecker: failed to read solves.json: {e}")
        else:
            logger.warning(f"FactChecker: {solves_file} not found")

        latex_numbers = self.extract_numbers_from_latex(latex_code)
        solve_numbers = self.extract_numbers_from_solves(solves)
        issues = self.compare(latex_numbers, solve_numbers, threshold)

        report = {
            "task_id": task_id,
            "latex_file": str(latex_file),
            "solves_file": str(solves_file),
            "latex_number_count": len(latex_numbers),
            "solve_number_count": len(solve_numbers),
            "issue_count": len(issues),
            "issues": [i.to_dict() for i in issues],
            "passed": len(issues) == 0,
        }
        return report


_fact_checker: Optional[FactChecker] = None


def get_fact_checker() -> FactChecker:
    global _fact_checker
    if _fact_checker is None:
        _fact_checker = FactChecker()
    return _fact_checker
