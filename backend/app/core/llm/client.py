"""Unified LLM client used by Agent Core."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...services.rate_limiter import AsyncTokenBucket
from .adapters import import_all_adapters  # noqa: F401; registers adapters
from .cache import LLMCache
from .registry import get_registry
from .types import LLMRequest, NormalizedResponse

logger = logging.getLogger(__name__)

_DEFAULT_RATE_LIMITER = AsyncTokenBucket(rate=5.0)


class UnifiedLLMClient:
    """Agent-facing LLM client.

    Accepts a provider configuration dict (from provider_config) and
    delegates to the registered adapter for that provider type.
    """

    def __init__(self, rate_limiter: Optional[AsyncTokenBucket] = None):
        self._rate_limiter = rate_limiter or _DEFAULT_RATE_LIMITER
        self._cache = LLMCache()

    async def chat_completion(
        self,
        provider: Dict[str, Any],
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        timeout: Optional[float] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Execute a chat completion for the given provider.

        Returns an OpenAI-compatible normalized dict:
            {"choices": [{"message": {"role": "assistant", "content": ..., "tool_calls": [...]}}]}
        """
        provider_type = provider.get("type")
        if not provider_type:
            meta = provider.get("meta", {}) or {}
            provider_type = meta.get("api_format", "openai_compatible")

        # Cache lookup — skip when tools are present (non-deterministic output).
        use_cache = not tools
        if use_cache:
            cached = self._cache.get(provider, messages, model)
            if cached is not None:
                logger.debug("LLM cache hit")
                return cached

        # Rate limit before adapter call.
        await self._rate_limiter.acquire()

        adapter_cls = get_registry().get(provider_type)
        adapter = adapter_cls()

        request = LLMRequest(
            provider=provider,
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            timeout=timeout,
            extra=extra,
        )

        response = await adapter.chat_completion(request)
        if isinstance(response, str):
            response = NormalizedResponse.from_text(response)
        elif not isinstance(response, dict):
            response = NormalizedResponse.from_text(str(response))

        if use_cache:
            self._cache.put(provider, messages, model, response)

        return response


# Global singleton used by BaseAgent.
_default_client: Optional[UnifiedLLMClient] = None


def get_unified_llm_client() -> UnifiedLLMClient:
    global _default_client
    if _default_client is None:
        _default_client = UnifiedLLMClient()
    return _default_client


def reset_unified_llm_client() -> None:
    global _default_client
    _default_client = None
