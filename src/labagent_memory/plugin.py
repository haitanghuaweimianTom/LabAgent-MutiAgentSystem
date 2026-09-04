"""MemoryPlugin - wraps the existing memory_store module."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from labagent.plugin import Context, SessionLog

logger = logging.getLogger(__name__)


class MemoryPlugin:
    name = "memory"
    inject = ["session_log"]

    def __init__(self, store_dir: Optional[Path | str] = None) -> None:
        self._store_dir = store_dir
        self._ctx: Optional[Context] = None

    def setup(self, ctx: Context) -> None:
        self._ctx = ctx
        ctx.require("session_log")
        from memory_store import MemoryStore

        store = MemoryStore(self._store_dir or (Path.cwd() / ".memory"))
        ctx.register("memory_store", store)
        # Persist a per-session summary into memory on session/end
        ctx.on("session/end", lambda p: self._on_session_end(p))
        logger.info("memory plugin: ready")

    def _on_session_end(self, payload: dict[str, Any]) -> None:
        if self._ctx is None:
            return
        log: SessionLog = self._ctx.get("session_log")
        store = self._ctx.get("memory_store")
        if log is None or store is None:
            return
        events = log.read_all()
        if not events:
            return
        summary = f"Session {log.session_id}: {len(events)} events, last kind={events[-1].kind.value}"
        try:
            store.add(
                content=summary,
                category="ideation",
                metadata={"session_id": log.session_id},
                source="plugin:memory",
                tags=[log.session_id],
            )
        except Exception as e:
            logger.warning(f"memory plugin: failed to record summary: {e}")
