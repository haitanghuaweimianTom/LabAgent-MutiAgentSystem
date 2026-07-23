"""Bug Finder Agent — 代码错误自动诊断与分类

使用微调的小模型（Qwen2.5-Coder-1.5B）进行本地推理：
- 错误类型分类（11 类）
- 错误行定位（行级）
- 根因分析
- 结构化修复建议

与 DebuggerAgent 的区别：
- DebuggerAgent 使用大模型 API，成本高、延迟高
- Bug Finder Agent 使用本地小模型，零 API 成本、延迟 <100ms
- Bug Finder 输出结构化诊断，给大模型提供精准修复信息

架构设计：
- 通过 API 接口调用本地模型（支持 Ollama/vLLM）
- 复用 BaseAgent.call_llm() 统一接口
- 无本地模型时 fallback 到规则引擎

集成位置：
- solver_agent.py 的失败路径中调用 Bug Finder
- Bug Finder 输出注入大模型修复 prompt
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)

# 错误类型定义（11类，与训练数据一致）
ERROR_TYPES = [
    "IndexError",        # 索引越界
    "KeyError",          # 键不存在
    "ValueError",        # 值错误
    "ZeroDivisionError", # 除零错误
    "TypeError",         # 类型错误
    "AttributeError",    # 属性错误
    "FileNotFoundError", # 文件未找到
    "ImportError",       # 导入错误
    "RuntimeError",      # 运行时错误
    "LogicError",        # 逻辑错误
    "OOM",               # 显存不足
    "SyntaxError",       # 语法错误
    "Timeout",           # 超时
]

BUG_FINDER_SYSTEM_PROMPT = """你是一个专业的代码错误诊断专家。你的任务是分析代码执行错误，给出结构化的诊断结果。

【输出格式】
严格返回 JSON，不要有任何其他文字：
{
    "error_type": "错误类型（从以下类型中选择）",
    "error_location": "错误发生的位置（行号或函数名）",
    "root_cause": "错误根本原因（一句话）",
    "fix_suggestion": "具体的修复方案（可直接应用）",
    "confidence": 0.87
}

