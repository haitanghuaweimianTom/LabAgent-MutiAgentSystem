"""Disposer handle for reversible effects.

DSH 不变式：所有 ctx 注册必须有 disposer，unload/重载时按逆序 unwind。
"""

from __future__ import annotations

from typing import Callable


class DisposerHandle:
    """A handle to a registered effect that can be disposed exactly once.

    Calling dispose() multiple times is safe — only the first call runs cleanup.
    This is critical for plugin unload because disposing listeners twice could
    unregister a callback that's already been swapped, causing runtime errors.
    """

    def __init__(self, cleanup: Callable[[], None]) -> None:
        self._cleanup = cleanup
        self._disposed = False

    def dispose(self) -> None:
        if not self._disposed:
            try:
                self._cleanup()
            finally:
                self._disposed = True

    @property
    def disposed(self) -> bool:
        return self._disposed
