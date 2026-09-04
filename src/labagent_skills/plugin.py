"""SkillsPlugin - wraps the existing skill_library module."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from labagent.plugin import Context

logger = logging.getLogger(__name__)


class SkillsPlugin:
    name = "skills"
    inject = ["session_log"]

    def __init__(self, store_dir: Optional[Path | str] = None) -> None:
        self._store_dir = store_dir

    def setup(self, ctx: Context) -> None:
        ctx.require("session_log")
        from skill_library import SkillLibrary

        lib = SkillLibrary(self._store_dir or (Path.cwd() / ".skills"))
        ctx.register("skill_library", lib)
        logger.info("skills plugin: ready")
