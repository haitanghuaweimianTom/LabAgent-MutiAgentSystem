"""CircuitBreaker 熔断器测试（v5.3）。

用户担忧：「我的 key 在不停调用，应自动停止，调用 10 次没成功就暂停」。

验证：
1. CLOSED → OPEN：连续 N 次失败触发熔断
2. OPEN：拒绝所有请求（抛 CircuitOpenError）
3. HALF_OPEN：冷却时间到后允许试探
4. HALF_OPEN 试探成功 → CLOSED（恢复）
5. HALF_OPEN 试探失败 → OPEN（重新冷却）
6. 滑动窗口：窗口外的失败不计入
7. 任务级隔离：一个任务熔断不影响其他任务
8. reset() 手动恢复
"""
import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    get_breaker,
    remove_breaker,
    reset_all,
)


# ==================== 1. CLOSED → OPEN ====================

def test_closed_to_open_after_threshold_failures():
    """连续 N 次失败后，熔断器应打开。"""
    cb = CircuitBreaker("test1", CircuitBreakerConfig(
        failure_threshold=3,
        window_seconds=60,
    ))
    assert cb.state == CircuitBreaker.CLOSED

    cb.record_failure()
    assert cb.state == CircuitBreaker.CLOSED  # 1 次不够
    cb.record_failure()
    assert cb.state == CircuitBreaker.CLOSED  # 2 次不够
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN  # 3 次触发熔断


def test_open_rejects_requests():
    """OPEN 状态下 allow_request 返回 False，check_or_raise 抛 CircuitOpenError。"""
    cb = CircuitBreaker("test2", CircuitBreakerConfig(failure_threshold=2))
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN

    assert not cb.allow_request()
    with pytest.raises(CircuitOpenError) as exc_info:
        cb.check_or_raise()
    assert exc_info.value.name == "test2"
    assert exc_info.value.retry_after_sec > 0


# ==================== 2. 成功重置 ====================

def test_success_in_closed_clears_failures():
    """CLOSED 状态下成功应清空滑动窗口里的失败记录。"""
    cb = CircuitBreaker("test3", CircuitBreakerConfig(
        failure_threshold=3,
        window_seconds=60,
    ))
    cb.record_failure()
    cb.record_failure()
    assert len(cb._failures) == 2

    cb.record_success()
    assert len(cb._failures) == 0  # 成功清空
    assert cb.state == CircuitBreaker.CLOSED


# ==================== 3. HALF_OPEN 转换 ====================

def test_open_to_half_open_after_cool_down():
    """OPEN 状态冷却时间到后转为 HALF_OPEN。"""
    cb = CircuitBreaker("test4", CircuitBreakerConfig(
        failure_threshold=1,
        open_duration_seconds=0.1,  # 100ms 冷却（测试加速）
    ))
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN

    time.sleep(0.15)  # 等冷却
    cb.allow_request()  # 触发状态转移
    assert cb.state == CircuitBreaker.HALF_OPEN


def test_half_open_probe_success_returns_to_closed():
    """HALF_OPEN 试探成功 → CLOSED。"""
    cb = CircuitBreaker("test5", CircuitBreakerConfig(
        failure_threshold=1,
        open_duration_seconds=0.05,
    ))
    cb.record_failure()
    time.sleep(0.1)
    cb.allow_request()
    assert cb.state == CircuitBreaker.HALF_OPEN

    cb.record_success()
    assert cb.state == CircuitBreaker.CLOSED
    assert len(cb._failures) == 0


def test_half_open_probe_failure_returns_to_open():
    """HALF_OPEN 试探失败 → OPEN（重置冷却时间）。"""
    cb = CircuitBreaker("test6", CircuitBreakerConfig(
        failure_threshold=1,
        open_duration_seconds=0.05,
    ))
    cb.record_failure()
    time.sleep(0.1)
    cb.allow_request()
    assert cb.state == CircuitBreaker.HALF_OPEN

    cb.record_failure()  # 试探失败
    assert cb.state == CircuitBreaker.OPEN

    # 冷却时间应被重置（不是原冷却时间的剩余）
    assert cb._state_since > 0


# ==================== 4. 滑动窗口 ====================

def test_window_prunes_old_failures():
    """滑动窗口外的失败不应计入（避免历史失败永久影响）。"""
    cb = CircuitBreaker("test7", CircuitBreakerConfig(
        failure_threshold=3,
        window_seconds=0.1,  # 100ms 窗口
    ))
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.15)  # 等待窗口过期
    cb.record_failure()  # 这一次的失败应该让窗口只有 1 个失败
    cb.record_failure()
    assert cb.state == CircuitBreaker.CLOSED  # 窗口里只有 2 个，不够阈值

    cb.record_failure()  # 第 3 个失败（在窗口内）→ 触发熔断
    assert cb.state == CircuitBreaker.OPEN


# ==================== 5. 任务级隔离 ====================

