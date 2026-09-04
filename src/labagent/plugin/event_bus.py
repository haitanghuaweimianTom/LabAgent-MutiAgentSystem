"""5-mode event bus: emit/parallel/serial/bail/waterfall.

DSH 5-mode 总线复刻。waterfall 模式是拦截/改写的主战场：
listener 收 (args..., next_fn)，调 next() 透传；不调即 veto。
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable

from .disposer import DisposerHandle

Listener = Callable[..., Any]


class EventBus:
    """The 5-mode event bus shared by all plugins on a single Context.

    Modes:
      - emit(name, payload): fire-and-forget notification; returns immediately.
      - parallel(name, payload): await all listeners concurrently; returns list.
      - serial(name, payload): await listeners in order, return first non-None.
      - bail(name, payload): synchronous serial, return first non-None.
      - waterfall(name, *args): chain middleware; listener may call next() or veto.

    All listeners are auto-detected for sync/async. Async listeners are awaited
    in all modes. waterfall always returns an awaitable (call with `await`).
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = {}

    def on(
        self,
        name: str,
        listener: Listener,
        *,
        prepend: bool = False,
    ) -> DisposerHandle:
        """Register a listener. Returns a handle that can dispose the registration."""
        if prepend:
            self._listeners.setdefault(name, []).insert(0, listener)
        else:
            self._listeners.setdefault(name, []).append(listener)

        def _cleanup() -> None:
            try:
                self._listeners[name].remove(listener)
            except (KeyError, ValueError):
                pass

        return DisposerHandle(_cleanup)

    @staticmethod
    def _is_async(listener: Listener) -> bool:
        return inspect.iscoroutinefunction(listener)

    @staticmethod
    async def _call(listener: Listener, *args: Any) -> Any:
        """Call a listener, awaiting if async."""
        result = listener(*args)
        if inspect.isawaitable(result):
            return await result
        return result

    def emit(self, name: str, payload: Any = None) -> None:
        """Fire-and-forget. Sync listeners called immediately; async are scheduled.

        Returns immediately (does not block). Errors in one listener don't break
        the others.
        """
        listeners = list(self._listeners.get(name, []))
        for listener in listeners:
            try:
                if self._is_async(listener):
                    # Schedule async listener
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(listener(payload))
                    except RuntimeError:
                        # No running loop — try asyncio.run, best-effort
                        try:
                            asyncio.run(listener(payload))
                        except Exception:
                            import traceback
                            traceback.print_exc()
                else:
                    listener(payload)
            except Exception:
                import traceback
                traceback.print_exc()

    async def parallel(self, name: str, payload: Any = None) -> list:
        """Run all listeners concurrently. Returns list of results."""
        coros = [self._call(listener, payload) for listener in self._listeners.get(name, [])]
        return await asyncio.gather(*coros) if coros else []

    async def serial(self, name: str, payload: Any = None) -> Any:
        """Run listeners in order; return first non-None result."""
        for listener in self._listeners.get(name, []):
            result = await self._call(listener, payload)
            if result is not None:
                return result
        return None

    def bail(self, name: str, payload: Any = None) -> Any:
        """Synchronous version of serial. Refuses async listeners."""
        for listener in self._listeners.get(name, []):
            if self._is_async(listener):
                raise RuntimeError(
                    f"bail() cannot await async listener; use serial() for {name!r}"
                )
            result = listener(payload)
            if result is not None:
                return result
        return None

    async def waterfall(self, name: str, *args: Any) -> Any:
        """Chain middleware. Each listener receives (..., next=callable).

        If a listener returns without calling next(), its return value is
        the final result (veto). If all call next(), the final result is the
        last listener's return.

        Both sync and async listeners are supported. Sync listeners receive a
        `next` callable; the bus runs the rest of the chain inline and returns
        the result when next() is invoked.
        """
        listeners = list(self._listeners.get(name, []))

        async def _chain(idx: int) -> Any:
            if idx >= len(listeners):
                return None
            listener = listeners[idx]
            is_async = self._is_async(listener)

            async def next_fn() -> Any:
                return await _chain(idx + 1)

            if is_async:
                # Pass next as keyword arg (DSH style: keyword-only)
                return await listener(*args, next=next_fn)

            # Sync listener: provide a sync-friendly next
            try:
                asyncio.get_running_loop()
                # Inside running loop — use a fallback that returns awaitable
                class _FallbackNext:
                    def __call__(self_inner):
                        return next_fn()
                return listener(*args, next=_FallbackNext())
            except RuntimeError:
                # No running loop — safe to run synchronously
                class _SyncNext:
                    def __init__(self, awaitable):
                        self._awaitable = awaitable

                    def __call__(self_inner):
                        return asyncio.run(self._awaitable)

                return listener(*args, next=_SyncNext(next_fn()))

        return await _chain(0)
