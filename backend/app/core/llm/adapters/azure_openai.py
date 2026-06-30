"""Azure OpenAI adapter.

Azure OpenAI uses a distinct authentication header (api-key) and URL shape:
  {endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}
"""
from __future__ import annotations

from typing import Any, Dict

import httpx

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse


@register_adapter
class AzureOpenAIAdapter(BaseAdapter):
    provider_type = "azure_openai"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        host = self._strip_base_url(request.api_host())
        deployment = request.effective_model()
        api_version = request.meta().get("api_version") or request.extra.get("api_version", "2024-06-01")
        url = f"{host}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"

        headers = {
            "api-key": request.api_key(),
            "Content-Type": "application/json; charset=utf-8",
        }

        payload: Dict[str, Any] = {
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
