"""Phase 2 第一组测试：
- task_persistence 增量 checkpoint API
- experimentation_agent 基本逻辑
- peer_review_agent 基本逻辑（含 recommendation 强制覆盖）
"""
import json
from pathlib import Path

import pytest

from app.core.task_persistence import (
    save_task_checkpoint,
    load_task_checkpoints,
    load_task_checkpoint,
    clear_task_checkpoints,
)
from app.agents.experimentation_agent import (
    ExperimentationAgent,
    EXPERIMENTATION_SYSTEM,
)
from app.agents.peer_review_agent import (
    PeerReviewAgent,
    PEER_REVIEW_SYSTEM,
)
from app.agents.base import AgentFactory


# ==================== 1. 增量 checkpoint ====================

@pytest.fixture
def patched_task_dir(tmp_path, monkeypatch):
    import app.core.task_persistence as tp
    monkeypatch.setattr(tp, "TASK_DATA_DIR", tmp_path)
    return tmp_path


def test_save_and_load_checkpoint(patched_task_dir):
    save_task_checkpoint("t1", "phase1", "analyzer", {"x": 1})
    cps = load_task_checkpoints("t1")
    assert len(cps) == 1
    assert cps[0]["phase"] == "phase1"
    assert cps[0]["step"] == "analyzer"
    assert cps[0]["payload"] == {"x": 1}
    assert "saved_at" in cps[0]


def test_checkpoint_upsert(patched_task_dir):
    """同 (phase, step) 后写覆盖前写。"""
    save_task_checkpoint("t1", "phase1", "analyzer", {"x": 1})
    save_task_checkpoint("t1", "phase1", "analyzer", {"x": 2})
    cps = load_task_checkpoints("t1")
    assert len(cps) == 1
    assert cps[0]["payload"]["x"] == 2


def test_checkpoint_multiple_steps(patched_task_dir):
    save_task_checkpoint("t1", "phase1", "analyzer", {"a": 1})
    save_task_checkpoint("t1", "phase1", "data", {"b": 2})
    save_task_checkpoint("t1", "phase2", "modeler", {"c": 3})
    cps = load_task_checkpoints("t1")
    assert len(cps) == 3
    keys = [(c["phase"], c["step"]) for c in cps]
    assert ("phase1", "analyzer") in keys
    assert ("phase1", "data") in keys
    assert ("phase2", "modeler") in keys


def test_load_checkpoint_by_phase_step(patched_task_dir):
    save_task_checkpoint("t1", "phase1", "data", {"rows": 100})
    e = load_task_checkpoint("t1", "phase1", "data")
    assert e["payload"]["rows"] == 100
    e_miss = load_task_checkpoint("t1", "phase1", "nonexistent")
    assert e_miss is None


def test_clear_checkpoints(patched_task_dir):
    save_task_checkpoint("t1", "phase1", "analyzer", {"x": 1})
    assert clear_task_checkpoints("t1") is True
    assert load_task_checkpoints("t1") == []
    # clear 不存在的也是 True（幂等）
    assert clear_task_checkpoints("t1") is True


def test_checkpoint_persists_to_disk(patched_task_dir):
    save_task_checkpoint("t2", "phase1", "analyzer", {"a": 1})
    fpath = patched_task_dir / "t2_checkpoints.json"
    assert fpath.exists()
    data = json.loads(fpath.read_text())
    assert data["task_id"] == "t2"
    assert len(data["checkpoints"]) == 1


# ==================== 2. ExperimentationAgent ====================

def test_experimentation_agent_registered():
    assert "experimentation_agent" in AgentFactory.list_agents()


def test_experimentation_system_prompt_well_formed():
    assert "baselines" in EXPERIMENTATION_SYSTEM
    assert "datasets" in EXPERIMENTATION_SYSTEM
    assert "metrics" in EXPERIMENTATION_SYSTEM
    assert "ablation_plan" in EXPERIMENTATION_SYSTEM
    assert "splits" in EXPERIMENTATION_SYSTEM
    assert "hardware_budget" in EXPERIMENTATION_SYSTEM
    # 严格控制幻觉
    assert "不要" in EXPERIMENTATION_SYSTEM or "不要补充" in EXPERIMENTATION_SYSTEM or "不要编造" in EXPERIMENTATION_SYSTEM


def test_experimentation_empty_plan():
    e = ExperimentationAgent.__new__(ExperimentationAgent)
    plan = ExperimentationAgent._empty_plan()
    assert plan["baselines"] == []
    assert plan["hardware_budget"]["feasible"] is False


def test_experimentation_parse_invalid_json():
    e = ExperimentationAgent.__new__(ExperimentationAgent)
    plan = e._parse_plan("not json at all")
    assert plan["baselines"] == []


