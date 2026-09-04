"""HelloPlugin - canonical example of a labagent plugin.

Demonstrates the full plugin contract:
  - declares `name` and `inject`
  - implements `setup(ctx)`
  - subscribes to step lifecycle events
  - writes to the session log
  - could register a service for downstream plugins

Authoring a new plugin in the same style:
  1. copy this package
  2. change `name` and `inject`
  3. add your own handlers in `setup(ctx)`
  4. ship as a pip package (declare entry_point) or drop into ./plugins/ as a directory
"""

from __future__ import annotations

import logging
from typing import Any

from labagent.plugin import (
    Context,
    EventKind,
    SessionLog,
)

logger = logging.getLogger(__name__)


class HelloPlugin:
    """Minimal plugin: logs every step start/end into the session log.

    Host services required (declared via `inject`):
      - `session_log`: a SessionLog instance to write events to
    """

    name = "hello"
    inject = ["session_log"]

    def setup(self, ctx: Context) -> None:
        log = ctx.require("session_log")
        self._log = log
        # Subscribe to step lifecycle; persist into the session log.
        ctx.on("step/start", lambda p: self._on_step_start(p))
        ctx.on("step/end", lambda p: self._on_step_end(p))
        logger.info(f"hello plugin: installed handlers on ctx={ctx!r}")

    def _on_step_start(self, payload: dict[str, Any]) -> None:
        self._log.append(
            EventKind.STEP_START,
            {"step": payload.get("step"), "name": payload.get("name")},
        )

    def _on_step_end(self, payload: dict[str, Any]) -> None:
        self._log.append(
            EventKind.STEP_END,
            {"step": payload.get("step"), "result": payload.get("result", "ok")},
        )
