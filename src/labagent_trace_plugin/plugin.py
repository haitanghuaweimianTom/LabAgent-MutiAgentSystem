"""TracePlugin - dumps every step's output to a JSON file (debug aid)."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

from labagent.plugin import Context

logger = logging.getLogger(__name__)

# Conservative secret-redaction patterns. Keep simple to avoid leaking.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),          # OpenAI / MiniMax style
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*[\w-]{8,}"),
    re.compile(r"(?i)password\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}"),
]

_REDACTED = "[REDACTED]"


def _scrub(text: str) -> str:
    if not isinstance(text, str):
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(_REDACTED, out)
    return out


def _scrub_obj(o: Any) -> Any:
    if isinstance(o, str):
        return _scrub(o)
    if isinstance(o, dict):
        return {k: _scrub_obj(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_scrub_obj(v) for v in o]
    if isinstance(o, tuple):
        return tuple(_scrub_obj(v) for v in o)
    return o


class TracePlugin:
    name = "trace"
    inject = []

    def __init__(self, out_dir: Optional[Path | str] = None) -> None:
        self._out_dir = Path(out_dir) if out_dir else (Path.cwd() / ".traces")
        self._run_id: str = "run"
        self._counter = 0

    def setup(self, ctx: Context) -> None:
        self._out_dir.mkdir(parents=True, exist_ok=True)
        ctx.on("session/start", lambda p: self._on_session_start(p))
        ctx.on("step/end", lambda p: self._on_step_end(p))
        logger.info("trace plugin: ready (out_dir=%s)", self._out_dir)

    def _on_session_start(self, p: dict[str, Any]) -> None:
        self._run_id = p.get("run_id", self._run_id)
        self._counter = 0

    def _on_step_end(self, p: dict[str, Any]) -> None:
        self._counter += 1
        step = p.get("step", "unknown")
        ts = time.time()
        record = {
            "ts": ts,
            "run_id": self._run_id,
            "step": step,
            "payload": _scrub_obj(p),
        }
        # Use a sortable name: counter-step-timestamp
        out_file = self._out_dir / f"{self._counter:04d}-{step}-{int(ts)}.json"
        out_file.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
