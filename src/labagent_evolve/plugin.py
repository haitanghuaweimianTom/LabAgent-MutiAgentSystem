"""EvolutionPlugin - wraps the existing self_evolution + reflection_agent.

This is a thin plugin adapter over the existing modules (no rewrite).
The plugin:
  - injects llm_call and session_log
  - registers `evolution_store` and `reflection_agent` services for downstream
    plugins to consume
  - subscribes to step/end and session/end to extract lessons and reflect
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from labagent.plugin import Context, EventKind, SessionLog

logger = logging.getLogger(__name__)


class EvolutionPlugin:
    name = "evolve"
    inject = ["llm_call", "session_log"]

    def __init__(self, store_dir: Optional[Path | str] = None) -> None:
        self._store_dir = Path(store_dir) if store_dir else None

    def setup(self, ctx: Context) -> None:
        llm_call: Callable = ctx.require("llm_call")
        log: SessionLog = ctx.require("session_log")
        self._log = log
        self._llm = llm_call
        self._ctx = ctx

        # Lazy import of the original modules (kept as-is).
        from self_evolution import EvolutionStore
        from reflection_agent import ReflectionAgent

        # Create the store and agent, expose as services.
        store = EvolutionStore(self._store_dir or (Path.cwd() / ".evolution"))
        agent = ReflectionAgent(llm_fn=llm_call)
        ctx.register("evolution_store", store)
        ctx.register("reflection_agent", agent)

        # Subscribe to session lifecycle.
        ctx.on("session/end", lambda p: self._on_session_end(p))
        logger.info("evolve plugin: ready (store=%s)", store.lessons_path)

    def _on_session_end(self, payload: dict[str, Any]) -> None:
        """End-of-session hook: extract lessons from stage results and persist."""
        from self_evolution import LessonV2, extract_lessons, update_effectiveness

        ctx_payload: dict[str, Any] = payload or {}
        stage_results = ctx_payload.get("stage_results", {})
        if not stage_results:
            return

        # Run the rule-based extractor (cheap; LLM fallback is host-driven).
        lessons = extract_lessons(stage_results, run_id=ctx_payload.get("run_id", ""))
        for lesson in lessons:
            self._log.append(
                EventKind.EVOLUTION_LESSON,
                {
                    "stage": lesson.stage_name,
                    "category": lesson.category,
                    "severity": lesson.severity,
                    "description": lesson.description[:300],
                },
                run_id=ctx_payload.get("run_id", ""),
            )

        # Update effectiveness against existing lessons.
        store = self._ctx.get("evolution_store")
        if store is not None:
            prior = store.load_all()
            current_keys = [l.issue_key for l in lessons if hasattr(l, "issue_key")]
            update_effectiveness(current_keys, prior)
            # Persist the lessons.
            store.append_many(lessons)
