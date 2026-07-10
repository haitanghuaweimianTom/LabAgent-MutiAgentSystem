"""Debugger Agent — 智能代码修复

比简单的错误分类更智能：分析完整错误栈、结合代码上下文和文档、多轮反思修复。
区分"代码逻辑错误"vs"环境/依赖问题"vs"数据问题"。
"""

import logging
import traceback
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)

DEBUGGER_SYSTEM = r"""你是一个专业的Python调试专家。你的任务是分析代码执行错误并提供精准的修复方案。

【分析流程】
1. 阅读完整错误栈（Traceback），定位错误发生的具体行号和函数
2. 分析错误类型和原因（不是猜测，是基于错误信息的逻辑推理）
3. 检查相关代码上下文（错误行前后的代码）
4. 提出具体的修复方案（直接可执行的代码修改，不是泛泛建议）

【错误分类】
- 代码逻辑错误：IndexError, KeyError, TypeError, ValueError, AttributeError, NameError
- 数据问题：FileNotFoundError, KeyError(列名), ShapeMismatch, NaN/Inf
- 环境/依赖问题：ImportError, ModuleNotFoundError, OSError
- 运行时资源问题：MemoryError, TimeoutError

【输出格式】
严格返回JSON：
{
    "error_type": "logic_error|data_issue|env_issue|resource_issue",
    "root_cause": "错误根本原因（一句话）",
    "fix": "具体的代码修复方案（可直接应用的diff或替换代码）",
    "explanation": "为什么会出这个错，修复后为什么能正常工作",
    "prevention": "如何避免同类错误（可选）"
}
"""


@AgentFactory.register("debugger_agent")
class DebuggerAgent(BaseAgent):
    name = "debugger_agent"
    label = "调试专家"
    description = "分析代码错误栈，提供精准修复方案"
    default_model = ""

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """分析代码错误并提供修复方案

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
        error_tb = task_input.get("error_traceback", "")
        file_path = task_input.get("file_path", "")
        attempt = task_input.get("attempt", 1)

        if not code or not error_tb:
            return {"error_type": "unknown", "root_cause": "缺少代码或错误信息", "fix": ""}

        # 构建分析提示
        user_content = f"""## 出错的代码
```python
{code[:4000]}
```

## 完整错误栈
```
{error_tb[-3000:]}
```

## 当前是第 {attempt} 次尝试
{"如果这是第3次尝试，请考虑更根本的重构方案。" if attempt >= 3 else ""}

请分析错误原因并提供修复方案。"""

        messages = [
            {"role": "system", "content": DEBUGGER_SYSTEM},
            {"role": "user", "content": user_content},
        ]

        try:
            response = await self.call_llm(messages=messages, temperature=0.2)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            parsed = self._extract_json(content)

            return {
                "error_type": parsed.get("error_type", "unknown"),
                "root_cause": parsed.get("root_cause", ""),
                "fix": parsed.get("fix", ""),
                "explanation": parsed.get("explanation", ""),
                "prevention": parsed.get("prevention", ""),
            }
        except Exception as e:
            logger.warning(f"[DebuggerAgent] 分析失败: {e}")
            return {
                "error_type": "unknown",
                "root_cause": f"调试分析异常: {e}",
                "fix": "",
                "explanation": "",
                "prevention": "",
            }


def classify_error(traceback_str: str) -> str:
    """快速错误分类（不调用LLM，基于规则）

    Returns:
        错误类型: "logic" | "data" | "env" | "resource" | "unknown"
    """
    tb_lower = traceback_str.lower()

    # 环境/依赖问题
    if any(kw in tb_lower for kw in ["importerror", "modulenotfounderror", "no module named"]):
        return "env"

    # 数据问题
    if any(kw in tb_lower for kw in ["filenotfounderror", "no such file", "column", "keyerror"]):
        return "data"
    if "shape mismatch" in tb_lower or "shape" in tb_lower:
        return "data"

    # 资源问题
    if any(kw in tb_lower for kw in ["memoryerror", "out of memory", "timeout"]):
        return "resource"

    # 代码逻辑错误
    if any(kw in tb_lower for kw in [
        "indexerror", "typeerror", "valueerror", "attributeerror",
        "nameerror", "zerodivisionerror", "stopiteration",
    ]):
        return "logic"

    return "unknown"
