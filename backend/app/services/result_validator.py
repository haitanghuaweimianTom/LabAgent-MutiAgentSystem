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
        if any(k in lower_key for k in ["概率", "比例", "percentage", "percent", "ratio", "accuracy", "r2", "precision", "recall", "f1", "auc"]):
            if abs_val > 1.0:
                self.issues.append(ValidationIssue("error", "range", f"概率/比例字段 {path} 超过 1.0 ({value})", path))
            if abs_val < 0:
                self.issues.append(ValidationIssue("error", "range", f"概率/比例字段 {path} 为负数 ({value})", path))

        # 准确率/精确率/召回率/F1 特殊检查
        if any(k in lower_key for k in ["accuracy", "精确率", "precision", "recall", "召回率", "f1", "auc"]):
            if abs_val > 1.0:
                self.issues.append(ValidationIssue("error", "range", f"指标 {path} 不能大于 1.0 ({value})", path))
            if abs_val < 0:
                self.issues.append(ValidationIssue("error", "range", f"指标 {path} 不能为负数 ({value})", path))

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


# ====================================================================
# Phase 7: 跨方法交叉验证 (CrossValidator)
# ====================================================================
# 目标：把"同一结论用两种方法重算，差异 > 阈值则报警"做成可调用 API。
# 严格控制幻觉：
#   - 不创造数字；只比对 *实际收到* 的两组结果
#   - 替代方法缺失时返回 skipped=True，不报伪警
#   - 阈值在 config 中可调（默认 5%）
# ====================================================================

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class CrossValidationResult:
    """一次跨方法比对的结果。"""

    method_a: str
    method_b: str
    field: str
    value_a: Any
    value_b: Any
    abs_diff: float
    rel_diff: float
    diverged: bool
    threshold: float
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method_a": self.method_a,
            "method_b": self.method_b,
            "field": self.field,
            "value_a": self.value_a,
            "value_b": self.value_b,
            "abs_diff": round(self.abs_diff, 6),
            "rel_diff": round(self.rel_diff, 4),
            "diverged": self.diverged,
            "threshold": self.threshold,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


ALTERNATIVE_METHODS: Dict[str, Callable[..., Any]] = {}


def register_alternative_method(name: str, fn: Callable[..., Any]) -> None:
    """注册一种替代方法实现。"""
    ALTERNATIVE_METHODS[name] = fn


class CrossValidator:
    """跨方法交叉验证器。"""

    DEFAULT_THRESHOLD = 0.05  # 5%

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = float(threshold)

    async def cross_check(
        self,
        method_a_name: str,
        method_a_results: Dict[str, Any],
        method_b_name: str,
        method_b_results: Dict[str, Any],
        fields: Optional[List[str]] = None,
        threshold: Optional[float] = None,
    ) -> List[CrossValidationResult]:
        """比对两组结果中指定字段。仅在两组结果都 *实际包含* 字段时才比对，
        否则返回 ``skipped=True``。
        """
        thr = threshold if threshold is not None else self.threshold
        fields = fields or sorted(set(method_a_results.keys()) & set(method_b_results.keys()))

        results: List[CrossValidationResult] = []
        for f in fields:
            a = method_a_results.get(f)
            b = method_b_results.get(f)
            if a is None or b is None:
                results.append(CrossValidationResult(
                    method_a=method_a_name, method_b=method_b_name,
                    field=f, value_a=a, value_b=b,
                    abs_diff=0.0, rel_diff=0.0, diverged=False,
                    threshold=thr, skipped=True,
                    skip_reason=f"missing field in {'a' if a is None else 'b'}",
                ))
                continue
            try:
                a_f, b_f = float(a), float(b)
            except (TypeError, ValueError):
                results.append(CrossValidationResult(
                    method_a=method_a_name, method_b=method_b_name,
                    field=f, value_a=a, value_b=b,
                    abs_diff=0.0, rel_diff=0.0, diverged=False,
                    threshold=thr, skipped=True,
                    skip_reason=f"non-numeric value",
                ))
                continue
            denom = max(abs(a_f), abs(b_f), 1e-9)
            rel = abs(a_f - b_f) / denom
            diverged = rel > thr
            results.append(CrossValidationResult(
                method_a=method_a_name, method_b=method_b_name,
                field=f, value_a=a_f, value_b=b_f,
                abs_diff=abs(a_f - b_f), rel_diff=rel,
                diverged=diverged, threshold=thr,
            ))
        return results

    async def cross_check_from_methods(
        self,
        method_a_name: str,
        method_b_name: str,
        problem_text: str,
        params: Optional[Dict[str, Any]] = None,
        fields: Optional[List[str]] = None,
    ) -> List[CrossValidationResult]:
        """动态调两种注册方法（ALTERNATIVE_METHODS），再 cross_check。

        特殊支持：``method_a_name == "primary"`` 时直接取 ``params["numerical_results"]``，
        无需额外注册 primary 方法。
        """
        params = params or {}
        if method_a_name != "primary" and method_a_name not in ALTERNATIVE_METHODS:
            raise KeyError(f"method_a not registered: {method_a_name}")
        if method_b_name not in ALTERNATIVE_METHODS:
            raise KeyError(f"method_b not registered: {method_b_name}")

        if method_a_name == "primary":
            a_res = params.get("numerical_results", {})
        else:
            fn_a = ALTERNATIVE_METHODS[method_a_name]
            if asyncio.iscoroutinefunction(fn_a):
                a_res = await fn_a(problem_text, **params)
            else:
                a_res = await asyncio.to_thread(fn_a, problem_text, **params)
        fn_b = ALTERNATIVE_METHODS[method_b_name]
        if asyncio.iscoroutinefunction(fn_b):
            b_res = await fn_b(problem_text, **params)
        else:
            b_res = await asyncio.to_thread(fn_b, problem_text, **params)
        if isinstance(a_res, Exception):
            a_res = {"_error": str(a_res)}
        if isinstance(b_res, Exception):
            b_res = {"_error": str(b_res)}
        return await self.cross_check(
            method_a_name, a_res, method_b_name, b_res, fields=fields,
        )


