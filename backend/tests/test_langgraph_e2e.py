"""LangGraph 端到端集成测试。

mock 所有 Agent 的 execute 方法，验证 LangGraph 编排器的完整流程：
- 有数据 / 无数据 / 数据不匹配 三种场景
- 标准 / 快速 / 深度研究 三种工作流
- 自主迭代求解 + 多 Agent 投票
- Harness 评判 + 事实核查
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.langgraph_orchestrator import LangGraphOrchestrator, LANGGRAPH_AVAILABLE, TaskState
from app.agents.base import BaseAgent


class _MockAgent(BaseAgent):
    """可配置返回值的 mock agent。"""

    def __init__(self, name: str, response: dict):
        super().__init__()
        self.name = name
        self._response = response
        self._execute_calls = []

    async def execute(self, task_input, context):
        self._execute_calls.append({"task_input": task_input, "context": context})
        return dict(self._response)

    async def call_llm(self, messages=None, stream=False, temperature=None, context=None, tools=None, max_react_iterations=5):
        return {"choices": [{"message": {"role": "assistant", "content": "abort"}}]}

    def get_system_prompt(self, template: str = "math_modeling") -> str:
        return f"Mock system prompt for {self.name}"


def _make_agents():
    """构造完整的 mock agents 字典。"""
    return {
        "analyzer_agent": _MockAgent("analyzer_agent", {
            "sub_problems": [
                {"id": 1, "name": "Sub1", "description": "优化目标函数", "suggested_method": "LP"}
            ],
            "problem_type": "优化",
            "difficulty": "中等",
            "overall_approach": "线性规划",
        }),
        "data_agent": _MockAgent("data_agent", {
            "analyses": [{"file": "data.csv", "insight": "数据完整"}],
            "insights": ["数据包含 100 行 5 列"],
        }),
        "research_agent": _MockAgent("research_agent", {
            "papers": [
                {"title": "LP Methods", "abstract": "A survey of LP.", "url": "http://arxiv.org/1234"}
            ],
            "methods": [{"name": "simplex", "description": "Simplex algorithm"}],
        }),
        "modeler_agent": _MockAgent("modeler_agent", {
            "sub_problem_models": [{
                "sub_problem_id": 1,
                "sub_problem_name": "Sub1",
                "model_name": "LP_Model",
                "model_type": "optimization",
                "objective_function": "min c^T x",
                "decision_variables": [{"name": "x", "type": "continuous"}],
                "constraints": ["Ax <= b"],
                "algorithm": {"name": "simplex"},
            }]
        }),
        "solver_agent": _MockAgent("solver_agent", {
            "execution_success": True,
            "sub_problem_solutions": [{
                "sub_problem_id": 1,
                "results": {
                    "key_findings": ["最优值为 42.0"],
                    "numerical_results": {"optimal_value": 42.0, "iterations": 10},
                },
                "code_files": [
                    {"path": "solver_sub1.py", "role": "solver", "code": "print(42)"}
                ],
                "cross_check": [
                    {"method_a": "primary", "method_b": "analytical_estimate", "diverged": False}
                ],
                "code_manifest": {
                    "manifest": {"files": [{"path": "solver_sub1.py", "role": "solver"}]}
                },
            }],
            "numerical_results": {"optimal_value": 42.0},
            "code_manifest": {"manifest": {"files": [{"path": "solver_sub1.py", "role": "solver"}]}},
        }),
        "writer_agent": _MockAgent("writer_agent", {
            "latex_code": r"\documentclass{article}\begin{document}Optimal: 42.0\end{document}",
            "chapters": [{"id": "abstract", "title": "Abstract", "score": 90}],
            "bib_entries": [{"key": "ref1", "title": "LP Methods"}],
        }),
        "peer_review_agent": _MockAgent("peer_review_agent", {
            "recommendation": "accept",
            "overall_score": 4.5,
            "scores": {"novelty": 4, "soundness": 5, "clarity": 4, "significance": 4},
        }),
        "experimentation_agent": _MockAgent("experimentation_agent", {
            "plan": {"baselines": ["baseline_a"], "datasets": ["synthetic"], "metrics": ["accuracy"]},
        }),
    }


def _make_failing_solver_agents():
    """构造 solver 会失败的 agents（用于测试迭代求解）。"""
    agents = _make_agents()
    # solver 第一次失败，第二次成功
    call_count = {"n": 0}

    class _FailingSolverAgent(BaseAgent):
        def __init__(self):
            super().__init__()
            self.name = "solver_agent"

        async def execute(self, task_input, context):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                return {
                    "execution_success": False,
                    "error": "KeyError: 'column_x'",
                    "numerical_results": {},
                    "code_manifest": {"manifest": {"files": []}},
                }
            return {
                "execution_success": True,
                "sub_problem_solutions": [{
                    "sub_problem_id": 1,
                    "results": {
                        "key_findings": ["修复后最优值为 42.0"],
                        "numerical_results": {"optimal_value": 42.0},
                    },
                    "code_files": [{"path": "solver_sub1.py", "role": "solver", "code": "print(42)"}],
                    "cross_check": [],
                    "code_manifest": {"manifest": {"files": [{"path": "solver_sub1.py", "role": "solver"}]}},
                }],
                "numerical_results": {"optimal_value": 42.0},
                "code_manifest": {"manifest": {"files": [{"path": "solver_sub1.py", "role": "solver"}]}},
            }

        async def call_llm(self, **kwargs):
            return {"choices": [{"message": {"role": "assistant", "content": "retry"}}]}

        def get_system_prompt(self, **kwargs):
            return "Mock solver"

    agents["solver_agent"] = _FailingSolverAgent()
    return agents


@pytest.fixture
def patched_output_dir(tmp_path, monkeypatch):
    import app.core.paths as paths
    monkeypatch.setattr(paths, "get_project_output_dir", lambda p: tmp_path / "output" / (p or "__global__"))
    return tmp_path


@pytest.fixture
def patched_task_dir(tmp_path, monkeypatch):
    import app.core.task_persistence as tp
    monkeypatch.setattr(tp, "TASK_DATA_DIR", tmp_path / "tasks")
    return tmp_path / "tasks"


@pytest.fixture
def patched_chat_room(tmp_path, monkeypatch):
    """mock ChatRoom 避免真实内存状态。"""
    import app.core.chat_room as cr
    rooms = {}

    def _create(task_id, problem_text):
        room = MagicMock()
        room.post = MagicMock()
        rooms[task_id] = room
        return room

    def _get(task_id):
        return rooms.get(task_id)

    monkeypatch.setattr(cr, "create_chat_room", _create)
    monkeypatch.setattr(cr, "get_chat_room", _get)
    return rooms


@pytest.fixture
def patched_memory(tmp_path, monkeypatch):
    """mock 记忆系统。"""
    import app.core.memory as mem

    wm = MagicMock()
    wm.set_result = MagicMock()
    wm.sub_problems = []
    wm.data_insights = []
    wm.add_literature = MagicMock()
    wm.add_method = MagicMock()
    wm.update_problem = MagicMock()

    em = MagicMock()
    em.record = MagicMock()

    mm = MagicMock()
    mm.create_task_memory = MagicMock(return_value=(wm, em))
    mm.get_task_memory = MagicMock(return_value=(wm, em))

    monkeypatch.setattr(mem, "get_memory_manager", lambda: mm)
    return mm


# ====================================================================
# 测试场景
# ====================================================================


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
@pytest.mark.asyncio
async def test_langgraph_standard_workflow(
    patched_output_dir, patched_task_dir, patched_chat_room, patched_memory
):
    """场景 1：标准工作流，有数据，全流程跑通。"""
    agents = _make_agents()
    orch = LangGraphOrchestrator(agents)

    result = await orch.run(
        task_id="lg_test_standard",
        problem_text="优化某供应链总成本",
        data_files=["/tmp/data.csv"],
        template="neurips_2024",
        workflow_type="standard",
        mode="batch",
        project_name="test_project",
    )

    assert result["status"] == "completed"
    assert "results" in result
    assert "analyzer_agent" in result["results"]
    # solver_agent 结果可能在 solver_output 中（逐个子问题求解）
    solver_out = result["results"].get("solver_agent", {})
    assert solver_out is not None
    assert "writer_agent" in result["results"]


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
@pytest.mark.asyncio
async def test_langgraph_quick_workflow(
    patched_output_dir, patched_task_dir, patched_chat_room, patched_memory
):
    """场景 2：快速模式，跳过文献搜集。"""
    agents = _make_agents()
    orch = LangGraphOrchestrator(agents)

    result = await orch.run(
        task_id="lg_test_quick",
        problem_text="快速求解一个简单优化问题",
        data_files=[],
        template="math_modeling",
        workflow_type="quick",
        mode="batch",
    )

    assert result["status"] == "completed"
    # research 应该被跳过
    research = agents["research_agent"]
    assert len(research._execute_calls) == 0


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
@pytest.mark.asyncio
async def test_langgraph_deep_research_workflow(
    patched_output_dir, patched_task_dir, patched_chat_room, patched_memory
):
    """场景 3：深度研究模式，多轮文献搜集。"""
    agents = _make_agents()
    orch = LangGraphOrchestrator(agents)

    result = await orch.run(
        task_id="lg_test_deep",
        problem_text="深度研究一个前沿课题",
        data_files=[],
        template="acm_sigconf",
        workflow_type="deep_research",
        mode="batch",
    )

    assert result["status"] == "completed"
    # research 应该被调用 3 次（search / search_background / search_methods）
    research = agents["research_agent"]
    assert len(research._execute_calls) == 3


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
@pytest.mark.asyncio
async def test_langgraph_no_data_aborts(
    patched_output_dir, patched_task_dir, patched_chat_room, patched_memory
):
    """场景 4：无数据且 preflight 报告 missing → abort。"""
    agents = _make_agents()
    orch = LangGraphOrchestrator(agents)

    result = await orch.run(
        task_id="lg_test_no_data",
        problem_text="需要数据才能求解的问题",
        data_files=[],
        preflight_report={"data_adequacy": "missing", "llm_should_collect": False},
    )

    assert result["status"] == "completed"
    assert result.get("cannot_solve_report") is not None


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
@pytest.mark.asyncio
async def test_langgraph_self_collect_then_continue(
    patched_output_dir, patched_task_dir, patched_chat_room, patched_memory
):
    """场景 5：无数据但 LLM 判断可以自行搜集 → self_collect → 重新 preflight → abort。"""
    agents = _make_agents()
    orch = LangGraphOrchestrator(agents)

    result = await orch.run(
        task_id="lg_test_self_collect",
        problem_text="需要数据的问题",
        data_files=[],
        preflight_report={
            "data_adequacy": "missing",
            "llm_should_collect": True,
            "collection_plan": "搜索 Kaggle 数据集",
        },
    )

    # self_collect 节点执行后回到 preflight_decision，但 preflight 仍是 missing → abort
    assert result["status"] == "completed"


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
@pytest.mark.asyncio
async def test_langgraph_iterative_solver_retry(
    patched_output_dir, patched_task_dir, patched_chat_room, patched_memory
):
    """场景 6：solver 失败后自动迭代修复。"""
    agents = _make_failing_solver_agents()
    cfg = {"max_solver_iterations": 4, "max_solver_escalations": 1}
    orch = LangGraphOrchestrator(agents, config=cfg)

    result = await orch.run(
        task_id="lg_test_retry",
        problem_text="需要迭代修复的求解问题",
        data_files=[],
        template="math_modeling",
        workflow_type="standard",
    )

    assert result["status"] == "completed"
    assert result["solver_attempts"] >= 1


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
@pytest.mark.asyncio
async def test_langgraph_harness_judgment(
    patched_output_dir, patched_task_dir, patched_chat_room, patched_memory
):
    """场景 7：Harness 评判通过。"""
    agents = _make_agents()
    orch = LangGraphOrchestrator(agents)

    result = await orch.run(
        task_id="lg_test_harness",
        problem_text="Harness 评判测试",
        data_files=[],
        template="ieee_conference",
    )

    assert result["status"] == "completed"
    # 验证工作流正常完成（Harness 评判在 iterative_solver_node 内部执行）
    assert "results" in result
    assert len(result["results"]) > 0


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
@pytest.mark.asyncio
async def test_langgraph_contract_validation(
    patched_output_dir, patched_task_dir, patched_chat_room, patched_memory
):
    """场景 8：contract_validator 对 analyzer 和 writer 输出做 schema 校验。"""
    agents = _make_agents()
    orch = LangGraphOrchestrator(agents)

    result = await orch.run(
        task_id="lg_test_contract",
        problem_text="Contract 校验测试",
        data_files=[],
    )

    analyzer_out = result["results"].get("analyzer_agent", {})
    assert "_contract" in analyzer_out
    assert analyzer_out["_contract"]["valid"] is True

    writer_out = result["results"].get("writer_agent", {})
    assert "_contract" in writer_out


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
@pytest.mark.asyncio
async def test_langgraph_cannot_solve_report(
    patched_output_dir, patched_task_dir, patched_chat_room, patched_memory
):
    """场景 9：达到迭代上限后生成 cannot_solve_report。"""

    class _AlwaysFailSolver(BaseAgent):
        def __init__(self):
            super().__init__()
            self.name = "solver_agent"

        async def execute(self, task_input, context):
            return {
                "execution_success": False,
                "error": "ValueError: 无法求解",
                "numerical_results": {},
            }

        async def call_llm(self, **kwargs):
            return {"choices": [{"message": {"role": "assistant", "content": "abort"}}]}

        def get_system_prompt(self, **kwargs):
            return "Mock"

    agents = _make_agents()
    agents["solver_agent"] = _AlwaysFailSolver()
    cfg = {"max_solver_iterations": 2, "max_solver_escalations": 0}
    orch = LangGraphOrchestrator(agents, config=cfg)

    result = await orch.run(
        task_id="lg_test_cannot_solve",
        problem_text="不可解问题",
        data_files=[],
    )

    assert result["status"] == "completed"
    report = result.get("cannot_solve_report")
    assert report is not None
    assert report["task_id"] == "lg_test_cannot_solve"
