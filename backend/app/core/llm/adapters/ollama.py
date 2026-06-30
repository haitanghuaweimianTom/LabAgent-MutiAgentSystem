"""Ollama adapter."""
from __future__ import annotations

from typing import Any, Dict

import httpx

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse


@register_adapter
class OllamaAdapter(BaseAdapter):
    provider_type = "ollama"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        host = self._strip_base_url(request.api_host())
        url = f"{host}/api/chat"
        headers = {"Content-Type": "application/json"}

        payload: Dict[str, Any] = {
            "model": request.effective_model(),
            "messages": request.messages,
            "stream": False,
            "options": {},
        }
        if request.temperature is not None:
            payload["options"]["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["options"]["num_predict"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools

        try:
            data = await self._http_post(request, url, headers, payload)
            return NormalizedResponse.from_ollama(data)
        except httpx.HTTPStatusError as e:
            self._handle_http_error(request, e)
        except Exception as e:
            self._handle_exception(request, e)
        return NormalizedResponse.from_text("")
