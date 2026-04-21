"""
Agent 聊天室 - 核心模块
让所有Agent像团队一样在聊天室中互相沟通、@提及、共享上下文
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Message:
    id: str
    sender: str          # agent名称
    sender_label: str    # 显示名称
    content: str
    msg_type: str        # text / broadcast / mention / result / error
    mentions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    task_id: Optional[str] = None


class ChatRoom:
    """聊天室"""

    def __init__(self, room_id: str, task_id: str, problem_text: str):
        self.room_id = room_id
        self.task_id = task_id
        self.problem_text = problem_text
        self.messages: List[Message] = []
        self.agents: Dict[str, Dict[str, Any]] = {}

        # 团队成员定义
        self.team = {
            "coordinator": {"label": "协调者", "color": "#e74c3c", "role": "项目负责人，制定计划协调进度"},
            "research_agent": {"label": "研究员", "color": "#3498db", "role": "搜集文献和数据"},
            "data_agent": {"label": "数据分析师", "color": "#9b59b6", "role": "数据分析与预处理"},
            "analyzer_agent": {"label": "分析师", "color": "#f39c12", "role": "问题分析与任务分解"},
            "modeler_agent": {"label": "建模师", "color": "#27ae60", "role": "建立数学模型"},
            "solver_agent": {"label": "求解器", "color": "#e67e22", "role": "编程求解与验证"},
            "writer_agent": {"label": "写作专家", "color": "#1abc9c", "role": "生成完整LaTeX论文"},
        }

        # 系统初始化消息
        self._add_message("system", "系统", f"🎯 任务已启动！问题：{problem_text[:80]}...", "broadcast")
        self._add_message("coordinator", "协调者", "大家好！我已收到任务，现在开始制定工作计划。", "broadcast")

    def _add_message(
        self,
        sender: str,
        sender_label: str,
        content: str,
        msg_type: str = "text",
        mentions: Optional[List[str]] = None,
    ) -> Message:
        msg = Message(
            id=f"msg_{uuid.uuid4().hex[:8]}",
            sender=sender,
            sender_label=sender_label,
            content=content,
            msg_type=msg_type,
            mentions=mentions or [],
            task_id=self.task_id,
        )
        self.messages.append(msg)
        return msg

    def post(
        self,
        sender: str,
        content: str,
        msg_type: str = "text",
        mentions: Optional[List[str]] = None,
    ) -> Message:
        """Agent发言"""
        label = self.team.get(sender, {}).get("label", sender)
        msg = self._add_message(sender, label, content, msg_type, mentions)

        # 如果@了某个Agent，同步广播
        if mentions:
            mentioned = ", ".join([self.team.get(m, {}).get("label", m) for m in mentions])
            logger.info(f"[{label}] @{mentioned}: {content[:50]}")

        return msg

    def broadcast(self, sender: str, content: str) -> Message:
        """广播消息"""
        return self.post(sender, content, "broadcast")

    def get_messages(self, after_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取消息列表"""
        if after_id:
            idx = next((i for i, m in enumerate(self.messages) if m.id == after_id), -1)
            msgs = self.messages[idx + 1:]
        else:
            msgs = self.messages

        return [
            {
                "id": m.id,
                "sender": m.sender,
                "sender_label": m.sender_label,
                "content": m.content,
                "type": m.msg_type,
                "mentions": m.mentions,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in msgs
        ]

    def get_context(self, for_agent: Optional[str] = None) -> str:
        """获取对话上下文摘要（供LLM使用）"""
        recent = self.messages[-20:] if len(self.messages) > 20 else self.messages
        lines = []
        for m in recent:
            lines.append(f"[{m.sender_label}] {m.content}")
        return "\n".join(lines)


# 全局聊天室管理
_chat_rooms: Dict[str, ChatRoom] = {}


def create_chat_room(task_id: str, problem_text: str) -> ChatRoom:
    """创建聊天室"""
    room = ChatRoom(room_id=f"room_{task_id}", task_id=task_id, problem_text=problem_text)
    _chat_rooms[task_id] = room
    logger.info(f"Created chat room for task {task_id}")
    return room


def get_chat_room(task_id: str) -> Optional[ChatRoom]:
    return _chat_rooms.get(task_id)


def list_chat_rooms() -> List[str]:
    return list(_chat_rooms.keys())