【错误类型】
- IndexError：索引越界（list index out of range, index out of bounds）
- KeyError：键不存在（KeyError: 'xxx'）
- ValueError：值错误（ValueError: xxx）
- ZeroDivisionError：除零错误（division by zero, modulo by zero）
- TypeError：类型错误（TypeError: xxx）
- AttributeError：属性错误（'xxx' object has no attribute 'yyy'）
- FileNotFoundError：文件未找到（No such file or directory）
- ImportError：导入错误（No module named 'xxx'）
- RuntimeError：运行时错误（RuntimeError: xxx）
- LogicError：逻辑错误（NotFittedError, RecursionError, 设备不匹配等）
- OOM：显存不足（CUDA out of memory）
- SyntaxError：语法错误（SyntaxError, IndentationError）
- Timeout：超时（TimeoutError, timed out）
"""


@AgentFactory.register("bug_finder_agent")
class BugFinderAgent(BaseAgent):
    """Bug Finder Agent — 通过 API 调用本地/远程模型进行代码错误诊断"""

    name = "bug_finder_agent"
    label = "代码诊断专家"
    description = "通过 API 调用模型分析代码错误，输出结构化诊断结果"
    default_model = "bug-finder-local"  # 本地微调模型

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model_loaded = False
        self._check_model_availability()

    def get_system_prompt(self) -> str:
        """返回系统提示词"""
        return BUG_FINDER_SYSTEM_PROMPT

    def _check_model_availability(self):
        """检查模型是否可用"""
        # 检查是否有本地模型配置
        possible_paths = [
            Path("ml/checkpoints/bug_finder"),
            Path("backend/data/models/bug_finder"),
            Path("models/bug_finder"),
        ]

        for path in possible_paths:
            if path.exists():
                self._model_loaded = True
                logger.info(f"Bug Finder 模型可用: {path}")
                return

        logger.warning("Bug Finder 模型未找到，将使用规则引擎回退")

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Bug Finder 诊断

        Args:
            task_input: {
                "code": str,           # 出错的代码
                "error_traceback": str, # 完整错误栈
                "file_path": str,       # 代码文件路径（可选）
                "attempt": int,         # 当前是第几次尝试
            }
            context: 上下文信息
        """
        code = task_input.get("code", "")
        traceback_str = task_input.get("error_traceback", "")
        attempt = task_input.get("attempt", 1)

        logger.info(f"Bug Finder 开始诊断 (attempt={attempt})")

        start_time = time.time()

        # 优先尝试通过 API 调用模型
        if self._model_loaded:
            try:
                result = await self._diagnose_with_api(code, traceback_str, context)
            except Exception as e:
                logger.warning(f"API 调用失败，回退到规则引擎: {e}")
                result = self._diagnose_with_rules(code, traceback_str)
        else:
            # 回退到规则引擎
            result = self._diagnose_with_rules(code, traceback_str)

        latency_ms = (time.time() - start_time) * 1000
        result["latency_ms"] = latency_ms
        result["model_used"] = "api" if self._model_loaded else "rules"

        logger.info(f"Bug Finder 诊断完成: {result['error_type']} "
                   f"(confidence={result['confidence']:.2f}, {latency_ms:.0f}ms)")

        return result

    async def _diagnose_with_api(self, code: str, traceback_str: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """通过 API 调用模型进行诊断"""
        # 构建用户消息
        user_prompt = f"""分析以下代码执行错误，给出错误类型、定位、原因和修复建议。

代码：
{code}

Traceback：
{traceback_str}

请返回 JSON 格式的诊断结果。"""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": user_prompt},
        ]

        # 使用 BaseAgent.call_llm() 统一接口
        response = await self.call_llm(
            messages=messages,
            temperature=0.1,
            context=context,
        )

        # 解析响应
        response_text = response.get("content", "") if isinstance(response, dict) else str(response)

        # 提取 JSON
        json_match = re.search(r'\{[^{}]*"error_type"[^{}]*\}', response_text)
        if json_match:
            try:
                result = json.loads(json_match.group())
                # 应用标签映射（与评估脚本一致）
                result = self._apply_label_mapping(result)
                # 验证字段
                if "error_type" not in result:
                    result["error_type"] = "Other"
                if "confidence" not in result:
                    result["confidence"] = 0.7
                return result
            except json.JSONDecodeError:
                pass

        # 解析失败，使用规则引擎
        return self._diagnose_with_rules(code, traceback_str)

    def _apply_label_mapping(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """应用标签映射（与评估脚本一致）"""
        error_type = result.get("error_type", "Other")

        # 标签映射
        LABEL_MAP = {
            "ModuleNotFoundError": "ImportError",
            "torch.cuda.OutOfMemoryError": "OOM",
            "cuda.OutOfMemoryError": "OOM",
            "OutOfMemoryError": "OOM",
            "CUDA Out of Memory Error": "OOM",
            "CUDA out of memory": "OOM",
            "NotFittedError": "LogicError",
            "RecursionError": "LogicError",
        }

        # 中文标签映射
        CN_MAP = {
            "索引错误": "IndexError",
            "列表索引越界错误": "IndexError",
            "索引出界错误": "IndexError",
            "形状不匹配": "ValueError",
            "键错误": "KeyError",
            "类型错误": "TypeError",
            "值错误": "ValueError",
            "文件未找到错误": "FileNotFoundError",
            "属性错误": "AttributeError",
            "导入错误": "ImportError",
            "运行时错误": "RuntimeError",
            "语法错误": "SyntaxError",
            "CUDA内存不足错误": "OOM",
            "GPU显存不足": "OOM",
        }

        if error_type in LABEL_MAP:
            error_type = LABEL_MAP[error_type]

        if error_type in CN_MAP:
            error_type = CN_MAP[error_type]

        # 处理包含CUDA的情况
        if "CUDA" in error_type and "memory" in error_type.lower():
            error_type = "OOM"

        result["error_type"] = error_type
        return result

    def _diagnose_with_rules(self, code: str, traceback_str: str) -> Dict[str, Any]:
        """使用规则引擎进行诊断（回退方案）"""
        # 识别错误类型
        error_type = self._classify_error(traceback_str)

        # 提取错误行
        error_location = self._extract_error_line(traceback_str)

        # 生成根因描述
        root_cause = self._extract_root_cause(traceback_str, error_type)

        # 生成修复建议
        fix_suggestion = self._generate_fix_suggestion(error_type, traceback_str)

        return {
            "error_type": error_type,
            "error_location": error_location,
            "root_cause": root_cause,
            "fix_suggestion": fix_suggestion,
            "confidence": 0.75,
        }

    def _classify_error(self, traceback_str: str) -> str:
        """根据 traceback 识别错误类型"""
        traceback_lower = traceback_str.lower()

        # OOM
        if any(kw in traceback_lower for kw in ["out of memory", "cuda out of memory", "oom"]):
            return "OOM"

        # SyntaxError
        if any(kw in traceback_lower for kw in ["syntaxerror", "indentationerror", "taberror"]):
            return "SyntaxError"

        # ImportError
        if any(kw in traceback_lower for kw in ["importerror", "modulenotfounderror", "no module named"]):
            return "ImportError"

        # FileNotFoundError
        if any(kw in traceback_lower for kw in ["filenotfounderror", "no such file"]):
            return "FileNotFoundError"

        # ZeroDivisionError
        if any(kw in traceback_lower for kw in ["zerodivisionerror", "division by zero", "modulo by zero"]):
            return "ZeroDivisionError"

        # IndexError
        if any(kw in traceback_lower for kw in ["indexerror", "index out of range", "index out of bounds"]):
            return "IndexError"

        # KeyError
        if "keyerror" in traceback_lower:
            return "KeyError"

        # TypeError
        if "typeerror" in traceback_lower:
            return "TypeError"

        # ValueError
        if "valueerror" in traceback_lower:
            return "ValueError"

        # AttributeError
        if "attributeerror" in traceback_lower:
            return "AttributeError"

        # LogicError
        if any(kw in traceback_lower for kw in ["notfittederror", "recursionerror", "maximum recursion depth"]):
            return "LogicError"

        # Timeout
        if any(kw in traceback_lower for kw in ["timeouterror", "timed out"]):
            return "Timeout"

        # RuntimeError (默认)
        return "RuntimeError"

    def _extract_error_line(self, traceback_str: str) -> str:
        """提取错误行号"""
        match = re.search(r"line (\d+)", traceback_str)
        if match:
            return f"line {match.group(1)}"

        # 尝试提取文件名和行号
        match = re.search(r'File "(.+?)", line (\d+)', traceback_str)
        if match:
            return f"{match.group(1)}:{match.group(2)}"

        return "unknown"

    def _extract_root_cause(self, traceback_str: str, error_type: str) -> str:
        """提取根因描述"""
        # 取最后一行（通常是错误信息）
        lines = traceback_str.strip().split("\n")
        last_line = lines[-1] if lines else ""

        # 清理
        last_line = last_line.strip()
        if len(last_line) > 200:
            last_line = last_line[:200] + "..."

        return last_line

    def _generate_fix_suggestion(self, error_type: str, traceback_str: str) -> str:
        """生成修复建议"""
        suggestions = {
            "OOM": "减少 batch_size 或使用 gradient_accumulation；添加 torch.cuda.empty_cache()；检查是否有内存泄漏",
            "SyntaxError": "检查代码缩进和语法；确保括号、引号匹配；检查 Python 版本兼容性",
            "ImportError": "安装缺失的包：pip install <package_name>；检查 import 语句；使用虚拟环境",
            "FileNotFoundError": "检查文件路径是否正确；验证文件是否存在；使用 os.path.exists() 检查",
            "ZeroDivisionError": "检查除数是否为零；添加边界条件判断；使用 try-except 捕获异常",
            "IndexError": "检查索引是否在有效范围内；添加边界检查；使用 len() 获取长度",
            "KeyError": "检查键是否存在；使用 dict.get() 方法；使用 try-except 捕获异常",
            "TypeError": "检查变量类型是否正确；使用 type() 或 isinstance() 验证；进行类型转换",
            "ValueError": "检查参数值是否在有效范围内；添加输入验证；使用 try-except 捕获异常",
            "AttributeError": "检查对象是否有该属性/方法；使用 dir() 查看可用属性；检查拼写",
            "RuntimeError": "检查运行时条件是否满足；查看详细错误信息；检查设备兼容性",
            "LogicError": "检查程序逻辑；添加边界条件；使用调试工具定位问题",
            "Timeout": "优化算法复杂度；增加超时时间；检查是否有死循环；使用更高效的数据结构",
        }

        return suggestions.get(error_type, "检查错误信息，定位问题代码行并修复")


def create_bug_finder_agent() -> BugFinderAgent:
    """创建 Bug Finder Agent 实例"""
    return BugFinderAgent()
