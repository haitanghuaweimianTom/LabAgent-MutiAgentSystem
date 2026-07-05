"""LLM response cache with SHA-256 keying and LRU eviction."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LLMCache:
    """Simple in-memory LLM response cache.

    Keys are SHA-256 hashes of (provider_key, model, messages) tuples.
    Entries expire after *ttl* seconds and the cache evicts the oldest
    entry when it exceeds *max_size*.
    """

    def __init__(self, max_size: int = 200, ttl: float = 1800.0):
        self.max_size = max_size
        self.ttl = ttl
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        provider: Dict[str, Any],
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> Optional[Any]:
        """Return cached response or *None*."""
        key = self._make_key(provider, messages, model)
        entry = self._store.get(key)
        if entry is None:
            return None
        created_at, value = entry
        if time.monotonic() - created_at > self.ttl:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def put(
        self,
        provider: Dict[str, Any],
        messages: List[Dict[str, Any]],
        model: Optional[str],
        value: Any,
    ) -> None:
        key = self._make_key(provider, messages, model)
        self._store[key] = (time.monotonic(), value)
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(
        provider: Dict[str, Any],
        messages: List[Dict[str, Any]],
        model: Optional[str],
    ) -> str:
        provider_key = provider.get("name") or provider.get("api_host") or provider.get("type", "")
        payload = json.dumps(
            {"pk": provider_key, "m": model, "msgs": messages},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()
