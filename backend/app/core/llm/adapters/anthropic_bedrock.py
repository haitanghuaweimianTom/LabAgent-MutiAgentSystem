"""Anthropic Bedrock adapter.

Requires the ``anthropic`` Python SDK with Bedrock support.
Credentials are read from provider meta or standard AWS environment variables.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse

logger = logging.getLogger(__name__)


@register_adapter
class AnthropicBedrockAdapter(BaseAdapter):
    provider_type = "anthropic_bedrock"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                f"[{self.provider_type}] The anthropic SDK is required for Bedrock. "
                "Install it with: pip install anthropic"
            ) from exc

        meta = request.meta()
        kwargs: Dict[str, Any] = {}
        if meta.get("aws_access_key"):
            kwargs["aws_access_key"] = meta["aws_access_key"]
        if meta.get("aws_secret_key"):
            kwargs["aws_secret_key"] = meta["aws_secret_key"]
        if meta.get("aws_session_token"):
            kwargs["aws_session_token"] = meta["aws_session_token"]
        if meta.get("aws_region"):
            kwargs["aws_region"] = meta["aws_region"]

        client = anthropic.AsyncAnthropicBedrock(**kwargs)
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
