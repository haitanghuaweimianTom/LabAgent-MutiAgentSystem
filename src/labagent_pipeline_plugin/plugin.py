"""PipelinePlugin - profile-driven 7-step pipeline with step pruning.

Reads a profile YAML and emits step/start + step/end for the steps the
profile declares. Steps not in the profile are skipped entirely.

Two modes:
  - `step_runners` dict: caller injects async callables per step name
    (default: stub runners that return a placeholder result)
  - profile + run_problem: the plug-and-play entry point
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import yaml

from labagent.plugin import Context

logger = logging.getLogger(__name__)

# Default step set if profile doesn't declare any.
DEFAULT_STEPS = ["research", "debate", "modeling", "code", "writing", "review", "compile"]


def _default_runner(step: str) -> Callable[[dict[str, Any], Context], Awaitable[dict[str, Any]]]:
    async def runner(payload, ctx):
        return {"step": step, "ok": True}
    return runner


class PipelinePlugin:
    name = "pipeline"
    inject = []

    def __init__(
        self,
        profile_path: Optional[Path | str] = None,
        step_runners: Optional[dict[str, Callable]] = None,
    ) -> None:
        self._profile_path = Path(profile_path) if profile_path else None
        self._steps: list[str] = list(DEFAULT_STEPS)
        self._step_runners: dict[str, Callable] = dict(step_runners or {})
        self._ctx: Optional[Context] = None
        self._results: dict[str, Any] = {}

        if self._profile_path and self._profile_path.exists():
            self._load_profile()

    @property
    def steps(self) -> list[str]:
        return list(self._steps)

    @property
    def results(self) -> dict[str, Any]:
        return dict(self._results)

    def _load_profile(self) -> None:
        data = yaml.safe_load(self._profile_path.read_text(encoding="utf-8")) or {}
        name = data.get("name", "default")
        steps = data.get("steps")
        if steps:
            self._steps = list(steps)
        logger.info("pipeline: loaded profile %r with %d steps", name, len(self._steps))

    def setup(self, ctx: Context) -> None:
        self._ctx = ctx
        logger.info("pipeline plugin: ready (steps=%s)", self._steps)

    async def run(self, problem: str, *, run_id: str = "run") -> dict[str, Any]:
        """Execute the profile-declared step sequence.

        Emits session/start, step/start, step/end (per step), session/end.
        Each step's output is stored in self.results.
        """
        ctx = self._ctx
        assert ctx is not None, "call setup(ctx) first"
        ctx.emit("session/start", {"run_id": run_id, "problem": problem})

        for step in self._steps:
            ctx.emit("step/start", {"step": step, "run_id": run_id})
            start = time.time()
            try:
                runner = self._step_runners.get(step, _default_runner(step))
                payload = {"step": step, "problem": problem, "run_id": run_id}
                result = await runner(payload, ctx)
                tokens = int(result.get("tokens", 0) or 0) if isinstance(result, dict) else 0
            except Exception as e:
                logger.exception("pipeline: step %s failed", step)
                result = {"error": str(e), "step": step}
                tokens = 0
            duration = time.time() - start
            self._results[step] = result
            ctx.emit("step/end", {
                "step": step,
                "run_id": run_id,
                "result": result,
                "duration_s": round(duration, 4),
                "tokens": tokens,
            })

        ctx.emit("session/end", {
            "run_id": run_id,
            "stage_results": self._stage_results(),
        })
        return self._results

    def _stage_results(self) -> dict[str, dict[str, Any]]:
        """Adapt self.results to the shape extract_lessons expects."""
        out: dict[str, dict[str, Any]] = {}
        for step, res in self._results.items():
            if isinstance(res, dict):
                err = res.get("error")
                out[step] = {
                    "status": "failed" if err else "completed",
                    "error": err or "",
                    "score": res.get("score"),
                    "duration": res.get("duration_s"),
                }
            else:
                out[step] = {"status": "completed"}
        return out
