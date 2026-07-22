"""Bug Finder Agent 集成指南

本文件展示如何将 Bug Finder Agent 集成到 solver_agent.py 的失败路径中。

集成步骤：
1. 在 solver_agent.py 中导入 BugFinderAgent
2. 在代码执行失败时调用 Bug Finder
3. 将 Bug Finder 的结构化诊断注入大模型修复 prompt
"""
from __future__ import annotations

# === 集成代码示例 ===

# 在 solver_agent.py 的 execute 方法中，代码执行失败时：

async def _handle_execution_failure_with_bug_finder(
    self,
    code: str,
    error_traceback: str,
    attempt: int,
    context: dict,
) -> dict:
    """使用 Bug Finder 辅助修复"""

    # 1. 调用 Bug Finder 获取结构化诊断
    from .bug_finder_agent import BugFinderAgent

    bug_finder = BugFinderAgent()
    diagnosis = await bug_finder.execute(
        task_input={
            "code": code,
            "error_traceback": error_traceback,
            "attempt": attempt,
        },
        context=context,
    )

    # 2. 构建增强的修复 prompt
    fix_prompt = f"""代码执行失败，请根据以下诊断信息修复代码。

【原始代码】
{code}

【错误栈】
{error_traceback}

【Bug Finder 诊断】
- 错误类型：{diagnosis['error_type']}
- 错误位置：{diagnosis['error_location']}
- 根本原因：{diagnosis['root_cause']}
- 修复建议：{diagnosis['fix_suggestion']}
- 置信度：{diagnosis['confidence']:.2f}

请根据诊断结果修复代码。只返回修复后的完整代码，不要有其他文字。"""

    # 3. 调用大模型修复
    fixed_code = await self.call_llm(fix_prompt)

    return {
        "code": fixed_code,
        "diagnosis": diagnosis,
        "attempt": attempt + 1,
    }


# === 在 orchestrator 中注册 Bug Finder ===

# 在 langgraph_orchestrator.py 中：

# 1. 导入
from .bug_finder_agent import BugFinderAgent

# 2. 在 Solver 节点的失败路径中调用
async def solver_node(state: TaskState) -> TaskState:
    """Solver 节点：代码生成与执行"""
    # ... 生成代码并执行 ...

    if execution_failed:
        # 使用 Bug Finder 诊断
        bug_finder = BugFinderAgent()
        diagnosis = await bug_finder.execute({
            "code": generated_code,
            "error_traceback": error_traceback,
        })

        # 将诊断信息注入下一轮 LLM 调用
        state["bug_finder_diagnosis"] = diagnosis

    return state
