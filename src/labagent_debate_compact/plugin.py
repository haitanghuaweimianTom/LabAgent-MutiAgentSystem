"""CompactDebatePlugin - 3-persona lightweight debate (vs EnhancedDebate's 6).

Replaces the default 6-persona debate with a 3-persona version, cutting cost
and latency in half for users who don't need the full 6-perspective debate.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from labagent.plugin import Context

logger = logging.getLogger(__name__)


COMPACT_PERSONAS = [
    {
        "name": "planner",
        "weight": 1.2,
        "system": "你是策略规划者。给出任务分解、优先级和可执行路径。",
    },
    {
        "name": "critic",
        "weight": 1.3,
        "system": "你是质量评审员。找出方案的问题、风险和遗漏。",
    },
    {
        "name": "implementer",
        "weight": 1.1,
        "system": "你是实现者。给出具体的执行步骤、代码要点和验证方法。",
    },
]


class _CompactDebate:
    """Minimal 3-persona debate. Replaces the default 6-persona EnhancedDebate."""

    persona_count = 3

    def __init__(self, llm_call: Callable, personas: list[dict[str, Any]] = None,
                 rounds: int = 2) -> None:
        self._llm = llm_call
        self.personas = personas or COMPACT_PERSONAS
        self._rounds = rounds

    async def debate(self, topic: str, context: str = "") -> dict[str, Any]:
        """Async debate: each persona speaks, then a short synthesis."""
        opinions = []
        for persona in self.personas:
            sys_msg = persona["system"]
            user_msg = f"【议题】{topic}\n【背景】{context[:2000]}"
            try:
                resp = await self._maybe_async_call(sys_msg, user_msg)
                opinions.append({"persona": persona["name"], "content": resp.get("content", "")})
            except Exception as e:
                logger.warning("compact-debate: %s failed: %s", persona["name"], e)
        # crude synthesis: last opinion wins (real implementation would
        # call an LLM to merge). Keep it dependency-free.
        return {
            "synthesis": opinions[-1]["content"] if opinions else "",
            "opinions": opinions,
            "persona_count": len(self.personas),
            "rounds": self._rounds,
        }

    async def _maybe_async_call(self, sys_msg, user_msg):
        resp = self._llm(sys_msg, user_msg, 8000)
        if hasattr(resp, "__await__"):
            return await resp
        return resp


class CompactDebatePlugin:
    name = "debate_compact"
    inject = ["llm_call"]

    def __init__(self, rounds: int = 2) -> None:
        self._rounds = rounds
        self._personas = COMPACT_PERSONAS

    @property
    def personas(self) -> list[dict[str, Any]]:
        return list(self._personas)

    def setup(self, ctx: Context) -> None:
        llm = ctx.require("llm_call")
        ctx.register("debate", _CompactDebate(llm, personas=self._personas, rounds=self._rounds))
        logger.info("compact-debate plugin: ready (3 personas, %d rounds)", self._rounds)
