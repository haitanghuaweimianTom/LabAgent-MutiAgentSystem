"""
Agent 讨论与投票协议

实现结构化的多 Agent 讨论流程：
- 提案 → 讨论 → 投票 → 决策
- 支持人类覆盖（human override）
- 讨论过程持久化到磁盘
"""
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import get_task_data_dir

logger = logging.getLogger(__name__)


# ====================================================================
# 数据模型
# ====================================================================

@dataclass
class Proposal:
    """讨论提案"""
    id: str
    proposer_agent: str
    topic: str
    content: str
    rationale: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Proposal":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class DiscussionMessage:
    """讨论消息"""
    agent_name: str
    message_type: str  # proposal / support / opposition / abstention / modification
    content: str
    reply_to: Optional[str] = None  # proposal_id
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DiscussionMessage":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Vote:
    """投票记录"""
    agent_name: str
    decision: str  # approve / reject / abstain
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Vote":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class DiscussionRound:
    """讨论轮次"""
    round_number: int
    messages: List[DiscussionMessage] = field(default_factory=list)
    votes: List[Vote] = field(default_factory=list)
    decision: str = "pending"  # approved / rejected / needs_revision / pending

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_number": self.round_number,
            "messages": [m.to_dict() for m in self.messages],
            "votes": [v.to_dict() for v in self.votes],
            "decision": self.decision,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DiscussionRound":
        return cls(
            round_number=d["round_number"],
            messages=[DiscussionMessage.from_dict(m) for m in d.get("messages", [])],
            votes=[Vote.from_dict(v) for v in d.get("votes", [])],
            decision=d.get("decision", "pending"),
        )


# ====================================================================
# 讨论会话
# ====================================================================

class DiscussionSession:
    """管理一轮完整的讨论流程"""

    def __init__(
        self,
        topic: str,
        session_id: Optional[str] = None,
        max_rounds: int = 3,
    ):
        self.session_id = session_id or f"disc_{uuid.uuid4().hex[:10]}"
        self.topic = topic
        self.proposals: List[Proposal] = []
        self.rounds: List[DiscussionRound] = []
        self.max_rounds = max_rounds
        self.human_override: Optional[str] = None
        self.current_round = 1
        self.created_at = datetime.now().isoformat()
        self.resolved = False

        # 初始化第一轮
        self.rounds.append(DiscussionRound(round_number=1))

    def add_proposal(self, proposer: str, content: str, rationale: str) -> Proposal:
        proposal = Proposal(
            id=f"prop_{uuid.uuid4().hex[:8]}",
            proposer_agent=proposer,
            topic=self.topic,
            content=content,
            rationale=rationale,
        )
        self.proposals.append(proposal)
        logger.info(f"Discussion {self.session_id}: new proposal from {proposer}")
        return proposal

    def add_message(
        self,
        agent_name: str,
        msg_type: str,
        content: str,
        reply_to: Optional[str] = None,
    ) -> DiscussionMessage:
        if msg_type not in ("proposal", "support", "opposition", "abstention", "modification"):
            raise ValueError(f"Invalid message_type: {msg_type}")

        msg = DiscussionMessage(
            agent_name=agent_name,
            message_type=msg_type,
            content=content,
            reply_to=reply_to,
        )
        current = self.rounds[-1]
        current.messages.append(msg)
        logger.debug(f"Discussion {self.session_id}: {agent_name} -> {msg_type}")
        return msg

    def vote(self, agent_name: str, decision: str, reason: str) -> Vote:
        if decision not in ("approve", "reject", "abstain"):
            raise ValueError(f"Invalid vote decision: {decision}")

        v = Vote(agent_name=agent_name, decision=decision, reason=reason)
        current = self.rounds[-1]
        current.votes.append(v)
        logger.info(f"Discussion {self.session_id}: {agent_name} votes {decision}")
        return v

    def resolve(self) -> DiscussionRound:
        """统计当前轮次投票，决定通过/驳回/需修订"""
        current = self.rounds[-1]

        if not current.votes:
            current.decision = "needs_revision"
        else:
            approve = sum(1 for v in current.votes if v.decision == "approve")
            reject = sum(1 for v in current.votes if v.decision == "reject")
            total = approve + reject  # 不含 abstain

            if total == 0:
                current.decision = "needs_revision"
            elif approve > reject:
                current.decision = "approved"
            elif reject > approve:
                current.decision = "rejected"
            else:
                current.decision = "needs_revision"

        self.resolved = True
        logger.info(f"Discussion {self.session_id}: resolved -> {current.decision}")
        return current

    def start_new_round(self) -> DiscussionRound:
        """开始新一轮讨论（若未超过最大轮次）"""
        if self.current_round >= self.max_rounds:
            raise ValueError(f"Max rounds ({self.max_rounds}) reached")
        self.current_round += 1
        new_round = DiscussionRound(round_number=self.current_round)
        self.rounds.append(new_round)
        return new_round

    def set_human_decision(self, decision: str) -> None:
        """人类覆盖决策"""
        self.human_override = decision
        self.resolved = True
        # 更新最后一轮的 decision
        if self.rounds:
            self.rounds[-1].decision = f"human_override:{decision}"
        logger.info(f"Discussion {self.session_id}: human override -> {decision}")

    def get_summary(self) -> Dict[str, Any]:
        """获取完整讨论摘要"""
        current = self.rounds[-1] if self.rounds else None
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "created_at": self.created_at,
            "resolved": self.resolved,
            "human_override": self.human_override,
            "total_proposals": len(self.proposals),
            "total_rounds": len(self.rounds),
            "max_rounds": self.max_rounds,
            "current_decision": current.decision if current else "pending",
            "proposals": [p.to_dict() for p in self.proposals],
            "rounds": [r.to_dict() for r in self.rounds],
            "final_decision": self.human_override or (current.decision if current else "pending"),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "max_rounds": self.max_rounds,
            "current_round": self.current_round,
            "human_override": self.human_override,
            "resolved": self.resolved,
            "created_at": self.created_at,
            "proposals": [p.to_dict() for p in self.proposals],
            "rounds": [r.to_dict() for r in self.rounds],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DiscussionSession":
        session = cls(
            topic=d["topic"],
            session_id=d["session_id"],
            max_rounds=d.get("max_rounds", 3),
        )
        session.current_round = d.get("current_round", 1)
        session.human_override = d.get("human_override")
        session.resolved = d.get("resolved", False)
        session.created_at = d.get("created_at", session.created_at)
        session.proposals = [Proposal.from_dict(p) for p in d.get("proposals", [])]
        session.rounds = [DiscussionRound.from_dict(r) for r in d.get("rounds", [])]
        return session


