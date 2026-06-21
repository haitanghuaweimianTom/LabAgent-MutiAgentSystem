"""验证 use_critique=False 时 LangGraph _route_peer_review 直接跳过修订循环。

用户反馈：「关闭任务自评功能了，为什么写作专家还写了第二稿而不直接交付给我？」
根因：use_critique=False 只关闭 WriterAgent 章节级自评，但 LangGraph 编排器
仍然会进入 peer_review 节点，触发 revise 重新跑 writer。

修复：_route_peer_review 检查 state["use_critique"]，为 False 时直接返回 "accept"。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.agents.langgraph_orchestrator import LangGraphOrchestrator, LANGGRAPH_AVAILABLE


@pytest.fixture
def mock_chat_room(monkeypatch):
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


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
def test_route_peer_review_skips_revision_when_use_critique_false(mock_chat_room):
    """use_critique=False 时，peer review 即便建议 revise，也必须直接 accept。"""
    orch = LangGraphOrchestrator(agents={}, config={"enable_peer_review": True})

    # 构造一个让 peer review 强烈建议 revise 的 state
    state = {
        "task_id": "t_skip",
        "problem_text": "p",
        "use_critique": False,
        "results": {
            "peer_review_agent": {
                "recommendation": "revise",  # 即便如此，也必须跳过
                "overall_score": 2.0,        # 远低于 4.0 接受线
            },
            "writer_agent": {"_revision_count": 1},
        },
    }
    decision = orch._route_peer_review(state)
    assert decision == "accept", (
        f"关闭自评后即使评分低也应直接 accept，但 _route_peer_review 返回 {decision!r}"
    )


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
def test_route_peer_review_normal_when_use_critique_true(mock_chat_room):
    """use_critique=True 时（默认），peer review 评分低应进入 revise 修订循环。"""
    orch = LangGraphOrchestrator(agents={}, config={"enable_peer_review": True})

    state = {
        "task_id": "t_revise",
        "problem_text": "p",
        "use_critique": True,
        "results": {
            "peer_review_agent": {
                "recommendation": "revise",
                "overall_score": 2.5,  # 低于 4.0 接受线
            },
            "writer_agent": {"_revision_count": 0},
        },
    }
    decision = orch._route_peer_review(state)
    assert decision == "revise", (
        f"开启自评且评分低时应进入 revise，但返回 {decision!r}"
    )


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
def test_route_peer_review_accepts_on_high_score(mock_chat_room):
    """use_critique=True 且评分 >= 4.0 时直接 accept。"""
    orch = LangGraphOrchestrator(agents={}, config={"enable_peer_review": True})

    state = {
        "task_id": "t_accept",
        "problem_text": "p",
        "use_critique": True,
        "results": {
            "peer_review_agent": {
                "recommendation": "revise",
                "overall_score": 4.5,
            },
            "writer_agent": {"_revision_count": 1},
        },
    }
    decision = orch._route_peer_review(state)
    assert decision == "accept"


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="langgraph not installed")
def test_route_peer_review_aborts_on_reject(mock_chat_room):
    """recommendation=reject 时必须 abort，不受 use_critique 影响。"""
    orch = LangGraphOrchestrator(agents={}, config={"enable_peer_review": True})

    state = {
        "task_id": "t_reject",
        "problem_text": "p",
        "use_critique": True,
        "results": {
            "peer_review_agent": {
                "recommendation": "reject",
                "overall_score": 1.0,
            },
        },
    }
    decision = orch._route_peer_review(state)
    assert decision == "abort"
