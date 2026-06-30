"""Anthropic Batch adapter.

The Batch API is asynchronous and not suitable for real-time chat completion.
This adapter registers the type so the architecture recognizes it, but rejects
synchronous calls with a clear message.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest


@register_adapter
class AnthropicBatchAdapter(BaseAdapter):
    provider_type = "anthropic_batch"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        raise NotImplementedError(
            f"[{self.provider_type}] Anthropic Batch API is asynchronous and "
            "not supported for synchronous chat_completion. Use the batch job API instead."
        )
