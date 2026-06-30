"""OpenAI adapter (chat completions)."""
from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse

logger = logging.getLogger(__name__)


@register_adapter
class OpenAIAdapter(BaseAdapter):
    provider_type = "openai"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        url = f"{self._strip_base_url(request.api_host())}/chat/completions"
        headers = {
            "Authorization": f"Bearer {request.api_key()}",
            "Content-Type": "application/json; charset=utf-8",
        }

        payload: Dict[str, Any] = {
            "model": request.effective_model(),
            "messages": request.messages,
            "max_tokens": request.max_tokens,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"

        try:
            data = await self._http_post(request, url, headers, payload)
            return NormalizedResponse.from_openai(data)
        except httpx.HTTPStatusError as e:
            self._handle_http_error(request, e)
        except Exception as e:
            self._handle_exception(request, e)

        # Unreachable, but keeps mypy happy.
        return NormalizedResponse.from_text("")
