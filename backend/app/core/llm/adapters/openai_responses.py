"""OpenAI Responses API adapter."""
from __future__ import annotations

from typing import Any, Dict

import httpx

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse


@register_adapter
class OpenAIResponsesAdapter(BaseAdapter):
    provider_type = "openai_responses"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        url = f"{self._strip_base_url(request.api_host())}/responses"
        headers = {
            "Authorization": f"Bearer {request.api_key()}",
            "Content-Type": "application/json; charset=utf-8",
        }

        payload: Dict[str, Any] = {
            "model": request.effective_model(),
            "input": request.messages,
        }
        if request.max_tokens is not None:
            payload["max_output_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"

        try:
            data = await self._http_post(request, url, headers, payload)
            return NormalizedResponse.from_text(self._extract_text(data))
        except httpx.HTTPStatusError as e:
            self._handle_http_error(request, e)
        except Exception as e:
            self._handle_exception(request, e)
        return NormalizedResponse.from_text("")

    def _extract_text(self, data: Dict[str, Any]) -> str:
        output = data.get("output", [])
        parts = []
        for item in output:
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        parts.append(c.get("text", ""))
                    elif c.get("type") == "refusal":
                        parts.append(c.get("refusal", ""))
        return "\n".join(parts)
