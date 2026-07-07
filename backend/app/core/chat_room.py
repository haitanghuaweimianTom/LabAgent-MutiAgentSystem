"""
Agent 聊天室 - 核心模块（v2：支持实时推送 + 用户消息 + 多 Agent 讨论）

让所有 Agent 像团队一样在聊天室中互相沟通、@提及、共享上下文。
用户也可以加入讨论，修正工作方向。
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Message:
    id: str
    sender: str          # agent名称 / "user"
    sender_label: str    # 显示名称
    content: str
    msg_type: str        # text / broadcast / mention / result / error / user_input / discussion
    mentions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    task_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "sender_label": self.sender_label,
            "content": self.content,
            "type": self.msg_type,
            "mentions": self.mentions,
            "timestamp": self.timestamp.isoformat(),
        }


class ChatRoom:
    """聊天室 v2：支持 SSE 实时推送 + 用户消息 + 讨论线程"""

    def __init__(self, room_id: str, task_id: str, problem_text: str):
        self.room_id = room_id
        self.task_id = task_id
        self.problem_text = problem_text
        self.messages: List[Message] = []
        self.agents: Dict[str, Dict[str, Any]] = {}

        # SSE 订阅者列表（每个订阅者是一个 asyncio.Queue）
        self._subscribers: List[asyncio.Queue] = []

        # 用户消息队列（Agent 可以检查是否有用户输入）
        self._user_messages: List[Message] = []

        # 讨论线程：discuss_id -> list of messages
        self._discussions: Dict[str, List[Message]] = {}

        # 用户反馈队列（用于影响后续 Agent 行为）
        self._user_feedback: List[Dict[str, Any]] = []

        # 自动迭代控制
        self._auto_iterate: bool = True  # 用户未发言时自动迭代
        self._user_last_spoke_at: Optional[datetime] = None
        self._waiting_for_user: bool = False  # 是否正在等待用户回复

        # 团队成员定义
        self.team = {
            "coordinator": {"label": "协调者", "color": "#e74c3c", "role": "项目负责人，制定计划协调进度"},
            "research_agent": {"label": "研究员", "color": "#3498db", "role": "搜集文献和数据"},
            "data_agent": {"label": "数据分析师", "color": "#9b59b6", "role": "数据分析与预处理"},
            "analyzer_agent": {"label": "分析师", "color": "#f39c12", "role": "问题分析与任务分解"},
            "modeler_agent": {"label": "建模师", "color": "#27ae60", "role": "建立数学模型"},
            "algorithm_engineer_agent": {"label": "算法工程师", "color": "#16a085", "role": "设计创新算法与方法"},
            "financial_analyst_agent": {"label": "金融分析师", "color": "#d4ac0d", "role": "建立金融数学与量化模型"},
            "solver_agent": {"label": "求解器", "color": "#e67e22", "role": "编程求解与验证"},
            "writer_agent": {"label": "写作专家", "color": "#1abc9c", "role": "生成完整LaTeX论文"},
            "peer_review_agent": {"label": "审稿人", "color": "#8e44ad", "role": "同行评议与质量把关"},
            "experimentation_agent": {"label": "实验设计专家", "color": "#2c3e50", "role": "设计严谨可复现的实验方案"},
            "figure_agent": {"label": "科研绘图师", "color": "#e84393", "role": "生成发表级质量图表"},
            "user": {"label": "用户", "color": "#3498db", "role": "人类专家，参与讨论与决策"},
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

        # 异步通知所有 SSE 订阅者
        self._notify_subscribers(msg)

        # 广播到 EventBus（供前端实时监听）
        try:
            from ..core.event_bus import get_event_bus
            get_event_bus().broadcast_chat_message(
                task_id=self.task_id,
                sender=sender,
                content=content,
                sender_label=sender_label,
                msg_type=msg_type,
            )
        except Exception:
            pass  # EventBus 不影响聊天室核心功能

        return msg

    def _notify_subscribers(self, msg: Message) -> None:
        """通知所有 SSE 订阅者（非阻塞）"""
        data = json.dumps(msg.to_dict(), ensure_ascii=False)
        for q in self._subscribers:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass  # 订阅者处理太慢，丢弃

    def post(
        self,
        sender: str,
        content: str,
        msg_type: str = "text",
        mentions: Optional[List[str]] = None,
    ) -> Message:
        """Agent 发言"""
        label = self.team.get(sender, {}).get("label", sender)
        msg = self._add_message(sender, label, content, msg_type, mentions)

        if mentions:
            mentioned = ", ".join([self.team.get(m, {}).get("label", m) for m in mentions])
            logger.info(f"[{label}] @{mentioned}: {content[:50]}")

        return msg

    def user_post(self, content: str, mentions: Optional[List[str]] = None) -> Message:
        """用户发言（通过前端输入）"""
        msg = self._add_message("user", "用户", content, "user_input", mentions)
        self._user_messages.append(msg)
        self._user_last_spoke_at = datetime.now()
        self._waiting_for_user = False

        # 提取并存储用户反馈（用于影响后续 Agent）
        self._extract_feedback(content, msg.id)

        logger.info(f"[用户] {content[:80]}")
        return msg

    def _extract_feedback(self, content: str, msg_id: str) -> None:
        """从用户消息中提取结构化反馈"""
        feedback = {
            "msg_id": msg_id,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "type": "general",
            "target_agent": None,
            "action": None,
        }

        # 检测反馈类型
        content_lower = content.lower()

        # 修正建议
        if any(kw in content_lower for kw in ["修正", "修改", "改", "不对", "错误", "问题", "应该", "建议"]):
            feedback["type"] = "correction"
            feedback["action"] = "revise"

        # 确认/批准
        elif any(kw in content_lower for kw in ["确认", "同意", "可以", "好", "ok", "yes", "没问题"]):
            feedback["type"] = "approval"
            feedback["action"] = "proceed"

        # 拒绝/驳回
        elif any(kw in content_lower for kw in ["拒绝", "不行", "驳回", "重做", "重新", "no", "不对"]):
            feedback["type"] = "rejection"
            feedback["action"] = "rework"

        # 问题/疑问
        elif any(kw in content_lower for kw in ["为什么", "怎么", "什么", "？", "?", "疑问", "不清楚"]):
            feedback["type"] = "question"
            feedback["action"] = "clarify"

        self._user_feedback.append(feedback)

    def get_user_feedback(self, since_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取用户反馈列表（供 Agent 读取）"""
        if since_id is None:
            return list(self._user_feedback)
        # 找到 since_id 之后的反馈
        idx = next((i for i, f in enumerate(self._user_feedback) if f["msg_id"] == since_id), -1)
        return self._user_feedback[idx + 1:]

    def get_latest_feedback_summary(self) -> str:
        """获取最新用户反馈的摘要（供 LLM 使用）"""
        if not self._user_feedback:
            return ""

        recent = self._user_feedback[-5:]  # 最近 5 条
        lines = ["【用户反馈摘要】"]
        for f in recent:
            type_label = {
                "correction": "修正建议",
                "approval": "确认",
                "rejection": "驳回",
                "question": "疑问",
                "general": "一般反馈",
            }.get(f["type"], "反馈")
            lines.append(f"- [{type_label}] {f['content'][:100]}")

        return "\n".join(lines)

    def broadcast(self, sender: str, content: str) -> Message:
        """广播消息"""
        return self.post(sender, content, "broadcast")

    def start_discussion(self, topic: str, participants: List[str]) -> str:
        """发起一个讨论线程"""
        discuss_id = f"disc_{uuid.uuid4().hex[:8]}"
        self._discussions[discuss_id] = []
        participant_labels = [self.team.get(p, {}).get("label", p) for p in participants]
        self.post(
            "coordinator",
            f"📢 发起讨论：{topic}\n参与人：{', '.join(participant_labels)}",
            "discussion",
            mentions=participants,
        )
        return discuss_id

    def post_to_discussion(self, discuss_id: str, sender: str, content: str) -> Optional[Message]:
        """在讨论线程中发言"""
        if discuss_id not in self._discussions:
            return None
        label = self.team.get(sender, {}).get("label", sender)
        msg = self._add_message(sender, label, content, "discussion")
        self._discussions[discuss_id].append(msg)
        return msg

    def get_discussion(self, discuss_id: str) -> List[Dict[str, Any]]:
        """获取讨论线程的所有消息"""
        msgs = self._discussions.get(discuss_id, [])
        return [m.to_dict() for m in msgs]

    def get_messages(self, after_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取消息列表"""
        if after_id:
            idx = next((i for i, m in enumerate(self.messages) if m.id == after_id), -1)
            msgs = self.messages[idx + 1:]
        else:
            msgs = self.messages
        return [m.to_dict() for m in msgs]

    def get_user_messages_since(self, since: Optional[datetime] = None) -> List[Message]:
        """获取用户消息（用于 Agent 检查用户是否有新输入）"""
        if since is None:
            return list(self._user_messages)
        return [m for m in self._user_messages if m.timestamp > since]

    def has_user_input(self) -> bool:
        """检查是否有用户输入（用于自动迭代判断）。

        v7.2 修复：只在系统正在等待用户时才算"有用户输入"。
        之前 or True 导致任何历史消息都被视为有效输入，
        导致 peer_review 永远路由到 wait_user。
        """
        return (
            self._waiting_for_user  # 只在等待用户时才检查
            and len(self._user_messages) > 0
            and self._user_last_spoke_at is not None
        )

    def set_waiting_for_user(self, waiting: bool = True) -> None:
        """设置是否正在等待用户回复"""
        self._waiting_for_user = waiting

    def should_auto_iterate(self) -> bool:
        """判断是否应该自动迭代（用户未发言时）"""
        if not self._auto_iterate:
            return False
        # 如果正在等待用户回复，且用户已发言，则不自动迭代
        if self._waiting_for_user and self._user_last_spoke_at:
            return False
        return True

    def get_context(self, for_agent: Optional[str] = None) -> str:
        """获取对话上下文摘要（供 LLM 使用）"""
        recent = self.messages[-20:] if len(self.messages) > 20 else self.messages
        lines = []
        for m in recent:
            prefix = f"[{m.sender_label}]"
            if m.msg_type == "user_input":
                prefix = f"[👤 用户]"
            elif m.msg_type == "discussion":
                prefix = f"[💬 讨论-{m.sender_label}]"
            lines.append(f"{prefix} {m.content}")

        # 添加用户反馈摘要
        feedback_summary = self.get_latest_feedback_summary()
        if feedback_summary:
            lines.append("")
            lines.append(feedback_summary)

        return "\n".join(lines)

    # ===== SSE 订阅 =====

    def subscribe(self) -> asyncio.Queue:
        """订阅消息推送（返回一个 Queue，SSE 端点从中读取）"""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """取消订阅"""
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def message_stream(self) -> AsyncGenerator[str, None]:
        """SSE 消息流生成器"""
        q = self.subscribe()
        try:
            # 先发送历史消息
            for msg in self.messages:
                yield f"data: {json.dumps(msg.to_dict(), ensure_ascii=False)}\n\n"
            # 然后实时推送新消息
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # 发送心跳
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(q)


# ===== 全局聊天室管理 =====
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
