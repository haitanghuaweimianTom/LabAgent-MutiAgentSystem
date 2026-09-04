"""LLMCachePlugin - cache LLM responses by (system, user) hash.

Hooks `llm/pre-call` (waterfall): if a cached response exists, return it
(vetoes the real call). On miss, the host proceeds with the real LLM call
and calls `record()` to store the response for next time.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from labagent.plugin import Context

logger = logging.getLogger(__name__)


def _hash_request(req: dict[str, Any]) -> str:
    """Stable cache key from (system, user, max_tokens)."""
    payload = json.dumps(
        {"system": req.get("system", ""), "user": req.get("user", ""),
         "max_tokens": req.get("max_tokens", 0)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class LLMCachePlugin:
    name = "llm_cache"
    inject = []

    def __init__(self, cache_dir: Optional[Path | str] = None) -> None:
        self._dir = Path(cache_dir) if cache_dir else (Path.cwd() / ".llm_cache")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    def setup(self, ctx: Context) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        logger.info("llm-cache plugin: ready (cache_dir=%s)", self._dir)

    def _path_for(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, req: dict[str, Any]) -> Optional[dict[str, Any]]:
        key = _hash_request(req)
        p = self._path_for(key)
        if not p.exists():
            self._misses += 1
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._misses += 1
            return None

    def record(self, req: dict[str, Any], response: dict[str, Any]) -> None:
        key = _hash_request(req)
        p = self._path_for(key)
        p.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
        logger.info("llm-cache: stored %s", key[:12])

    async def llm_call(self, req: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Async cache lookup. Returns cached response or None.

        Designed to be wired into `llm/pre-call` waterfall:
            result = await ctx.waterfall("llm/pre-call", req, next=...)
            if result is None:  # cache miss → call real LLM
                result = await real_llm(req)
                self.record(req, result)
            return result
        """
        cached = self.get(req)
        if cached is not None:
            self._hits += 1
            # Tag so callers can recognize cache hits in traces.
            return {**cached, "cached": True}
        return None
