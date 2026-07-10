"""AST代码静态分析器 — 检测硬编码指标、伪造输出、缺少真实数据源

在代码送入沙箱执行前，用Python AST解析检测作弊嫌疑。
核心原则：Code-as-Truth，LLM只输出代码，数字由沙箱真实运行产生。
"""

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


# ===== 检测规则配置 =====

# 硬编码指标变量名（驼峰/下划线/缩写）
HARDCODED_METRIC_NAMES: Set[str] = {
    # 分类指标
    "accuracy", "acc", "precision", "recall", "f1", "f1_score", "f1score",
    "auc", "auc_roc", "auroc", "specificity", "sensitivity",
    # 回归指标
    "rmse", "mse", "mae", "mape", "r2", "r_squared", "rsquared", "nmse",
    # 排序指标
    "ndcg", "map", "mrr", "hit_rate",
    # 金融指标
    "sharpe", "sortino", "calmar", "max_drawdown", "drawdown",
    "volatility", "var", "cvar", "es", "beta", "alpha",
    "return_rate", "total_return", "annual_return", "excess_return",
    # 损失指标
    "loss", "val_loss", "train_loss", "test_loss", "total_loss",
    "cross_entropy", "nll_loss", "mse_loss",
    # 通用
    "score", "performance", "result", "metric", "measure",
}

# 硬编码数值的print模式
SUSPICIOUS_PRINT_PATTERNS = [
    re.compile(r"(?:accuracy|acc|precision|recall|f1|auc|rmse| mse |mae|r2|sharpe|sortino|calmar|loss)\s*[:=]\s*\d+\.?\d*", re.IGNORECASE),
    re.compile(r"\d+\.?\d*\s*%"),  # 直接输出百分比数字
    re.compile(r"(?:Accuracy|F1|Loss|Sharpe|Return|Drawdown)\s*:\s*\d+\.?\d*", re.IGNORECASE),
]

# 任务类型 → 期望存在的函数调用关键词
TASK_REQUIRED_FUNCTIONS = {
    "training": {"train", "fit", "epoch", "backward", "step", "optimizer"},
    "data_analysis": {"read_csv", "read_excel", "load", "DataFrame", "Series"},
    "optimization": {"minimize", "solve", "optimize", "linprog", "curve_fit"},
    "classification": {"predict", "fit", "transform", "fit_transform"},
    "regression": {"predict", "fit", "curve_fit", "polyfit"},
    "clustering": {"fit", "predict", "fit_predict"},
    "time_series": {"arima", "garch", "forecast", "predict", "fit"},
    "visualization": {"plot", "scatter", "bar", "hist", "savefig", "show"},
    "general": set(),  # 不强制要求
}


@dataclass
class AuditIssue:
    """审计问题"""
    line: int
    severity: str  # "error" | "warning"
    category: str  # "hardcoded_metric" | "fake_output" | "no_data_source" | "suspicious_print"
    message: str
    suggestion: str


@dataclass
class AuditResult:
    """审计结果"""
    passed: bool
    issues: List[AuditIssue] = field(default_factory=list)
    score: float = 100.0  # 0-100，100为完全通过
    summary: str = ""


