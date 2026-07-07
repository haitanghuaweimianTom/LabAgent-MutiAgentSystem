"""Custom HTTP adapter.

Allows arbitrary endpoints configured via provider meta:
  - meta.http_method (default POST)
  - meta.http_path  (default /chat/completions)
  - meta.auth_header (default Authorization: Bearer)

Response is expected to be OpenAI-compatible; otherwise the raw text is returned.
"""
from __future__ import annotations

from typing import Any, Dict

import httpx

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse


@register_adapter
class CustomHTTPAdapter(BaseAdapter):
    provider_type = "custom_http"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        meta = request.meta()
        host = self._strip_base_url(request.api_host())
        path = meta.get("http_path", "/chat/completions")
        method = meta.get("http_method", "POST").upper()
        url = f"{host}{path}"

        auth_header = meta.get("auth_header", "Authorization")
        headers = {auth_header: f"Bearer {request.api_key()}", "Content-Type": "application/json; charset=utf-8"}

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
            if method == "GET":
                data = await self._http_get(request, url, headers)
            else:
                data = await self._http_post(request, url, headers, payload)
            return NormalizedResponse.from_openai(data)
        except httpx.HTTPStatusError as e:
            self._handle_http_error(request, e)
        except Exception as e:
            self._handle_exception(request, e)
        return NormalizedResponse.from_text("")

    async def _http_get(self, request: LLMRequest, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        timeout = self._default_timeout(request)
        async with httpx.AsyncClient(timeout=timeout, proxy=None) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
