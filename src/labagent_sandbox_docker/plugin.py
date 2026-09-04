"""DockerSandboxPlugin - registers a Docker-backed Sandbox service (with subprocess fallback)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from labagent.plugin import Context

from .sandbox_protocol import (
    Sandbox,
    SandboxResult,
    SubprocessSandbox,
)

logger = logging.getLogger(__name__)

try:
    import docker  # type: ignore
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False


class _DockerSandbox:
    """Run code inside a Docker container (one-shot)."""

    backend_name = "docker"

    def __init__(self, image: str = "python:3.11-slim", workspace_dir: Optional[Path] = None) -> None:
        self._image = image
        self._workspace = Path(workspace_dir) if workspace_dir else Path(tempfile.gettempdir()) / "labagent-sandbox"
        self._client = None
        if DOCKER_AVAILABLE:
            try:
                self._client = docker.from_env()
            except Exception as e:
                logger.warning("docker.from_env() failed: %s", e)
                self._client = None

    def run(self, code: str, *, timeout_s: int = 60, workdir: Optional[Path] = None) -> SandboxResult:
        if self._client is None:
            # Caller must check DOCKER_AVAILABLE before instantiating
            raise RuntimeError("docker not available")

        workdir = Path(workdir) if workdir else self._workspace
        workdir.mkdir(parents=True, exist_ok=True)
        script = workdir / "code.py"
        script.write_text(code, encoding="utf-8")

        start = time.time()
        try:
            output = self._client.containers.run(
                self._image,
                command=["python", "/work/code.py"],
                volumes={str(workdir): {"bind": "/work", "mode": "rw"}},
                working_dir="/work",
                network_mode="none",
                mem_limit="512m",
                remove=True,
                stdout=True, stderr=True,
                user=f"{subprocess.run(['id', '-u'], capture_output=True, text=True).stdout.strip()}:{subprocess.run(['id', '-g'], capture_output=True, text=True).stdout.strip()}",
                detach=False,
            )
            stdout = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else str(output)
            return SandboxResult(stdout=stdout, stderr="", returncode=0,
                                 duration_s=time.time() - start)
        except Exception as e:
            err = str(e)
            # Docker image not present, daemon down, etc.
            if "No such image" in err or "not found" in err.lower():
                try:
                    self._client.images.pull(self._image)
                    return self.run(code, timeout_s=timeout_s, workdir=workdir)
                except Exception:
                    pass
            return SandboxResult(stdout="", stderr=err, returncode=-1,
                                 duration_s=time.time() - start)


class DockerSandboxPlugin:
    name = "sandbox_docker"
    inject = []

    def __init__(self, image: str = "python:3.11-slim", workspace_dir: Optional[Path | str] = None) -> None:
        self._image = image
        self._workspace = Path(workspace_dir) if workspace_dir else None

    def setup(self, ctx: Context) -> None:
        if DOCKER_AVAILABLE:
            try:
                sb = _DockerSandbox(image=self._image, workspace_dir=self._workspace)
                # smoke-test
                if sb._client is None:
                    raise RuntimeError("docker daemon unavailable")
                sandbox: Sandbox = sb
                logger.info("sandbox-docker plugin: using Docker backend")
            except Exception as e:
                logger.warning("sandbox-docker: Docker init failed (%s); falling back", e)
                sandbox = SubprocessSandbox()
        else:
            logger.info("sandbox-docker plugin: docker not installed; using subprocess fallback")
            sandbox = SubprocessSandbox()
        ctx.register("sandbox", sandbox)
