"""异步速率限制工具"""
import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class AsyncTokenBucket:
    """异步 Token Bucket 速率限制器。

    用法：
        bucket = AsyncTokenBucket(rate=1.0)  # 每秒 1 个 token
        await bucket.acquire()                # 获取 1 个 token，必要时等待
        await bucket.acquire(tokens=5)        # 一次性获取 5 个 token
    """

    def __init__(self, rate: float, capacity: Optional[float] = None):
        """
        Args:
            rate: 每秒产生 token 的速度（tokens/second）。
            capacity: 桶最大容量，默认 rate * 5（允许最多攒 5 秒）。
        """
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.rate = float(rate)
        self.capacity = float(capacity or rate * 5)
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        """获取指定数量的 token，不足时阻塞等待。"""
        if tokens <= 0:
            return
        if tokens > self.capacity:
            raise ValueError(f"requested tokens ({tokens}) exceeds capacity ({self.capacity})")

        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < tokens:
                deficit = tokens - self.tokens
                wait_time = deficit / self.rate
                logger.debug(f"Rate limiter waiting {wait_time:.2f}s for {tokens} tokens")
                await asyncio.sleep(wait_time)
                self.tokens = 0.0
                self.last_update = time.monotonic()
            else:
                self.tokens -= tokens

    async def __aenter__(self) -> "AsyncTokenBucket":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass
