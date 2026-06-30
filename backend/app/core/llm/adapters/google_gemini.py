"""Google Gemini adapter.

Implements the Gemini REST API directly so no extra SDK is required.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import httpx

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse

logger = logging.getLogger(__name__)


@register_adapter
class GoogleGeminiAdapter(BaseAdapter):
    provider_type = "google_gemini"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        host = self._strip_base_url(request.api_host())
        model = request.effective_model()
        url = f"{host}/v1beta/models/{model}:generateContent?key={request.api_key()}"
        headers = {"Content-Type": "application/json"}

        system_instruction = ""
        contents = []
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_instruction = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": self._to_parts(content)})

        payload: Dict[str, Any] = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if request.temperature is not None:
            payload["generationConfig"] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            payload.setdefault("generationConfig", {})["maxOutputTokens"] = request.max_tokens

        gemini_tools = self._gemini_tools(request.tools)
        if gemini_tools:
            payload["tools"] = gemini_tools

        try:
            data = await self._http_post(request, url, headers, payload)
            return NormalizedResponse.from_text(self._extract_text(data))
        except httpx.HTTPStatusError as e:
            self._handle_http_error(request, e)
        except Exception as e:
            self._handle_exception(request, e)
        return NormalizedResponse.from_text("")

    def _to_parts(self, content: Any) -> List[Dict[str, Any]]:
        if isinstance(content, str):
            return [{"text": content}] if content else []
        if isinstance(content, list):
            parts = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    parts.append({"text": item.get("text", "")})
                elif item.get("type") == "image_url":
                    url = item.get("image_url", {}).get("url", "")
                    data_url = self._parse_data_url(url)
                    if data_url:
                        mime_type, data = data_url
                        parts.append({"inlineData": {"mimeType": mime_type, "data": data}})
            return parts
        return [{"text": json.dumps(content, ensure_ascii=False)}]

    @staticmethod
    def _parse_data_url(url: str):
        if not url.startswith("data:"):
            return None
        header, _, data = url[len("data:"):].partition(",")
        mime_type = header.split(";")[0] if header else "image/png"
        if "base64" in header:
            return mime_type, data
        return None

    def _gemini_tools(self, tools: Any) -> List[Dict[str, Any]]:
        if not tools:
            return []
        declarations = []
        for t in tools:
            fn = t.get("function", t) if isinstance(t.get("function"), dict) else t
            declarations.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            })
        return [{"functionDeclarations": declarations}]

    def _extract_text(self, data: Dict[str, Any]) -> str:
        parts = []
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                text = part.get("text")
                if text:
                    parts.append(text)
        return "\n".join(parts)
