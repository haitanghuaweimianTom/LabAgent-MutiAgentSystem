"""HealerPlugin - wraps the existing self_healer module."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from labagent.plugin import Context

logger = logging.getLogger(__name__)


class HealerPlugin:
    name = "healer"
    inject = ["session_log"]

    def __init__(self, state_dir: Optional[Path | str] = None) -> None:
        self._state_dir = state_dir

    def setup(self, ctx: Context) -> None:
        ctx.require("session_log")
        from self_healer import SelfHealer

        healer = SelfHealer(self._state_dir or (Path.cwd() / ".healer"))
        ctx.register("healer", healer)
        logger.info("healer plugin: ready")
