"""QualityPlugin - wraps the existing iterative_quality_gate module."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from labagent.plugin import Context

logger = logging.getLogger(__name__)


class QualityPlugin:
    name = "quality"
    inject = ["session_log"]

    def __init__(self, state_dir: Optional[Path | str] = None) -> None:
        self._state_dir = state_dir

    def setup(self, ctx: Context) -> None:
        ctx.require("session_log")
        from iterative_quality_gate import IterativeQualityGate

        gate = IterativeQualityGate(self._state_dir or (Path.cwd() / ".quality_gate"))
        ctx.register("quality_gate", gate)
        logger.info("quality plugin: ready")