def test_experimentation_parse_valid_json():
    e = ExperimentationAgent.__new__(ExperimentationAgent)
    raw = json.dumps({
        "baselines": [{"name": "Random Forest", "category": "baseline"}],
        "datasets": [{"name": "MNIST", "size": "70k", "source": "公开"}],
        "metrics": [{"name": "Accuracy", "direction": "higher_is_better"}],
        "hardware_budget": {"feasible": True, "gpu": "1× A100"},
        "ablation_plan": [{"component": "embedding"}],
        "splits": {"method": "train/val/test", "ratios": "8:1:1"},
        "risks": ["overfitting"],
    })
    plan = e._parse_plan(raw)
    assert plan["baselines"][0]["name"] == "Random Forest"
    assert plan["datasets"][0]["name"] == "MNIST"
    assert plan["hardware_budget"]["feasible"] is True
    assert plan["splits"]["ratios"] == "8:1:1"


def test_experimentation_build_user_prompt_includes_problem():
    e = ExperimentationAgent.__new__(ExperimentationAgent)
    prompt = e._build_user_prompt("Test problem", [{"id": 1, "name": "sub1"}], {})
    assert "Test problem" in prompt
    assert "sub1" in prompt


# ==================== 3. PeerReviewAgent ====================

def test_peer_review_agent_registered():
    assert "peer_review_agent" in AgentFactory.list_agents()


def test_peer_review_system_prompt_well_formed():
    assert "novelty" in PEER_REVIEW_SYSTEM
    assert "soundness" in PEER_REVIEW_SYSTEM
    assert "clarity" in PEER_REVIEW_SYSTEM
    assert "significance" in PEER_REVIEW_SYSTEM
    assert "accept" in PEER_REVIEW_SYSTEM
    assert "revise" in PEER_REVIEW_SYSTEM
    assert "reject" in PEER_REVIEW_SYSTEM
    # 严格控制幻觉
    assert "不要" in PEER_REVIEW_SYSTEM or "不要凭空" in PEER_REVIEW_SYSTEM or "实际" in PEER_REVIEW_SYSTEM


def test_peer_review_empty_review_defaults_to_revise():
    pr = PeerReviewAgent.__new__(PeerReviewAgent)
    r = PeerReviewAgent._empty_review()
    assert r["recommendation"] == "revise"
    assert r["overall_score"] == 3.0


def test_peer_review_parse_invalid_json():
    pr = PeerReviewAgent.__new__(PeerReviewAgent)
    r = pr._parse_review("not json")
    assert r["overall_score"] == 3.0
    assert r["recommendation"] == "revise"


def test_peer_review_high_scores_yields_accept():
    pr = PeerReviewAgent.__new__(PeerReviewAgent)
    raw = json.dumps({
        "scores": {"novelty": 5, "soundness": 4, "clarity": 5, "significance": 4},
        "recommendation": "accept",
    })
    r = pr._parse_review(raw)
    assert r["recommendation"] == "accept"
    assert r["overall_score"] == 4.5


def test_peer_review_low_dimension_forces_revise():
    """任一维度 < 4 即使 LLM 输出 accept 也强制 revise。"""
    pr = PeerReviewAgent.__new__(PeerReviewAgent)
    raw = json.dumps({
        "scores": {"novelty": 5, "soundness": 5, "clarity": 5, "significance": 3},
        "recommendation": "accept",
    })
    r = pr._parse_review(raw)
    assert r["recommendation"] == "revise"


def test_peer_review_scores_clamped_to_1_5():
    pr = PeerReviewAgent.__new__(PeerReviewAgent)
    raw = json.dumps({
        "scores": {"novelty": 99, "soundness": 0, "clarity": -3, "significance": "high"},
    })
    r = pr._parse_review(raw)
    assert 1 <= r["scores"]["novelty"] <= 5
    assert 1 <= r["scores"]["soundness"] <= 5


def test_peer_review_get_acceptance_threshold_bridges_registry():
    for tid, expected in [
        ("math_modeling", 75),
        ("coursework", 75),
        ("ieee_conference", 85),
        ("neurips_2024", 85),
        ("springer_lncs", 80),
        ("unknown-xxx", 75),
    ]:
        got = PeerReviewAgent.get_acceptance_threshold(tid)
        assert got == expected, f"{tid}: {got} != {expected}"


def test_peer_review_build_user_prompt_truncates_long_latex():
    pr = PeerReviewAgent.__new__(PeerReviewAgent)
    long_latex = "\\section{T}\nX" * 5000  # 25k chars
    prompt = PeerReviewAgent._build_user_prompt(long_latex, [], 85)
    assert "85" in prompt
    # 不应超过 ~4500 chars (4000 + 头部)
    assert len(prompt) < 5000