class _MetricAssignDetector(ast.NodeVisitor):
    """检测硬编码指标赋值: accuracy = 0.95"""

    def __init__(self):
        self.issues: List[AuditIssue] = []

    def visit_Assign(self, node: ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id.lower()
                if name in HARDCODED_METRIC_NAMES:
                    # 检查赋值是否为常量数字
                    if isinstance(node.value, (ast.Constant, ast.Num)):
                        val = node.value.value if isinstance(node.value, ast.Constant) else node.value.n
                        if isinstance(val, (int, float)):
                            self.issues.append(AuditIssue(
                                line=node.lineno,
                                severity="error",
                                category="hardcoded_metric",
                                message=f"硬编码指标赋值: {target.id} = {val}",
                                suggestion=f"应从模型预测结果或评估函数获取 {target.id}，而非直接赋值",
                            ))
                    # 检查赋值是否为固定字符串
                    elif isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        val = node.value.value
                        if re.search(r"\d+\.?\d*\s*%?", val):
                            self.issues.append(AuditIssue(
                                line=node.lineno,
                                severity="error",
                                category="hardcoded_metric",
                                message=f"硬编码指标字符串: {target.id} = \"{val}\"",
                                suggestion=f"应从实际计算结果生成 {target.id}，而非硬编码字符串",
                            ))
        self.generic_visit(node)


class _FakeOutputDetector(ast.NodeVisitor):
    """检测伪造输出: print("Accuracy: 95.2%")"""

    def __init__(self):
        self.issues: List[AuditIssue] = []

    def visit_Expr(self, node: ast.Expr):
        if isinstance(node.value, ast.Call):
            func = node.value.func
            # 检测 print() 调用
            if isinstance(func, ast.Name) and func.id == "print":
                for arg in node.value.args:
                    arg_str = ast.unparse(arg) if hasattr(ast, 'unparse') else str(arg)
                    for pattern in SUSPICIOUS_PRINT_PATTERNS:
                        if pattern.search(arg_str):
                            self.issues.append(AuditIssue(
                                line=node.lineno,
                                severity="warning",
                                category="fake_output",
                                message=f"疑似伪造输出: print({arg_str[:80]})",
                                suggestion="print的参数应引用变量，而非包含固定数字的字符串",
                            ))
                            break
        self.generic_visit(node)


class _DataSourceDetector(ast.NodeVisitor):
    """检测是否缺少真实数据源调用"""

    def __init__(self, task_type: str = "general"):
        self.task_type = task_type
        self.found_functions: Set[str] = set()
        self.has_file_io = False
        self.has_model_call = False

    def visit_Call(self, node: ast.Call):
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        self.found_functions.add(func_name.lower())

        # 检测文件IO
        if func_name in ("read_csv", "read_excel", "loadtxt", "genfromtxt", "open",
                         "read_json", "read_parquet", "read_feather"):
            self.has_file_io = True

        # 检测模型调用
        if func_name in ("fit", "train", "predict", "transform", "fit_transform",
                         "fit_predict", "score", "evaluate"):
            self.has_model_call = True

        self.generic_visit(node)

    def check(self) -> List[AuditIssue]:
        issues = []
        required = TASK_REQUIRED_FUNCTIONS.get(self.task_type, set())
        if not required:
            return issues

        # 如果有文件IO，数据源方面没问题
        if self.has_file_io:
            return issues

        # 检查是否有必要函数调用
        found_required = required & self.found_functions
        if not found_required and required:
            issues.append(AuditIssue(
                line=0,
                severity="warning",
                category="no_data_source",
                message=f"任务类型 '{self.task_type}' 未检测到数据读取函数调用",
                suggestion=f"建议使用 read_csv/read_excel 等函数从文件加载数据，而非内联数据",
            ))

        return issues


def _check_inline_data(node: ast.AST) -> List[AuditIssue]:
    """检测大量内联数据（列表字面量中包含过多数字）"""
    issues = []

    for child in ast.walk(node):
        if isinstance(child, ast.List):
            # 检查列表是否包含大量数字常量
            numeric_count = 0
            for elt in child.elts:
                if isinstance(elt, (ast.Constant, ast.Num)):
                    val = elt.value if isinstance(elt, ast.Constant) else elt.n
                    if isinstance(val, (int, float)):
                        numeric_count += 1
            if numeric_count > 20:  # 超过20个数字视为可疑内联数据
                issues.append(AuditIssue(
                    line=getattr(child, 'lineno', 0),
                    severity="warning",
                    category="no_data_source",
                    message=f"检测到大量内联数值数据（{numeric_count}个），疑似硬编码数据集",
                    suggestion="建议从文件或API加载数据，而非在代码中硬编码",
                ))

    return issues


def audit_code(code: str, task_type: str = "general") -> AuditResult:
    """AST分析代码，检测作弊嫌疑

    Args:
        code: Python源代码
        task_type: 任务类型 (training/data_analysis/optimization/classification等)

    Returns:
        AuditResult: 审计结果
    """
    issues: List[AuditIssue] = []

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return AuditResult(
            passed=False,
            issues=[AuditIssue(line=e.lineno or 0, severity="error", category="syntax_error",
                               message=f"语法错误: {e.msg}", suggestion="修复语法错误后重试")],
            score=0,
            summary="代码语法错误，无法解析",
        )

    # 1. 硬编码指标赋值检测
    detector1 = _MetricAssignDetector()
    detector1.visit(tree)
    issues.extend(detector1.issues)

    # 2. 伪造输出检测
    detector2 = _FakeOutputDetector()
    detector2.visit(tree)
    issues.extend(detector2.issues)

    # 3. 数据源检测
    detector3 = _DataSourceDetector(task_type)
    detector3.visit(tree)
    issues.extend(detector3.check())

    # 4. 内联数据检测
    issues.extend(_check_inline_data(tree))

    # 计算分数
    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    score = max(0, 100 - error_count * 20 - warning_count * 5)

    passed = error_count == 0  # 有error则不通过

    summary_parts = []
    if error_count:
        summary_parts.append(f"{error_count}个严重问题")
    if warning_count:
        summary_parts.append(f"{warning_count}个警告")
    summary = "通过" if not summary_parts else f"发现{', '.join(summary_parts)}"

    return AuditResult(
        passed=passed,
        issues=issues,
        score=score,
        summary=summary,
    )
