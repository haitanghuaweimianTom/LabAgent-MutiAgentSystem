"""事件总线 — 实时推送 Agent 执行状态到 SSE 流。

解决轮询延迟问题：Agent 状态变化时立即推送，而非每 2 秒轮询。

设计：
- TaskEventBus：全局单例，管理所有任务的事件订阅
- TaskEvent：结构化事件（agent_start/agent_complete/phase_change/error/progress）
- 基于 asyncio.Queue 的发布-订阅模式
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskEvent:
    """结构化任务事件。"""
    task_id: str
    event_type: str  # agent_start / agent_complete / phase_change / progress / error / completed / failed
    agent_name: Optional[str] = None
    phase: Optional[str] = None
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_sse(self) -> str:
        """转换为 SSE 格式。"""
        payload = {
            "task_id": self.task_id,
            "event_type": self.event_type,
            "agent_name": self.agent_name,
            "phase": self.phase,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"event: {self.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


class TaskEventBus:
    """全局事件总线 — 单例。

    每个任务有独立的订阅者列表，事件只推送给对应任务的订阅者。
    """

    _instance: Optional["TaskEventBus"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        # task_id -> list of subscriber queues
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        # task_id -> event history (最近 100 条，用于新订阅者回放)
        self._history: Dict[str, List[TaskEvent]] = {}
        self._max_history = 100
        self._initialized = True

    def subscribe(self, task_id: str) -> asyncio.Queue:
        """订阅某个任务的事件流。返回一个 Queue。"""
        queue: asyncio.Queue = asyncio.Queue()
        if task_id not in self._subscribers:
            self._subscribers[task_id] = []
        self._subscribers[task_id].append(queue)

        # 回放历史事件给新订阅者
        for event in self._history.get(task_id, []):
            queue.put_nowait(event)

        logger.debug(f"[EventBus] subscriber added for task {task_id}, total={len(self._subscribers[task_id])}")
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue):
        """取消订阅。"""
        if task_id in self._subscribers:
            self._subscribers[task_id] = [q for q in self._subscribers[task_id] if q is not queue]
            if not self._subscribers[task_id]:
                del self._subscribers[task_id]

    def publish(self, event: TaskEvent):
        """发布事件到对应任务的所有订阅者。"""
        task_id = event.task_id

        # 记录到历史
        if task_id not in self._history:
            self._history[task_id] = []
        self._history[task_id].append(event)
        if len(self._history[task_id]) > self._max_history:
            self._history[task_id] = self._history[task_id][-self._max_history:]

        # 推送给所有订阅者
        subscribers = self._subscribers.get(task_id, [])
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"[EventBus] queue full for task {task_id}, dropping event")

    def emit_agent_start(self, task_id: str, agent_name: str, phase: str = ""):
        """快捷方法：Agent 开始执行。"""
        self.publish(TaskEvent(
            task_id=task_id,
            event_type="agent_start",
            agent_name=agent_name,
            phase=phase,
            message=f"Agent {agent_name} 开始执行",
        ))

    def emit_agent_complete(self, task_id: str, agent_name: str, phase: str = "", summary: str = ""):
        """快捷方法：Agent 完成执行。"""
        self.publish(TaskEvent(
            task_id=task_id,
            event_type="agent_complete",
            agent_name=agent_name,
            phase=phase,
            message=summary or f"Agent {agent_name} 执行完成",
        ))

    def emit_phase_change(self, task_id: str, phase: str, message: str = ""):
        """快捷方法：阶段切换。"""
        self.publish(TaskEvent(
            task_id=task_id,
            event_type="phase_change",
            phase=phase,
            message=message or f"进入阶段: {phase}",
        ))

    def emit_progress(self, task_id: str, current: int, total: int, message: str = ""):
        """快捷方法：进度更新。"""
        self.publish(TaskEvent(
            task_id=task_id,
            event_type="progress",
            data={"current": current, "total": total, "percentage": round(current / max(total, 1) * 100)},
            message=message or f"进度: {current}/{total}",
        ))

    def emit_error(self, task_id: str, agent_name: str, error: str):
        """快捷方法：错误事件。"""
        self.publish(TaskEvent(
            task_id=task_id,
            event_type="error",
            agent_name=agent_name,
            message=error,
        ))

    def emit_completed(self, task_id: str, message: str = ""):
        """快捷方法：任务完成。"""
        self.publish(TaskEvent(
            task_id=task_id,
            event_type="completed",
            message=message or "任务已完成",
        ))

    def emit_failed(self, task_id: str, message: str = ""):
        """快捷方法：任务失败。"""
        self.publish(TaskEvent(
            task_id=task_id,
            event_type="failed",
            message=message or "任务失败",
        ))

    def cleanup(self, task_id: str):
        """清理任务的所有订阅者和历史。"""
        self._subscribers.pop(task_id, None)
        self._history.pop(task_id, None)


# 全局单例
_bus: Optional[TaskEventBus] = None


def get_event_bus() -> TaskEventBus:
    global _bus
    if _bus is None:
        _bus = TaskEventBus()
    return _bus
