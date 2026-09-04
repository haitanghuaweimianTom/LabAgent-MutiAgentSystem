"""DebatePlugin - wraps the existing enhanced_debate module."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from labagent.plugin import Context

logger = logging.getLogger(__name__)


class DebatePlugin:
    name = "debate"
    inject = ["llm_call", "session_log"]

    def __init__(self, rounds: int = 2) -> None:
        self._rounds = rounds

    def setup(self, ctx: Context) -> None:
        llm_call: Callable = ctx.require("llm_call")
        ctx.require("session_log")
        from enhanced_debate import EnhancedDebate

        debate = EnhancedDebate(call_fn=llm_call, rounds=self._rounds)
        ctx.register("debate", debate)
        logger.info("debate plugin: ready")
