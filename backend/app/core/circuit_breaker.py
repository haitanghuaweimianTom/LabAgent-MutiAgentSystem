"""LLM 调用熔断器（v5.3）。

用户担忧：「我的 key 在不停调用，系统应自动停止，调用 10 次没成功就暂停」。

设计目标：
1. 连续 N 次 LLM 调用失败 → 立即停止任务（避免 key 被刷爆 + 资金浪费）
2. 不把 fallback mock_response 算成功 —— 真失败才算
3. 滑动窗口（避免历史失败永久影响）
4. 触发后冷却 N 分钟半开（half-open）
5. 任务级隔离 —— 一个任务失败不影响其他任务

状态机：
    CLOSED (正常)
       ↓ 连续 N 次失败
    OPEN (熔断，N 分钟内不再调用)
       ↓ 冷却时间到
    HALF_OPEN (允许 1 次试探)
       ↓ 试探成功 → CLOSED
       ↓ 试探失败 → OPEN（重置冷却时间）

公开 API：
    cb = CircuitBreaker(name="main")
    if not cb.allow_request():
        raise CircuitOpenError("circuit open")
    try:
        result = await call_llm()
        cb.record_success()
    except LLMError:
        cb.record_failure()
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

logger = logging.getLogger(__name__)


# ==================== 异常 ====================


class CircuitOpenError(RuntimeError):
    """熔断器已 OPEN，所有请求被拒绝。"""

    def __init__(self, name: str, retry_after_sec: float, message: str = ""):
        self.name = name
        self.retry_after_sec = retry_after_sec
        super().__init__(
            f"[CircuitBreaker:{name}] OPEN: {message or 'too many failures'} "
            f"(retry in {retry_after_sec:.0f}s)"
        )


# ==================== 配置 ====================


@dataclass
class CircuitBreakerConfig:
    """熔断器配置。"""

    # 连续失败 N 次触发熔断（默认 10）
    failure_threshold: int = 10
    # 滑动窗口：只统计最近 N 秒内的失败（默认 30 分钟）
    window_seconds: float = 1800.0
    # OPEN 状态持续时间（默认 5 分钟）
    open_duration_seconds: float = 300.0
    # HALF_OPEN 状态允许的试探次数（默认 1）
    half_open_max_probes: int = 1
    # 触发熔断时是否调用回调（让 Orchestrator 标记 task failed）
    on_open_callback: Optional[callable] = None


# ==================== 熔断器 ====================


class CircuitBreaker:
    """单实例熔断器（线程安全）。"""

    # 状态枚举
    CLOSED = "closed"          # 正常
    OPEN = "open"              # 熔断
    HALF_OPEN = "half_open"    # 半开（试探）

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = self.CLOSED
        self._state_since: float = time.time()  # 当前状态开始时间
        self._failures: Deque[float] = deque()  # 滑动窗口内失败时间戳
        self._successes: int = 0  # HALF_OPEN 期成功计数（达阈值 → CLOSED）
        self._total_failures: int = 0  # 累计失败（用于指标）
        self._total_successes: int = 0
        self._lock = threading.RLock()

    # ----- 状态查询 -----

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def stats(self) -> dict:
        with self._lock:
            now = time.time()
            self._prune_failures(now)
            return {
                "name": self.name,
                "state": self._state,
                "state_since": self._state_since,
                "recent_failures": len(self._failures),
                "threshold": self.config.failure_threshold,
                "total_failures": self._total_failures,
                "total_successes": self._total_successes,
                "time_until_half_open": max(
                    0, self._state_since + self.config.open_duration_seconds - now
                ) if self._state == self.OPEN else 0,
            }

    # ----- 请求许可 -----

    def allow_request(self) -> bool:
        """检查是否允许发起请求。

        True：可调用（CLOSED 或 HALF_OPEN）
        False：熔断中（OPEN）
        """
        with self._lock:
            self._maybe_transition()
            return self._state in (self.CLOSED, self.HALF_OPEN)

    def check_or_raise(self):
        """不允许时直接抛 CircuitOpenError。"""
        with self._lock:
            self._maybe_transition()
            if self._state == self.OPEN:
                retry_after = max(
                    0, self._state_since + self.config.open_duration_seconds - time.time()
                )
                raise CircuitOpenError(self.name, retry_after)

    # ----- 状态转移 -----

    def record_success(self):
        """记录一次成功（可能触发 CLOSED 或保持）。"""
        with self._lock:
            self._total_successes += 1
            if self._state == self.HALF_OPEN:
                # 试探成功 → 立即回到 CLOSED
                logger.info(
                    f"[CircuitBreaker:{self.name}] HALF_OPEN probe succeeded → CLOSED"
                )
                self._transition(self.CLOSED)
                self._failures.clear()
            elif self._state == self.CLOSED:
                # 成功时清空滑动窗口里的旧失败（避免累积）
                self._failures.clear()

    def record_failure(self):
        """记录一次失败（可能触发 OPEN）。"""
        with self._lock:
            self._total_failures += 1
            now = time.time()
            self._failures.append(now)
            self._prune_failures(now)

            if self._state == self.HALF_OPEN:
                # 试探失败 → 重置冷却时间
                logger.warning(
                    f"[CircuitBreaker:{self.name}] HALF_OPEN probe failed → OPEN"
                )
                self._transition(self.OPEN)
                self._fire_open_callback()
                return

            if self._state == self.CLOSED:
                # 检查是否超阈值
                if len(self._failures) >= self.config.failure_threshold:
                    logger.error(
                        f"[CircuitBreaker:{self.name}] CLOSED → OPEN: "
                        f"{len(self._failures)} failures within {self.config.window_seconds}s"
                    )
                    self._transition(self.OPEN)
                    self._fire_open_callback()

    # ----- 内部 -----

    def _maybe_transition(self):
        """根据时间自动 OPEN → HALF_OPEN。"""
        if self._state != self.OPEN:
            return
        now = time.time()
        if now >= self._state_since + self.config.open_duration_seconds:
            logger.info(
                f"[CircuitBreaker:{self.name}] OPEN → HALF_OPEN (cool-down expired)"
            )
            self._transition(self.HALF_OPEN)

    def _transition(self, new_state: str):
        self._state = new_state
        self._state_since = time.time()
        self._successes = 0

    def _prune_failures(self, now: float):
        """清理滑动窗口外的失败记录。"""
        cutoff = now - self.config.window_seconds
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def _fire_open_callback(self):
        """触发熔断时通知 Orchestrator 标记任务 failed。"""
        cb = self.config.on_open_callback
        if cb:
            try:
                cb(self)
            except Exception as exc:
                logger.warning(
                    f"[CircuitBreaker:{self.name}] on_open_callback failed: {exc}"
                )

    # ----- 手动控制 -----

    def reset(self):
        """手动重置（运维用）。"""
        with self._lock:
            logger.info(f"[CircuitBreaker:{self.name}] manual reset")
            self._transition(self.CLOSED)
            self._failures.clear()


# ==================== 全局单例（任务级隔离）====================


_global_breakers: dict = {}  # task_id → CircuitBreaker
_lock = threading.RLock()


def get_breaker(
    task_id: str,
    config: Optional[CircuitBreakerConfig] = None,
) -> CircuitBreaker:
    """获取或创建任务的熔断器。

    每个任务独立 —— 一个任务熔断不影响其他任务。
    """
    with _lock:
        if task_id not in _global_breakers:
            _global_breakers[task_id] = CircuitBreaker(
                name=f"task_{task_id}",
                config=config or CircuitBreakerConfig(),
            )
            logger.info(f"[CircuitBreaker] created breaker for task {task_id}")
        return _global_breakers[task_id]


def remove_breaker(task_id: str):
    """任务结束后清理（释放内存）。"""
    with _lock:
        _global_breakers.pop(task_id, None)


def reset_all():
    """重置所有熔断器（运维用，重启时调用）。"""
    with _lock:
        _global_breakers.clear()