_validator_instance: Optional[CrossValidator] = None


def get_cross_validator(threshold: float = CrossValidator.DEFAULT_THRESHOLD) -> CrossValidator:
    """获取全局 CrossValidator。"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = CrossValidator(threshold=threshold)
    return _validator_instance


# ====================================================================
# 预注册通用替代方法
# ====================================================================

def _analytical_estimate(problem_text: str, **params: Any) -> Dict[str, Any]:
    """基于问题关键词的解析/边界估计（零 LLM 依赖）。

    策略：只在能计算出有意义的理论边界时返回结果，否则返回空 dict（跳过交叉验证）。
    不返回无意义的 0.0 常量——那会产生大量误报。

    能做的：
    - 回归问题：返回 [0, 1] 的 R² 合理范围提示（但不返回具体值）
    - 分类问题：返回 accuracy 应在 [0, 1] 的约束
    - 无法做的：LP、MCMC、图论等问题需要实际求解器，此处跳过
    """
    text = (problem_text or "").lower()
    result: Dict[str, Any] = {}

    # 回归 / 机器学习：只返回合理范围约束，不返回具体值
    # CrossValidator 可以用这些范围做 sanity check（如 R² > 1.0 则报错）
    if any(k in text for k in ("regression", "预测", "classification", "分类", "回归")):
        # 提取 numerical_results 中的数值做范围校验
        numerical_results = params.get("numerical_results", {})
        if numerical_results:
            for key, value in numerical_results.items():
                if isinstance(value, (int, float)):
                    key_lower = key.lower()
                    # R² 应在 [0, 1]（负值表示模型比均值差，但理论上可能）
                    if "r2" in key_lower or "r_squared" in key_lower:
                        if value > 1.0:
                            result[key] = {"bound": "upper", "limit": 1.0, "actual": value}
                    # Accuracy 应在 [0, 1]
                    if "accuracy" in key_lower or "acc" in key_lower:
                        if value > 1.0 or value < 0:
                            result[key] = {"bound": "range", "lower": 0, "upper": 1.0, "actual": value}
                    # Precision/Recall 应在 [0, 1]
                    if any(m in key_lower for m in ("precision", "recall", "f1")):
                        if value > 1.0 or value < 0:
                            result[key] = {"bound": "range", "lower": 0, "upper": 1.0, "actual": value}
                    # RMSE 应 > 0
                    if "rmse" in key_lower or "mse" in key_lower:
                        if value < 0:
                            result[key] = {"bound": "lower", "limit": 0, "actual": value}

    # 线性规划：如果有 numerical_results，校验最优值是否为数值
    if any(k in text for k in ("linear programming", "linear program", "lp", "线性规划")):
        numerical_results = params.get("numerical_results", {})
        optimal = numerical_results.get("optimal_value")
        if optimal is not None and not isinstance(optimal, (int, float)):
            result["optimal_value"] = {"bound": "type", "expected": "numeric", "actual": type(optimal).__name__}

    # 其他问题类型（MCMC、图论等）：无法做解析估计，返回空（跳过交叉验证）
    # 这比返回无意义的 0.0 要好——避免假误报

    return result


register_alternative_method("analytical_estimate", _analytical_estimate)


# 占位：llm_second_opinion 由 solver_agent 在初始化时注册，
# 以避免 result_validator 直接依赖 LLM 调用链。
