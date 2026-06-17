"""Phase 2 第二组测试：orchestrator 精简后保留的核心接口。

验证：
1. 旧 phase1/phase2/execute_workflow 入口仍保留（API 兼容）
2. Orchestrator 仍能通过 self.agents.get() 取到 experimentation/peer_review agent
3. 已删除的 should_run_* / run_research_paper_workflow 不再被测试覆盖
"""
import pytest

from app.agents.orchestrator import Orchestrator


def test_legacy_methods_still_present():
    """旧 phase1/phase2/execute_workflow 入口仍在，保证 API 兼容。"""
    o = Orchestrator({})
    for name in ("execute_phase1", "execute_phase2", "execute_workflow", "resume_task"):
        assert hasattr(o, name), f"missing legacy method: {name}"


def test_deprecated_methods_removed():
    """已精简的旧方法应不再存在。"""
    o = Orchestrator({})
    for name in (
        "should_run_experimentation",
        "should_run_peer_review",
        "run_experimentation_design",
        "run_peer_review",
        "run_research_paper_workflow",
        "_post_modeler_result",
        "_post_solver_result",
    ):
        assert not hasattr(o, name), f"deprecated method should be removed: {name}"


def test_orchestrator_can_resolve_experimentation_and_peer_review():
    """Orchestrator 通过 self.agents.get() 应能取到新 agent。"""
    from app.agents.base import AgentFactory
    agents = {
        "experimentation_agent": AgentFactory.create("experimentation_agent"),
        "peer_review_agent": AgentFactory.create("peer_review_agent"),
    }
    o = Orchestrator(agents)
    assert o.agents["experimentation_agent"] is not None
    assert o.agents["peer_review_agent"] is not None
