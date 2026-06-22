"""CircuitBreaker 集成测试（v5.3.2）。

验证：
1. Orchestrator 捕获 CircuitOpenError 时：
   - 标记 task_step.status = FAILED
   - 聊天室广播友好消息（含 ⛔ 提示 + 建议）
   - 持久化 metadata.status="failed" + error 信息
2. 任务失败后能从前端看到
"""
import asyncio
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    get_breaker,
    remove_breaker,
)


@pytest.fixture
def patched_task_dir(tmp_path, monkeypatch):
    import app.core.paths as paths
    import app.core.task_persistence as tp
    monkeypatch.setattr(paths, "TASK_DATA_DIR", tmp_path)
    monkeypatch.setattr(tp, "TASK_DATA_DIR", tmp_path)
    yield tmp_path


@pytest.mark.asyncio
async def test_orchestrator_circuit_open_marks_task_failed_and_broadcasts(
    patched_task_dir, monkeypatch
):
    """Orchestrator 捕获 CircuitOpenError 时必须：
    1. task_step.status = FAILED
    2. 聊天室广播友好消息
    3. 持久化 metadata.status='failed'
    """
    # 直接调用 Orchestrator._write_paper_and_finish 触发 writer 异常分支
    from app.agents.orchestrator import Orchestrator
    from app.core.task_persistence import save_task_metadata

    # 先建一个 task metadata（模拟正常提交）
    save_task_metadata(
        "task_circuit_test", "测试熔断器", "running", "2026-01-01",
        progress=50, current_step="写作中",
    )

    # 构造最小可用的 Orchestrator（不需要完整 Agent）
    orch = Orchestrator.__new__(Orchestrator)
    orch.agents = {}
    orch.task_history = {"task_circuit_test": []}
    orch._task_phase = {}
    orch._task_pause_data = {}
    orch._current_project_name = None
    orch._task_templates = {}
    orch._task_workflows = {}

    # 注入 CircuitOpenError 让 writer 抛
    from app.agents.orchestrator import TaskStep, TaskStatus
    from datetime import datetime
    from app.core.circuit_breaker import CircuitOpenError

    async def fake_writer_execute(*args, **kwargs):
        raise CircuitOpenError(
            name="task_circuit_test",
            retry_after_sec=120,
            message="10 consecutive failures",
        )

    class FakeWriterAgent:
        name = "writer_agent"
        _knowledge_base_id = None
        async def execute(self, task_input, context):
            return await fake_writer_execute()

    orch.agents["writer_agent"] = FakeWriterAgent()

    # mock ChatRoom
    fake_room = MagicMock()
    fake_room.post = MagicMock()
    fake_chat = {"task_circuit_test": fake_room}
    monkeypatch.setattr("app.core.chat_room.get_chat_room",
                        lambda task_id: fake_chat.get(task_id))

    # mock _save_output_files / _post_agent_result / TaskStep
    from app.agents.orchestrator import TaskStep as RealTaskStep
    from dataclasses import dataclass

    @dataclass
    class FakeTaskStep:
        step_id: str = "phase3_writer"
        agent_name: str = "writer_agent"
        status: TaskStatus = TaskStatus.RUNNING
        started_at: datetime = None
        completed_at: datetime = None
        output_data: dict = None
        error: str = None

    monkeypatch.setattr("app.agents.orchestrator.TaskStep", FakeTaskStep)
    monkeypatch.setattr(Orchestrator, "_save_output_files",
                        lambda self, *a, **kw: {})
    monkeypatch.setattr(Orchestrator, "_post_agent_result",
                        lambda self, *a, **kw: None)
    monkeypatch.setattr(Orchestrator, "_check_pause",
                        lambda self, *a, **kw: None)

    # 触发 CircuitOpenError
    try:
        await orch._write_paper_and_finish(
            task_id="task_circuit_test",
            problem_text="测试熔断器",
            sub_problems=[],
            section_results=[],
            all_results={},
            phase1_results={},
            context_base={"chat_room": fake_room, "use_critique": False},
            project_name="test",
            workflow_type="standard",
        )
    except CircuitOpenError:
        pass  # 预期会抛（task_step.error 已设置）

    # 验证 1: 聊天室广播了友好消息
    posted_messages = [
        call.args[1] if len(call.args) > 1 else call.args[0]
        for call in fake_room.post.call_args_list
    ]
    assert any("⛔" in m and "熔断" in m for m in posted_messages), (
        f"应广播 ⛔ 熔断消息，实际: {posted_messages}"
    )
    assert any("API key" in m or "API" in m for m in posted_messages), (
        f"应提及 API key 异常: {posted_messages}"
    )
    assert any("重新执行" in m for m in posted_messages), (
        f"应给出建议「重新执行」: {posted_messages}"
    )

    # 验证 2: task_step.error 是友好消息
    step = orch.task_history["task_circuit_test"][-1]
    assert step.status == TaskStatus.FAILED, "task_step 应为 FAILED"
    assert "⛔" in (step.error or ""), "task_step.error 应包含 ⛔ 提示"

    # 验证 3: metadata 持久化
    meta = json.loads((patched_task_dir / "task_circuit_test.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed", f"metadata.status 应为 failed，实际 {meta['status']}"
    assert "熔断" in meta.get("error", ""), f"metadata.error 应提及熔断，实际 {meta.get('error')}"
    assert "API key 异常" in meta.get("current_step", ""), (
        f"metadata.current_step 应为'已暂停（API key 异常）'，实际 {meta.get('current_step')}"
    )


@pytest.mark.asyncio
async def test_normal_exception_does_not_trigger_circuit_handling(patched_task_dir, monkeypatch):
    """普通异常（非 CircuitOpenError）不应触发熔断器友好消息，应正常失败。"""
    from app.agents.orchestrator import Orchestrator, TaskStep, TaskStatus
    from datetime import datetime

    from app.core.task_persistence import save_task_metadata
    save_task_metadata(
        "task_normal_fail", "普通失败", "running", "2026-01-01",
        progress=50,
    )

    orch = Orchestrator.__new__(Orchestrator)
    orch.agents = {}
    orch.task_history = {"task_normal_fail": []}
    orch._task_phase = {}
    orch._task_pause_data = {}
    orch._current_project_name = None
    orch._task_templates = {}
    orch._task_workflows = {}

    class FakeWriterAgent:
        name = "writer_agent"
        _knowledge_base_id = None
        async def execute(self, task_input, context):
            raise RuntimeError("普通 LLM 错误（非熔断）")

    orch.agents["writer_agent"] = FakeWriterAgent()

    fake_room = MagicMock()
    fake_room.post = MagicMock()
    fake_chat = {"task_normal_fail": fake_room}
    monkeypatch.setattr("app.core.chat_room.get_chat_room",
                        lambda task_id: fake_chat.get(task_id))

    from dataclasses import dataclass

    @dataclass
    class FakeTaskStep:
        step_id: str = "phase3_writer"
        agent_name: str = "writer_agent"
        status: TaskStatus = TaskStatus.RUNNING
        started_at: datetime = None
        completed_at: datetime = None
        output_data: dict = None
        error: str = None

    monkeypatch.setattr("app.agents.orchestrator.TaskStep", FakeTaskStep)
    monkeypatch.setattr(Orchestrator, "_save_output_files",
                        lambda self, *a, **kw: {})
    monkeypatch.setattr(Orchestrator, "_post_agent_result",
                        lambda self, *a, **kw: None)
    monkeypatch.setattr(Orchestrator, "_check_pause",
                        lambda self, *a, **kw: None)

    try:
        await orch._write_paper_and_finish(
            task_id="task_normal_fail",
            problem_text="测试",
            sub_problems=[],
            section_results=[],
            all_results={},
            phase1_results={},
            context_base={"chat_room": fake_room, "use_critique": False},
            project_name="test",
            workflow_type="standard",
        )
    except RuntimeError:
        pass

    # 不应广播 ⛔ 熔断消息
    posted_messages = [
        call.args[1] if len(call.args) > 1 else call.args[0]
        for call in fake_room.post.call_args_list
    ]
    assert not any("⛔" in m and "熔断" in m for m in posted_messages), (
        f"普通异常不应触发熔断消息，实际: {posted_messages}"
    )

    # 但 task_step.status 仍应为 FAILED
    step = orch.task_history["task_normal_fail"][-1]
    assert step.status == TaskStatus.FAILED
    # error 应是原始异常消息，不是 ⛔ 友好提示
    assert "⛔" not in (step.error or ""), (
        f"普通异常的 error 不应包含 ⛔: {step.error}"
    )


@pytest.mark.asyncio
async def test_real_circuit_breaker_triggers_via_consecutive_failures():
    """真实场景：10 次连续 LLM 失败 → 第 11 次熔断。

    模拟 CircuitBreaker 的真实行为，验证：
    - 阈值内（<10）允许请求
    - 第 11 次抛 CircuitOpenError
    """
    breaker = get_breaker("task_real_circuit", CircuitBreakerConfig(
        failure_threshold=10,
        window_seconds=60,
    ))

    # 前 10 次失败
    for i in range(10):
        breaker.check_or_raise()  # 前 9 次允许
        breaker.record_failure()
    # 第 10 次失败应触发熔断（因为之前 9 + 第 10 = 10）
    # 但 check_or_raise 已经在循环里跑过 —— 让 breaker 内部累计
    # 由于前面循环只在第 10 次 record_failure，状态应该 OPEN

    assert breaker.state == CircuitBreaker.OPEN, (
        f"10 次失败后应 OPEN，实际 {breaker.state}"
    )

    # 第 11 次必须抛 CircuitOpenError
    with pytest.raises(CircuitOpenError) as exc_info:
        breaker.check_or_raise()
    assert "OPEN" in str(exc_info.value)
    assert "task_real_circuit" in str(exc_info.value)
    assert exc_info.value.retry_after_sec > 0

    # cleanup
    remove_breaker("task_real_circuit")
