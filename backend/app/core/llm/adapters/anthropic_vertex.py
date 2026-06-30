"""Anthropic Vertex adapter.

Requires the ``anthropic`` Python SDK with Vertex support.
Project/region are read from provider meta; missing values fall back to
Google default credentials.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse

logger = logging.getLogger(__name__)


@register_adapter
class AnthropicVertexAdapter(BaseAdapter):
    provider_type = "anthropic_vertex"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                f"[{self.provider_type}] The anthropic SDK is required for Vertex. "
                "Install it with: pip install anthropic"
            ) from exc

        meta = request.meta()
        kwargs: Dict[str, Any] = {}
        if meta.get("project_id"):
            kwargs["project_id"] = meta["project_id"]
        if meta.get("region"):
            kwargs["region"] = meta["region"]

        client = anthropic.AsyncAnthropicVertex(**kwargs)
        try:
            response = await client.messages.create(
                model=request.effective_model(),
                max_tokens=request.max_tokens or 4096,
                temperature=request.temperature,
                messages=request.messages,
                tools=self._anthropic_tools(request.tools),
            )
            return NormalizedResponse.from_anthropic(response.model_dump())
        except Exception as exc:
            logger.error(f"[{self.provider_type}] call failed: {exc}")
            raise RuntimeError(f"[{self.provider_type}] call failed: {exc}") from exc
        finally:
            await client.close()
