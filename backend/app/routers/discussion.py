"""讨论与投票 API 路由

提供多 Agent 结构化讨论的 RESTful 接口：
- 发起讨论、提交提案、讨论发言、投票、人类覆盖
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.agent_discussion import get_discussion_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discussions", tags=["讨论"])


# ===== Pydantic 请求模型 =====

class StartDiscussionRequest(BaseModel):
    topic: str
    max_rounds: int = 3


class ProposeRequest(BaseModel):
    proposer: str
    content: str
    rationale: str = ""


class MessageRequest(BaseModel):
    agent_name: str
    message_type: str  # proposal / support / opposition / abstention / modification
    content: str
    reply_to: Optional[str] = None


class VoteRequest(BaseModel):
    agent_name: str
    decision: str  # approve / reject / abstain
    reason: str = ""


class HumanDecideRequest(BaseModel):
    decision: str  # approve / reject / revise


# ===== API 端点 =====

@router.post("/{task_id}/start")
def start_discussion(task_id: str, req: StartDiscussionRequest):
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="讨论主题不能为空")

    mgr = get_discussion_manager()
    existing = mgr.get_session(task_id)
    if existing and not existing.resolved:
        raise HTTPException(status_code=409, detail="该任务已有未结束的讨论，请先结束或解决当前讨论")

    session = mgr.start_discussion(task_id, req.topic, max_rounds=req.max_rounds)
    mgr.save_session(task_id)
    return {
        "session_id": session.session_id,
        "topic": session.topic,
        "max_rounds": session.max_rounds,
        "message": "讨论已发起",
    }


@router.post("/{task_id}/propose")
def add_proposal(task_id: str, req: ProposeRequest):
    mgr = get_discussion_manager()
    session = mgr.get_session(task_id)
    if not session:
        raise HTTPException(status_code=404, detail="该任务没有活跃的讨论，请先发起讨论")
    if session.resolved:
        raise HTTPException(status_code=400, detail="讨论已结束，无法继续提交提案")

    proposal = session.add_proposal(req.proposer, req.content, req.rationale)
    mgr.save_session(task_id)
    return {
        "proposal_id": proposal.id,
        "proposer": proposal.proposer_agent,
        "message": "提案已提交",
    }


@router.post("/{task_id}/message")
def add_message(task_id: str, req: MessageRequest):
    valid_types = {"proposal", "support", "opposition", "abstention", "modification"}
    if req.message_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"无效的消息类型: {req.message_type}，有效值: {', '.join(sorted(valid_types))}",
        )

    mgr = get_discussion_manager()
    session = mgr.get_session(task_id)
    if not session:
        raise HTTPException(status_code=404, detail="该任务没有活跃的讨论")
    if session.resolved:
        raise HTTPException(status_code=400, detail="讨论已结束")

    msg = session.add_message(req.agent_name, req.message_type, req.content, req.reply_to)
    mgr.save_session(task_id)
    return {
        "agent_name": msg.agent_name,
        "message_type": msg.message_type,
        "timestamp": msg.timestamp,
        "message": "讨论消息已记录",
    }


@router.post("/{task_id}/vote")
def cast_vote(task_id: str, req: VoteRequest):
    valid_decisions = {"approve", "reject", "abstain"}
    if req.decision not in valid_decisions:
        raise HTTPException(
            status_code=400,
            detail=f"无效的投票决定: {req.decision}，有效值: {', '.join(sorted(valid_decisions))}",
        )

    mgr = get_discussion_manager()
    session = mgr.get_session(task_id)
    if not session:
        raise HTTPException(status_code=404, detail="该任务没有活跃的讨论")
    if session.resolved:
        raise HTTPException(status_code=400, detail="讨论已结束，无法再投票")

    vote = session.vote(req.agent_name, req.decision, req.reason)
    mgr.save_session(task_id)
    return {
        "agent_name": vote.agent_name,
        "decision": vote.decision,
        "timestamp": vote.timestamp,
        "message": "投票已记录",
    }


@router.post("/{task_id}/human-decide")
def human_decide(task_id: str, req: HumanDecideRequest):
    valid_decisions = {"approve", "reject", "revise"}
    if req.decision not in valid_decisions:
        raise HTTPException(
            status_code=400,
            detail=f"无效的决策: {req.decision}，有效值: {', '.join(sorted(valid_decisions))}",
        )

    mgr = get_discussion_manager()
    session = mgr.get_session(task_id)
    if not session:
        raise HTTPException(status_code=404, detail="该任务没有活跃的讨论")

    session.set_human_decision(req.decision)
    mgr.save_session(task_id)
    return {
        "session_id": session.session_id,
        "human_decision": req.decision,
        "message": "人类决策已生效，讨论结束",
    }


@router.get("/{task_id}")
def get_discussion(task_id: str):
    mgr = get_discussion_manager()
    session = mgr.get_session(task_id)
    if not session:
        # 尝试列出历史讨论
        discussions = mgr.list_discussions(task_id)
        if not discussions:
            raise HTTPException(status_code=404, detail="该任务没有讨论记录")
        return {
            "task_id": task_id,
            "active": False,
            "discussions": discussions,
        }
    return {
        "task_id": task_id,
        "active": not session.resolved,
        "current": session.get_summary(),
    }


@router.get("/{task_id}/summary")
def get_discussion_summary(task_id: str):
    mgr = get_discussion_manager()
    session = mgr.get_session(task_id)
    if not session:
        raise HTTPException(status_code=404, detail="该任务没有讨论记录")
    return session.get_summary()
