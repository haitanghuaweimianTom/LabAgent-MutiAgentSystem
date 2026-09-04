"""Context - the world each plugin sees.

Wraps an EventBus + a service registry. Plugins access services via:
  - attribute proxy: ctx.logger
  - lazy lookup: ctx.get("logger")
  - delayed injection: ctx.inject(["logger"], lambda c: ...)
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .event_bus import EventBus
from .disposer import DisposerHandle


class Context:
    """Per-plugin execution context. One Context per host (shared by all plugins)."""

    def __init__(self) -> None:
        self._bus = EventBus()
        self._services: dict[str, Any] = {}
        self._disposers: list[DisposerHandle] = []
        self._pending_injects: list[tuple[list[str], Callable]] = []

    # --- Service registry ---

    def register(self, name: str, service: Any) -> None:
        """Provide a service to other plugins."""
        self._services[name] = service

    def get(self, name: str) -> Optional[Any]:
        """Look up a service; None if missing (use with care)."""
        return self._services.get(name)

    def require(self, name: str) -> Any:
        """Like get() but raises KeyError if missing."""
        if name not in self._services:
            raise KeyError(f"required service {name!r} not registered")
        return self._services[name]

    def __getattr__(self, name: str) -> Any:
        # Called only if the attribute is not found normally
        # Provides ctx.<service> sugar.
        services = self.__dict__.get("_services", {})
        if name in services:
            return services[name]
        raise AttributeError(
            f"Context has no service or attribute {name!r}. "
            f"Available: {sorted(services.keys())}"
        )

    # --- Delayed dependency injection (Cordis-style) ---

    def inject(self, names: list[str], callback: Callable) -> None:
        """Register a callback that runs once all named services are available.

        Useful for circular deps: A declares inject on B; B declares inject on
        A. Both register deferred work via inject(); host resolves when ready.
        """
        if all(n in self._services for n in names):
            callback(self)
        else:
            self._pending_injects.append((names, callback))

    def resolve_pending_injects(self) -> None:
        """Called by host after a service is registered; flushes ready callbacks."""
        still_pending = []
        for names, callback in self._pending_injects:
            if all(n in self._services for n in names):
                callback(self)
            else:
                still_pending.append((names, callback))
        self._pending_injects = still_pending

    # --- Reversible effects ---

    def effect(self, cleanup: Callable[[], None]) -> DisposerHandle:
        """Register a reversible side-effect. Unload runs cleanup() in LIFO order."""
        handle = DisposerHandle(cleanup)
        self._disposers.append(handle)
        return handle

    def shutdown(self) -> None:
        """Dispose all effects in reverse order. Idempotent."""
        for handle in reversed(self._disposers):
            handle.dispose()
        self._disposers.clear()

    # --- Event bus proxy (5-mode) ---

    def on(self, name: str, listener, *, prepend: bool = False) -> DisposerHandle:
        handle = self._bus.on(name, listener, prepend=prepend)
        # Track listener-registration disposers so ctx.shutdown() and
        # PluginManager unload() can reverse them too.
        self._disposers.append(handle)
        return handle

    def emit(self, name: str, payload: Any = None) -> None:
        self._bus.emit(name, payload)

    async def parallel(self, name: str, payload: Any = None) -> list:
        return await self._bus.parallel(name, payload)

    async def serial(self, name: str, payload: Any = None) -> Any:
        return await self._bus.serial(name, payload)

    def bail(self, name: str, payload: Any = None) -> Any:
        return self._bus.bail(name, payload)

    async def waterfall(self, name: str, *args: Any) -> Any:
        return await self._bus.waterfall(name, *args)
