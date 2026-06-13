"""求解结果验证服务"""
import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ValidationIssue:
    """验证问题"""
    def __init__(self, level: str, category: str, message: str, field: Optional[str] = None):
        self.level = level  # error, warning
        self.category = category
        self.message = message
        self.field = field

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "field": self.field,
        }


class ResultValidator:
    """验证 SolverAgent 输出结果的结构化数值是否合理"""

    def __init__(self):
        self.issues: List[ValidationIssue] = []

    def validate(self, numerical_results: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """验证数值结果并返回报告"""
        self.issues = []
        context = context or {}

        if not numerical_results or not isinstance(numerical_results, dict):
            self.issues.append(ValidationIssue("error", "empty", "数值结果为空或格式错误"))
            return self._report()

        # 递归检查所有数值
        self._check_dict(numerical_results, context)

        # 根据模型类型做特定检查
        model_info = context.get("model", {})
        self._check_model_specific(numerical_results, model_info)

        return self._report()

    def _check_dict(self, data: Dict[str, Any], context: Dict[str, Any], path: str = "") -> None:
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            self._check_value(key, value, current_path, context)

    def _check_value(self, key: str, value: Any, path: str, context: Dict[str, Any]) -> None:
        if isinstance(value, dict):
            self._check_dict(value, context, path)
            return

        if isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                self._check_value(f"{key}[{i}]", item, f"{path}[{i}]", context)
            return

        if isinstance(value, (int, float)):
            self._check_number(key, value, path, context)

    def _check_number(self, key: str, value: float, path: str, context: Dict[str, Any]) -> None:
        # NaN / Inf 检查
        if isinstance(value, float):
            if math.isnan(value):
                self.issues.append(ValidationIssue("error", "nan", f"字段 {path} 为 NaN", path))
                return
            if math.isinf(value):
                self.issues.append(ValidationIssue("error", "inf", f"字段 {path} 为无穷大", path))
                return

        # 常见异常值检查
        abs_val = abs(value)
        if abs_val > 1e12:
            self.issues.append(ValidationIssue("warning", "magnitude", f"字段 {path} 数值过大 ({value})", path))
        if 0 < abs_val < 1e-12:
            self.issues.append(ValidationIssue("warning", "magnitude", f"字段 {path} 数值过小 ({value})", path))

        # 概率/比例字段检查
        lower_key = key.lower()
        if any(k in lower_key for k in ["概率", "比例", "percentage", "percent", "ratio", "accuracy", "r2", "precision", "recall"]):
            if abs_val > 1.0:
                self.issues.append(ValidationIssue("warning", "range", f"概率/比例字段 {path} 超过 1.0 ({value})", path))

        # 非负字段检查
        if any(k in lower_key for k in ["厚度", "距离", "长度", "数量", "人数", "价格", "成本", "销量", "weight", "count", "distance", "thickness"]):
            if value < 0:
                self.issues.append(ValidationIssue("error", "negative", f"非负字段 {path} 为负数 ({value})", path))

    def _check_model_specific(self, numerical_results: Dict[str, Any], model_info: Dict[str, Any]) -> None:
        model_type = (model_info.get("model_type") or "").lower()
        model_name = (model_info.get("model_name") or "").lower()

        # 优化问题：检查最优值与约束
        if model_type in ("optimization", "linear_programming", "integer_programming", "nonlinear_optimization"):
            optimal_value = numerical_results.get("optimal_value")
            if optimal_value is None:
                self.issues.append(ValidationIssue("warning", "missing", "优化问题缺少 optimal_value"))

        # 回归问题：检查 R2
        if any(k in model_name for k in ["回归", "regression", "random forest", "svm", "neural"]):
            r2 = numerical_results.get("R2") or numerical_results.get("r2")
            if r2 is not None and r2 > 1.0:
                self.issues.append(ValidationIssue("error", "range", f"R² 不能大于 1.0 ({r2})", "R2"))
            if r2 is not None and r2 < 0:
                self.issues.append(ValidationIssue("warning", "range", f"R² 为负 ({r2})，模型可能欠拟合", "R2"))

        # AHP：一致性比率
        if "ahp" in model_name or "层次分析" in model_name:
            cr = numerical_results.get("CR")
            if cr is not None and cr >= 0.1:
                self.issues.append(ValidationIssue("warning", "consistency", f"AHP 一致性比率 CR={cr} ≥ 0.1，判断矩阵一致性不足", "CR"))

    def _report(self) -> Dict[str, Any]:
        errors = [i for i in self.issues if i.level == "error"]
        warnings = [i for i in self.issues if i.level == "warning"]
        return {
            "valid": len(errors) == 0,
            "passed": len(errors) == 0,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "issues": [i.to_dict() for i in self.issues],
            "errors": [i.to_dict() for i in errors],
            "warnings": [i.to_dict() for i in warnings],
        }


# 全局实例
_validator: Optional[ResultValidator] = None


def get_result_validator() -> ResultValidator:
    global _validator
    if _validator is None:
        _validator = ResultValidator()
    return _validator