def test_per_task_breaker_isolation():
    """每个 task 独立熔断 —— 一个任务熔断不影响其他任务。"""
    cb_a = get_breaker("task_a")
    cb_b = get_breaker("task_b")

    cb_a._failures.extend([time.time()] * 10)  # task_a 熔断
    # 触发熔断
    for _ in range(10):
        cb_a.record_failure()
    assert cb_a.state == CircuitBreaker.OPEN
    assert cb_b.state == CircuitBreaker.CLOSED, "task_b 不应受 task_a 影响"

    # 清理
    remove_breaker("task_a")
    remove_breaker("task_b")


def test_get_breaker_returns_same_instance():
    """get_breaker 同 task_id 返回同一实例。"""
    cb1 = get_breaker("task_same")
    cb2 = get_breaker("task_same")
    assert cb1 is cb2
    remove_breaker("task_same")


def test_reset_all_clears_all_breakers():
    """reset_all 清空所有熔断器（运维重启用）。"""
    cb = get_breaker("task_reset")
    cb._failures.extend([time.time()] * 10)
    cb.record_failure()  # 触发熔断
    assert cb.state == CircuitBreaker.OPEN

    reset_all()
    new_cb = get_breaker("task_reset")  # 新实例
    assert new_cb.state == CircuitBreaker.CLOSED
    remove_breaker("task_reset")


# ==================== 6. 手动 reset ====================

def test_manual_reset_recovers_from_open():
    """手动 reset 让熔断器回到 CLOSED（不需等冷却）。"""
    cb = CircuitBreaker("test8", CircuitBreakerConfig(failure_threshold=1))
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN

    cb.reset()
    assert cb.state == CircuitBreaker.CLOSED
    assert len(cb._failures) == 0


# ==================== 7. on_open 回调 ====================

def test_on_open_callback_fires_when_circuit_opens():
    """触发熔断时应通知回调（让 Orchestrator 标记 task failed）。"""
    callback_called = []

    def on_open(breaker):
        callback_called.append(breaker.name)

    cb = CircuitBreaker("test9", CircuitBreakerConfig(
        failure_threshold=2,
        on_open_callback=on_open,
    ))
    cb.record_failure()
    assert callback_called == []  # 未触发
    cb.record_failure()
    assert callback_called == ["test9"]  # 触发熔断 → 回调


def test_on_open_callback_swallows_exceptions():
    """on_open_callback 内部异常不应影响熔断器自身状态。"""
    def bad_callback(breaker):
        raise RuntimeError("callback error")

    cb = CircuitBreaker("test10", CircuitBreakerConfig(
        failure_threshold=1,
        on_open_callback=bad_callback,
    ))
    cb.record_failure()  # 不应抛异常
    assert cb.state == CircuitBreaker.OPEN


# ==================== 8. 统计信息 ====================

def test_stats_exposes_state_and_counts():
    """stats 必须包含 name / state / threshold / counts。"""
    cb = CircuitBreaker("test11", CircuitBreakerConfig(failure_threshold=5))
    cb.record_failure()
    cb.record_success()
    cb.record_failure()

    stats = cb.stats
    assert stats["name"] == "test11"
    assert stats["state"] == CircuitBreaker.CLOSED
    assert stats["threshold"] == 5
    assert stats["total_failures"] == 2
    assert stats["total_successes"] == 1


# ==================== 9. 集成：模拟 LLM key 失效场景 ====================

def test_simulation_api_key_invalid():
    """模拟场景：用户 API key 失效，连续 10 次 LLM 调用全部失败。

    验证：第 10 次后熔断器打开，第 11 次直接抛 CircuitOpenError
    （避免 key 被无限刷爆）。
    """
    cb = CircuitBreaker(
        "production",
        CircuitBreakerConfig(failure_threshold=10),
    )

    # 模拟 10 次连续失败
    for i in range(10):
        try:
            cb.check_or_raise()  # 前 9 次允许
            if i < 9:
                # 模拟 LLM 调用失败
                cb.record_failure()
        except CircuitOpenError:
            pytest.fail(f"第 {i+1} 次就熔断了，阈值应该是 10")

    # 第 10 次失败应触发熔断
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN

    # 第 11 次调用必须被拒绝
    with pytest.raises(CircuitOpenError) as exc_info:
        cb.check_or_raise()
    assert exc_info.value.retry_after_sec > 0

    # 用户看到清晰的错误信息
    assert "OPEN" in str(exc_info.value)
    assert "production" in str(exc_info.value)


# ==================== 10. 异步支持 ====================

@pytest.mark.asyncio
async def test_async_concurrent_calls_respect_breaker():
    """并发异步调用：熔断应线程安全（不超阈值就 OPEN）。"""
    cb = CircuitBreaker("test_async", CircuitBreakerConfig(failure_threshold=5))

    async def call_llm():
        cb.check_or_raise()
        cb.record_failure()
        return "ok"

    # 并发 10 次失败 —— 全部应被记账，但熔断只开一次
    results = await asyncio.gather(
        *[call_llm() for _ in range(10)],
        return_exceptions=True,
    )
    # 至少一次失败后熔断，后续 CircuitOpenError
    open_errors = [r for r in results if isinstance(r, CircuitOpenError)]
    failures = [r for r in results if r == "ok"]
    assert len(open_errors) > 0, "应至少有一个 CircuitOpenError"
    assert len(open_errors) + len(failures) == 10
    assert cb.state == CircuitBreaker.OPEN
