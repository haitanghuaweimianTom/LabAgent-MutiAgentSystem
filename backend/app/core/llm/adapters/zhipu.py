"""Zhipu AI adapter.

Zhipu provides an OpenAI-compatible chat completions endpoint.
"""
from __future__ import annotations

from typing import Any, Dict

import httpx

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse


@register_adapter
class ZhipuAdapter(BaseAdapter):
    provider_type = "zhipu"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        host = self._strip_base_url(request.api_host())
        url = f"{host}/chat/completions"
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
        return NormalizedResponse.from_text("")
