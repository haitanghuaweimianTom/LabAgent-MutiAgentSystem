"""CostGuardPlugin - abort the run when cumulative tokens exceed a budget."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from labagent.plugin import Context

logger = logging.getLogger(__name__)


class CostGuardPlugin:
    name = "cost_guard"
    inject = []

    def __init__(self, max_tokens: int = 1_000_000, out_dir: Optional[Path | str] = None) -> None:
        self._max = max_tokens
        self._total = 0
        self._aborted = False
        self._out_dir = Path(out_dir) if out_dir else (Path.cwd() / ".cost_guard")
        self._ctx: Optional[Context] = None

    @property
    def total_tokens(self) -> int:
        return self._total

    @property
    def aborted(self) -> bool:
        return self._aborted

    def check(self, current_total: int) -> bool:
        """Return True if `current_total` reaches or exceeds the budget."""
        return current_total >= self._max

    def setup(self, ctx: Context) -> None:
        self._ctx = ctx
        self._out_dir.mkdir(parents=True, exist_ok=True)
        ctx.on("step/end", lambda p: self._on_step_end(p))
        logger.info("cost-guard plugin: ready (max_tokens=%d)", self._max)

    def _on_step_end(self, p: dict[str, Any]) -> None:
        if self._aborted:
            return
        spent = int(p.get("tokens", 0) or 0)
        self._total += spent
        if self._total >= self._max:
            self._aborted = True
            payload = {
                "total_tokens": self._total,
                "limit": self._max,
                "last_step": p.get("step"),
            }
            self._ctx.emit("cost/abort", payload)
            logger.warning(
                "cost-guard: ABORT — total=%d > limit=%d (last step=%s)",
                self._total, self._max, p.get("step"),
            )
