"""Bug Finder Agent — 代码错误自动诊断与分类

使用微调的小模型（Qwen2.5-Coder-1.5B）进行本地推理：
- 错误类型分类（7 类）
- 错误行定位（行级）
- 根因分析
- 结构化修复建议

与 DebuggerAgent 的区别：
- DebuggerAgent 使用大模型 API，成本高、延迟高
- Bug Finder Agent 使用本地小模型，零 API 成本、延迟 <100ms
- Bug Finder 输出结构化诊断，给大模型提供精准修复信息

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

# 错误类型定义
ERROR_TYPES = [
    "OOM",                # 显存不足
    "SyntaxError",        # 语法错误
    "ShapeMismatch",      # 张量维度不匹配
    "LogicError",         # 逻辑错误（IndexError, KeyError, TypeError...）
    "DependencyMissing",  # 依赖缺失
    "DataFormat",         # 数据格式错误
    "Timeout",            # 超时
]

BUG_FINDER_SYSTEM_PROMPT = """你是一个专业的代码错误诊断专家。你的任务是分析代码执行错误，给出结构化的诊断结果。

【输出格式】
严格返回 JSON，不要有任何其他文字：
{
    "error_type": "错误类型（7选1）",
    "error_location": "错误发生的位置（行号或函数名）",
    "root_cause": "错误根本原因（一句话）",
    "fix_suggestion": "具体的修复方案（可直接应用）",
    "confidence": 0.87
}

【错误类型】
- OOM：显存不足（CUDA out of memory）
- SyntaxError：语法错误（SyntaxError, IndentationError）
- ShapeMismatch：张量维度不匹配
- LogicError：逻辑错误（IndexError, KeyError, TypeError, ValueError, AttributeError）
- DependencyMissing：依赖缺失（ImportError, ModuleNotFoundError）
- DataFormat：数据格式错误（FileNotFoundError, JSONDecodeError）
- Timeout：超时（TimeoutError）
"""


@AgentFactory.register("bug_finder_agent")
class BugFinderAgent(BaseAgent):
    """Bug Finder Agent — 使用本地小模型进行代码错误诊断"""

    name = "bug_finder_agent"
    label = "代码诊断专家"
    description = "使用本地小模型分析代码错误，输出结构化诊断结果"
    default_model = ""  # 使用本地模型，不需要 API

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model = None
        self._tokenizer = None
        self._model_path = None
        self._load_model()

    def get_system_prompt(self) -> str:
        """返回系统提示词"""
        return BUG_FINDER_SYSTEM_PROMPT

    def _load_model(self):
        """加载本地模型"""
        # 查找模型路径
        possible_paths = [
            Path("ml/checkpoints/bug_finder"),
            Path("backend/data/models/bug_finder"),
            Path("models/bug_finder"),
        ]

        for path in possible_paths:
            if path.exists():
                self._model_path = str(path)
                break

        if not self._model_path:
            logger.warning("Bug Finder 模型未找到，将使用规则引擎回退")
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info(f"加载 Bug Finder 模型: {self._model_path}")
            self._tokenizer = AutoTokenizer.from_pretrained(
                self._model_path, trust_remote_code=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self._model_path, trust_remote_code=True
            )

            if torch.cuda.is_available():
                self._model = self._model.cuda()
                logger.info("Bug Finder 模型已加载到 GPU")
            else:
                logger.info("Bug Finder 模型已加载到 CPU")

        except Exception as e:
            logger.error(f"加载 Bug Finder 模型失败: {e}")
            self._model = None

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

        # 尝试使用本地模型
        if self._model is not None:
            result = self._diagnose_with_model(code, traceback_str)
        else:
            # 回退到规则引擎
            result = self._diagnose_with_rules(code, traceback_str)

        latency_ms = (time.time() - start_time) * 1000
        result["latency_ms"] = latency_ms
        result["model_used"] = "local" if self._model is not None else "rules"

        logger.info(f"Bug Finder 诊断完成: {result['error_type']} "
                   f"(confidence={result['confidence']:.2f}, {latency_ms:.0f}ms)")

        return result

    def _diagnose_with_model(self, code: str, traceback_str: str) -> Dict[str, Any]:
        """使用本地模型进行诊断"""
        import torch

        # 构建 prompt
        prompt = f"""分析以下代码执行错误，给出错误类型、定位、原因和修复建议。

代码：
{code}

Traceback：
{traceback_str}

请返回 JSON 格式的诊断结果。"""

        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=2048,
        )

        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.1,
                do_sample=False,
            )

        response = self._tokenizer.decode(outputs[0], skip_special_tokens=True)

        # 解析 JSON
        try:
            # 提取 JSON 部分
            json_match = re.search(r'\{[^{}]*"error_type"[^{}]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
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

        # ShapeMismatch
        if any(kw in traceback_lower for kw in ["shape", "dimension", "size mismatch", "cannot be multiplied"]):
            return "ShapeMismatch"

        # DependencyMissing
        if any(kw in traceback_lower for kw in ["importerror", "modulenotfounderror", "no module named"]):
            return "DependencyMissing"

        # DataFormat
        if any(kw in traceback_lower for kw in ["filenotfounderror", "jsondecodeerror", "parsererror"]):
            return "DataFormat"

        # Timeout
        if any(kw in traceback_lower for kw in ["timeouterror", "timed out"]):
            return "Timeout"

        # LogicError (默认)
        return "LogicError"

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
            "ShapeMismatch": "检查 tensor 维度；打印 shape 调试；确保 matmul/conv 操作的输入输出维度匹配",
            "LogicError": "检查索引/键是否在有效范围内；添加边界检查；使用 try-except 捕获异常",
            "DependencyMissing": "安装缺失的包：pip install <package_name>；检查 import 语句；使用虚拟环境",
            "DataFormat": "检查文件路径是否正确；验证数据格式（CSV/JSON/Excel）；添加文件存在性检查",
            "Timeout": "优化算法复杂度；增加超时时间；检查是否有死循环；使用更高效的数据结构",
        }

        return suggestions.get(error_type, "检查错误信息，定位问题代码行并修复")


def create_bug_finder_agent() -> BugFinderAgent:
    """创建 Bug Finder Agent 实例"""
    return BugFinderAgent()
