"""Sandbox protocol - abstracts the code-execution backend.

Two implementations in this repo:
  - default (subprocess): the existing `CodeSandbox` from sandbox_and_gates
  - DockerSandboxPlugin: uses Docker for isolation

Host code does `ctx.require("sandbox")` and gets whichever the active
plugin provides.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from labagent.plugin import Context

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    returncode: int
    duration_s: float

    @property
    def success(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "duration_s": self.duration_s,
            "success": self.success,
        }


class Sandbox(Protocol):
    """Anything that can execute a Python file and return SandboxResult."""

    backend_name: str

    def run(self, code: str, *, timeout_s: int = 60, workdir: Optional[Path] = None) -> SandboxResult: ...


class SubprocessSandbox:
    """Default fallback: run the code in a subprocess."""

    backend_name = "subprocess-fallback"

    def run(self, code: str, *, timeout_s: int = 60, workdir: Optional[Path] = None) -> SandboxResult:
        import time
        workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="sandbox-fb-"))
        workdir.mkdir(parents=True, exist_ok=True)
        script = workdir / "code.py"
        script.write_text(code, encoding="utf-8")
        start = time.time()
        try:
            proc = subprocess.run(
                ["python", str(script)],
                capture_output=True, text=True, timeout=timeout_s,
            )
            return SandboxResult(
                stdout=proc.stdout, stderr=proc.stderr,
                returncode=proc.returncode,
                duration_s=time.time() - start,
            )
        except subprocess.TimeoutExpired as e:
            return SandboxResult(stdout=e.stdout or "", stderr="timeout",
                                 returncode=-1, duration_s=time.time() - start)
