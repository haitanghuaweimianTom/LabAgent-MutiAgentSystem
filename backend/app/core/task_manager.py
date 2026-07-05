"""异步任务管理器 — 轻量级任务队列。

替代 asyncio.create_task 的 fire-and-forget 模式，提供：
- 任务状态跟踪（pending/running/completed/failed/cancelled）
- 任务取消（真正取消底层协程）
- 任务并发限制（防止 LLM API 配额耗尽）
- 任务持久化（重启后可恢复）
- 与 EventBus 集成（推送任务状态变化）

设计参考：Celery 的概念，但用纯 asyncio 实现（零外部依赖）。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ManagedTask:
    """受管理的任务。"""
    task_id: str
    coro_factory: Callable[[], Coroutine]  # 创建协程的工厂函数
    status: TaskState = TaskState.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Any = None
    _asyncio_task: Optional[asyncio.Task] = field(default=None, repr=False)
    _cancel_event: Optional[asyncio.Event] = field(default=None, repr=False)

    def cancel(self) -> bool:
        """取消任务。"""
        if self.status not in (TaskState.PENDING, TaskState.RUNNING):
            return False
        self.status = TaskState.CANCELLED
        self.completed_at = datetime.now().isoformat()
        if self._cancel_event:
            self._cancel_event.set()
        if self._asyncio_task and not self._asyncio_task.done():
            self._asyncio_task.cancel()
        return True


class AsyncTaskManager:
    """异步任务管理器 — 单例。

    核心功能：
    1. 提交任务（返回 task_id）
    2. 取消任务（真正取消底层协程）
    3. 查询状态
    4. 并发限制（最多 N 个任务同时运行）
    """

    _instance: Optional["AsyncTaskManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_concurrent: int = 3):
        if self._initialized:
            return
        self.max_concurrent = max_concurrent
        self._tasks: Dict[str, ManagedTask] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._initialized = True
        logger.info(f"[TaskManager] initialized: max_concurrent={max_concurrent}")

    def submit(
        self,
        task_id: str,
        coro_factory: Callable[[], Coroutine],
        priority: int = 0,
    ) -> str:
        """提交异步任务。

        Args:
            task_id: 唯一任务 ID
            coro_factory: 创建协程的工厂函数（每次调用返回新的协程）
            priority: 优先级（保留，未来使用）

        Returns:
            task_id
        """
        if task_id in self._tasks:
            logger.warning(f"[TaskManager] task {task_id} already exists, ignoring")
            return task_id

        managed = ManagedTask(task_id=task_id, coro_factory=coro_factory)
        self._tasks[task_id] = managed

        # 创建后台任务
        loop = asyncio.get_event_loop()
        managed._asyncio_task = loop.create_task(self._run_with_semaphore(managed))

        logger.info(f"[TaskManager] task {task_id} submitted")
        return task_id

    async def _run_with_semaphore(self, task: ManagedTask):
        """带并发限制的任务执行。"""
        async with self._semaphore:
            task.status = TaskState.RUNNING
            task.started_at = datetime.now().isoformat()
            task._cancel_event = asyncio.Event()

            # 发布状态变化
            try:
                from .event_bus import get_event_bus
                bus = get_event_bus()
                bus.emit_phase_change(task.task_id, "running", "任务开始执行")
            except Exception:
                pass

            try:
                coro = task.coro_factory()
                task.result = await coro
                task.status = TaskState.COMPLETED
                task.completed_at = datetime.now().isoformat()

                try:
                    from .event_bus import get_event_bus
                    bus = get_event_bus()
                    bus.emit_completed(task.task_id, "任务执行完成")
                except Exception:
                    pass

                logger.info(f"[TaskManager] task {task.task_id} completed")

            except asyncio.CancelledError:
                task.status = TaskState.CANCELLED
                task.completed_at = datetime.now().isoformat()
                logger.info(f"[TaskManager] task {task.task_id} cancelled")

            except Exception as e:
                task.status = TaskState.FAILED
                task.error = str(e)
                task.completed_at = datetime.now().isoformat()

                try:
                    from .event_bus import get_event_bus
                    bus = get_event_bus()
                    bus.emit_failed(task.task_id, f"任务失败: {e}")
                except Exception:
                    pass

                logger.error(f"[TaskManager] task {task.task_id} failed: {e}")

    def cancel(self, task_id: str) -> bool:
        """取消任务。"""
        task = self._tasks.get(task_id)
        if not task:
            return False
        return task.cancel()

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态。"""
        task = self._tasks.get(task_id)
        if not task:
            return None
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error": task.error,
        }

    def list_tasks(self, status: Optional[TaskState] = None) -> List[Dict[str, Any]]:
        """列出所有任务。"""
        tasks = self._tasks.values()
        if status:
            tasks = [t for t in tasks if t.status == status]
        return [self.get_status(t.task_id) for t in tasks]

    def cleanup(self, max_age_seconds: int = 3600):
        """清理已完成的旧任务。"""
        now = time.time()
        to_remove = []
        for task_id, task in self._tasks.items():
            if task.status in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                if task.completed_at:
                    try:
                        completed = datetime.fromisoformat(task.completed_at)
                        age = (datetime.now() - completed).total_seconds()
                        if age > max_age_seconds:
                            to_remove.append(task_id)
                    except Exception:
                        pass
        for task_id in to_remove:
            del self._tasks[task_id]
            logger.debug(f"[TaskManager] cleaned up task {task_id}")

    @property
    def active_count(self) -> int:
        """当前活跃任务数。"""
        return sum(1 for t in self._tasks.values() if t.status == TaskState.RUNNING)

    @property
    def pending_count(self) -> int:
        """等待中的任务数。"""
        return sum(1 for t in self._tasks.values() if t.status == TaskState.PENDING)


# 全局单例
_manager: Optional[AsyncTaskManager] = None


def get_task_manager(max_concurrent: int = 3) -> AsyncTaskManager:
    global _manager
    if _manager is None:
        _manager = AsyncTaskManager(max_concurrent=max_concurrent)
    return _manager
