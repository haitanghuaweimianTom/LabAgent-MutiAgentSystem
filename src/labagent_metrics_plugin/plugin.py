"""MetricsPlugin - per-step timing, tokens, retry counter; writes a run summary JSON."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from labagent.plugin import Context, SessionLog

logger = logging.getLogger(__name__)


class MetricsPlugin:
    name = "metrics"
    inject = ["session_log"]

    def __init__(self, out_dir: Optional[Path | str] = None) -> None:
        self._out_dir = Path(out_dir) if out_dir else (Path.cwd() / ".metrics")
        self._step_starts: dict[str, float] = {}
        self._steps: list[dict[str, Any]] = []
        self._total_tokens = 0
        self._total_retries = 0
        self._ctx: Optional[Context] = None

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    def setup(self, ctx: Context) -> None:
        self._ctx = ctx
        ctx.require("session_log")
        self._out_dir.mkdir(parents=True, exist_ok=True)
        ctx.on("step/start", lambda p: self._on_step_start(p))
        ctx.on("step/end", lambda p: self._on_step_end(p))
        ctx.on("session/end", lambda p: self._on_session_end(p))
        logger.info("metrics plugin: ready (out_dir=%s)", self._out_dir)

    def _on_step_start(self, p: dict[str, Any]) -> None:
        step = p.get("step", "unknown")
        self._step_starts[step] = time.time()

    def _on_step_end(self, p: dict[str, Any]) -> None:
        step = p.get("step", "unknown")
        start = self._step_starts.pop(step, time.time())
        record = {
            "step": step,
            "duration_s": round(time.time() - start, 4),
            "tokens": int(p.get("tokens", 0) or 0),
            "retries": int(p.get("retries", 0) or 0),
        }
        self._total_tokens += record["tokens"]
        self._total_retries += record["retries"]
        self._steps.append(record)

    def _on_session_end(self, p: dict[str, Any]) -> None:
        run_id = p.get("run_id", f"run-{int(time.time())}")
        out_file = self._out_dir / f"{run_id}-metrics.json"
        out_file.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "session_id": (self._ctx.get("session_log").session_id
                                  if self._ctx else None),
                    "total_tokens": self._total_tokens,
                    "total_retries": self._total_retries,
                    "steps": self._steps,
                    "ended_at": time.time(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("metrics plugin: wrote %s (tokens=%d)", out_file, self._total_tokens)
