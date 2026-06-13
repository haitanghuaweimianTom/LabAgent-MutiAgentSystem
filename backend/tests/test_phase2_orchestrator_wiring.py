"""Phase 2 第二组测试：orchestrator 接入 experimentation + peer_review。

只验证：
1. 决策函数 should_run_experimentation / should_run_peer_review
2. run_research_paper_workflow 存在 + 决策条件 + 常量
3. 旧 CUMCM/standard 路径不变（decision 函数返回 False）
"""
import pytest

from app.agents.orchestrator import Orchestrator


# ==================== 1. Decision functions ====================

@pytest.mark.parametrize("template,workflow_type,expected", [
    # 旧 4 套模板：标准模式 → False
    ("math_modeling", "standard", False),
    ("coursework", "standard", False),
    ("financial_analysis", "standard", False),
    ("research_survey", "standard", False),
    # 旧 4 套 + research_paper workflow → True
    ("math_modeling", "research_paper", True),
    ("coursework", "research_paper", True),
    # 旧 4 套 + deep_research workflow → True
    ("math_modeling", "deep_research", True),
    # CCF-A 模板（任意 workflow）→ True
    ("ieee_conference", "standard", True),
    ("neurips_2024", "standard", True),
    ("acm_sigconf", "standard", True),
    ("springer_lncs", "standard", True),
    # quick / code_focused 不会触发
    ("math_modeling", "quick", False),
    ("math_modeling", "code_focused", False),
])
def test_should_run_experimentation(template, workflow_type, expected):
    got = Orchestrator.should_run_experimentation(template, workflow_type)
    assert got is expected, f"exp({template},{workflow_type})={got} != {expected}"


@pytest.mark.parametrize("template,workflow_type,expected", [
    ("math_modeling", "standard", False),
    ("math_modeling", "research_paper", True),
    ("math_modeling", "deep_research", True),
    ("ieee_conference", "standard", True),
    ("neurips_2024", "standard", True),
    ("acm_sigconf", "standard", True),
    ("springer_lncs", "standard", True),
    ("math_modeling", "quick", False),
    ("math_modeling", "code_focused", False),
])
def test_should_run_peer_review(template, workflow_type, expected):
    got = Orchestrator.should_run_peer_review(template, workflow_type)
    assert got is expected, f"rev({template},{workflow_type})={got} != {expected}"


# ==================== 2. Constants ====================

def test_max_revision_rounds_capped_at_2():
    """peer_review 触发 writer 重写最多 2 轮（防止死循环）。"""
    assert Orchestrator.MAX_REVISION_ROUNDS == 2
    assert Orchestrator.MAX_REVISION_ROUNDS <= 3


def test_peer_revise_threshold_reasonable():
    """overall_score < 阈值才触发 revise 重写。"""
    assert 2.5 <= Orchestrator.PEER_REVISE_THRESHOLD <= 4.0


# ==================== 3. CUMCM/Standard 旧路径不变 ====================

def test_cumcm_standard_does_not_trigger_extras():
    """math_modeling + standard 走最严格的旧路径，决策 = False。"""
    for func in (Orchestrator.should_run_experimentation, Orchestrator.should_run_peer_review):
        assert func("math_modeling", "standard") is False


def test_ccf_a_templates_always_trigger_extras():
    """CCF-A 4 套模板在 standard workflow 下也触发（不依赖 workflow_type）。"""
    for tpl in ("ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs"):
        for func in (Orchestrator.should_run_experimentation, Orchestrator.should_run_peer_review):
            assert func(tpl, "standard") is True, f"{tpl} should trigger"


# ==================== 4. Top-level entry exists ====================

def test_research_paper_workflow_method_exists():
    """完整工作流入口方法存在。"""
    o = Orchestrator({})
    assert hasattr(o, "run_research_paper_workflow")
    assert callable(o.run_research_paper_workflow)


def test_research_paper_workflow_is_coroutine():
    """必须是 async 协程函数。"""
    import inspect
    o = Orchestrator({})
    assert inspect.iscoroutinefunction(o.run_research_paper_workflow)


# ==================== 5. 旧 API 不破 ====================

def test_legacy_methods_still_present():
    """旧 phase1/phase2 入口仍在，未被替换。"""
    o = Orchestrator({})
    for name in ("execute_phase1", "execute_phase2", "execute_workflow", "pause_task", "resume_task"):
        assert hasattr(o, name), f"missing legacy method: {name}"


# ==================== 6. Agent factory 注册新 agent ====================

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