# ====================================================================
# 讨论管理器
# ====================================================================

class DiscussionManager:
    """管理所有活跃讨论的全局管理器"""

    def __init__(self):
        self.sessions: Dict[str, DiscussionSession] = {}
        self._task_data_dir: Path = get_task_data_dir()

    def _discussions_dir(self, task_id: str) -> Path:
        d = self._task_data_dir / task_id / "discussions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _session_file(self, task_id: str, discussion_id: str) -> Path:
        return self._discussions_dir(task_id) / f"{discussion_id}.json"

    def start_discussion(
        self,
        task_id: str,
        topic: str,
        max_rounds: int = 3,
    ) -> DiscussionSession:
        session = DiscussionSession(topic=topic, max_rounds=max_rounds)
        self.sessions[task_id] = session
        logger.info(f"Started discussion for task {task_id}: {topic}")
        return session

    def get_session(self, task_id: str) -> Optional[DiscussionSession]:
        # 优先从内存获取
        if task_id in self.sessions:
            return self.sessions[task_id]
        # 尝试从磁盘恢复
        self.load_session(task_id)
        return self.sessions.get(task_id)

    def end_discussion(self, task_id: str) -> None:
        session = self.sessions.get(task_id)
        if session:
            self.save_session(task_id)
            del self.sessions[task_id]
            logger.info(f"Ended discussion for task {task_id}")

    def save_session(self, task_id: str) -> None:
        session = self.sessions.get(task_id)
        if not session:
            return
        filepath = self._session_file(task_id, session.session_id)
        try:
            data = session.to_dict()
            filepath.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.debug(f"Saved discussion {session.session_id} for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to save discussion: {e}")

    def load_session(self, task_id: str) -> Optional[DiscussionSession]:
        discussions_dir = self._discussions_dir(task_id)
        files = sorted(discussions_dir.glob("disc_*.json"), reverse=True)
        if not files:
            return None

        # 加载最新的讨论
        try:
            data = json.loads(files[0].read_text(encoding="utf-8"))
            session = DiscussionSession.from_dict(data)
            self.sessions[task_id] = session
            logger.debug(f"Loaded discussion {session.session_id} for task {task_id}")
            return session
        except Exception as e:
            logger.error(f"Failed to load discussion from {files[0]}: {e}")
            return None

    def list_discussions(self, task_id: str) -> List[Dict[str, Any]]:
        """列出任务下所有讨论"""
        discussions_dir = self._discussions_dir(task_id)
        result = []
        for f in discussions_dir.glob("disc_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append({
                    "session_id": data.get("session_id"),
                    "topic": data.get("topic"),
                    "resolved": data.get("resolved", False),
                    "decision": data.get("rounds", [{}])[-1].get("decision", "pending") if data.get("rounds") else "pending",
                })
            except Exception:
                pass
        return result


# ====================================================================
# 全局实例
# ====================================================================

_manager: Optional[DiscussionManager] = None


def get_discussion_manager() -> DiscussionManager:
    global _manager
    if _manager is None:
        _manager = DiscussionManager()
    return _manager
