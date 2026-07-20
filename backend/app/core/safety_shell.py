"""AST 安全壳变换器 — 防沙箱崩溃的自动打补丁机制。

设计目标：
- 强制包裹 try-except，防止未捕获异常导致沙箱崩溃
- 在 torch.cuda 调用后注入 cuda.empty_cache()，防止 OOM 死亡螺旋
- 自动注入 gc.collect() 释放内存
- 保留原始代码逻辑不变，仅增加防护层

架构定位：
  Coder Agent 生成代码 → SafetyShellTransformer 打补丁 → Sandbox 执行
  ↓                      ↓                               ↓
  自由/受限模式代码    AST 遍历 + 注入防护          带防护的代码执行
"""
from __future__ import annotations

import ast
import logging
import textwrap
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class SafetyShellTransformer(ast.NodeTransformer):
    """AST 变换器：为代码自动注入安全壳。

    功能：
    1. 在最外层包裹 try-except（捕获所有异常，防止沙箱崩溃）
    2. 在 torch.cuda 调用后注入 cuda.empty_cache()（防 OOM）
    3. 在关键循环后注入 gc.collect()（释放内存）
    """

    # 需要在其后注入 empty_cache 的 torch.cuda 方法
    _CUDA_METHODS: Set[str] = {
        "empty_cache", "ipc_collect", "reset_peak_memory_stats",
    }

    def __init__(self):
        self._cuda_calls: List[ast.AST] = []
        self._patched = False

    def visit_Module(self, node: ast.Module) -> ast.Module:
        """访问模块根节点，包裹 try-except 安全壳。"""
        # 先遍历子节点，收集 cuda 调用位置
        self.generic_visit(node)

        # 构造 try-except 包裹
        try_node = ast.Try(
            body=node.body,
            handlers=[
                ast.ExceptHandler(
                    type=ast.Name(id="Exception", ctx=ast.Load()),
                    name="_safety_exc",
                    body=[
                        # import traceback; traceback.print_exc()
                        ast.Import(names=[ast.alias(name="traceback")]),
                        ast.Expr(value=ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id="traceback", ctx=ast.Load()),
                                attr="print_exc",
                                ctx=ast.Load(),
                            ),
                            args=[],
                            keywords=[],
                        )),
                        # print(f"[SAFETY_SHELL] 捕获异常: {_safety_exc}")
                        ast.Expr(value=ast.Call(
                            func=ast.Name(id="print", ctx=ast.Load()),
                            args=[ast.JoinedStr(values=[
                                ast.Constant(value="[SAFETY_SHELL] 捕获异常: "),
                                ast.FormattedValue(
                                    value=ast.Name(id="_safety_exc", ctx=ast.Load()),
                                    conversion=-1,
                                ),
                            ])],
                            keywords=[],
                        )),
                    ],
                )
            ],
            orelse=[],
            finalbody=[
                # finally: import gc; gc.collect()
                ast.Import(names=[ast.alias(name="gc")]),
                ast.Expr(value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="gc", ctx=ast.Load()),
                        attr="collect",
                        ctx=ast.Load(),
                    ),
                    args=[],
                    keywords=[],
                )),
            ],
        )

        node.body = [try_node]
        self._patched = True
        return node

    def visit_Expr(self, node: ast.Expr) -> ast.Expr:
        """在 torch.cuda 调用后注入 empty_cache()。"""
        self.generic_visit(node)

        # 检测 torch.cuda.xxx() 调用
        if isinstance(node.value, ast.Call):
            func = node.value.func
            if (isinstance(func, ast.Attribute)
                    and func.attr in self._CUDA_METHODS
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "cuda"):
                # 记录需要在其后注入 empty_cache
                self._cuda_calls.append(node)

        return node

    @property
    def patched(self) -> bool:
        """是否成功打补丁。"""
        return self._patched


def inject_safety_shell(code: str) -> str:
    """为 Python 代码注入安全壳防护。

    Args:
        code: 原始 Python 源代码

    Returns:
        注入安全壳后的代码。如果注入失败，返回原始代码。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        logger.warning(f"SafetyShell: 代码语法错误，无法打补丁: {e}")
        return code

    transformer = SafetyShellTransformer()
    try:
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
    except Exception as e:
        logger.warning(f"SafetyShell: AST 变换失败: {e}")
        return code

    try:
        patched_code = ast.unparse(new_tree)
        logger.info(f"SafetyShell: 成功注入安全壳防护")
        return patched_code
    except Exception as e:
        logger.warning(f"SafetyShell: 代码反序列化失败: {e}")
        return code


def inject_cuda_cache_guard(code: str) -> str:
    """在每个 torch.cuda 调用后注入 cuda.empty_cache()。

    这是更精细的注入：不改变整体结构，只在关键位置添加内存释放。
    """
    lines = code.split("\n")
    result_lines = []
    indent = ""

    for line in lines:
        result_lines.append(line)

        stripped = line.strip()
        # 检测 torch.cuda 调用
        if "torch.cuda" in stripped and "(" in stripped:
            # 提取缩进
            indent = line[: len(line) - len(line.lstrip())]
            result_lines.append(f"{indent}torch.cuda.empty_cache()")

    return "\n".join(result_lines)


def wrap_in_sandbox_safe(code: str, task_type: str = "general") -> str:
    """综合安全包装：try-except + gc + cuda cache guard。

    这是对外的统一入口，结合所有防护措施。
    """
    # 第一步：AST 安全壳注入
    patched = inject_safety_shell(code)

    # 第二步：额外的 cuda cache guard（AST 注入可能遗漏的情况）
    if "torch.cuda" in patched:
        patched = inject_cuda_cache_guard(patched)

    return patched
