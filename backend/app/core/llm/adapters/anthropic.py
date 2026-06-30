"""Anthropic Messages API adapter.

Accepts OpenAI-style messages and tool definitions, converts them to Anthropic
native format, then normalizes the response back to OpenAI-style.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

import httpx

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse

logger = logging.getLogger(__name__)


@register_adapter
class AnthropicAdapter(BaseAdapter):
    provider_type = "anthropic"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        host = self._strip_base_url(request.api_host())
        url = f"{host}/v1/messages"

        auth_field = request.meta().get("auth_field", "")
        if auth_field == "anthropic_auth_token":
            headers = self._auth_token_headers(request)
        else:
            headers = self._x_api_key_headers(request)

        system, messages = self._to_anthropic_messages(request.messages)
        payload: Dict[str, Any] = {
            "model": request.effective_model(),
            "max_tokens": request.max_tokens or 4096,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        anthropic_tools = self._anthropic_tools(request.tools)
        if anthropic_tools:
            payload["tools"] = anthropic_tools

        try:
            data = await self._http_post(request, url, headers, payload)
            return NormalizedResponse.from_anthropic(data)
        except httpx.HTTPStatusError as e:
            self._handle_http_error(request, e)
        except Exception as e:
            self._handle_exception(request, e)
        return NormalizedResponse.from_text("")

    def _to_anthropic_messages(self, messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
        """Convert OpenAI-style messages to Anthropic native format."""
        system_parts: List[str] = []
        out: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_parts.append(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
                continue

            if role == "assistant":
                anthropic_content: List[Dict[str, Any]] = []
                if content:
                    anthropic_content.extend(self._convert_content(content))
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            input_obj = json.loads(args)
                        except json.JSONDecodeError:
                            input_obj = {}
                    else:
                        input_obj = args
                    anthropic_content.append({
                        "type": "tool_use",
                        "id": tc.get("id") or f"toolu_{fn.get('name', 'call')}",
                        "name": fn.get("name", ""),
                        "input": input_obj,
                    })
                out.append({"role": "assistant", "content": anthropic_content})
                continue

            if role == "tool":
                out.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
                    }],
                })
                continue

            # Default user message
            out.append({"role": "user", "content": self._convert_content(content)})

        system = "\n".join(system_parts)
        return system, out

    def _convert_content(self, content: Any) -> List[Dict[str, Any]]:
        """Convert OpenAI content (str or list of parts) to Anthropic content blocks."""
        if isinstance(content, str):
            return [{"type": "text", "text": content}] if content else []
        if isinstance(content, list):
            blocks = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type")
                if part_type == "text":
                    blocks.append({"type": "text", "text": part.get("text", "")})
                elif part_type == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    data_url = self._parse_data_url(url)
                    if data_url:
                        media_type, data = data_url
                        blocks.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": data},
                        })
            return blocks
        return [{"type": "text", "text": json.dumps(content, ensure_ascii=False)}]

    @staticmethod
    def _parse_data_url(url: str) -> Any:
        """Parse a data URL like 'data:image/png;base64,DATA' and return (media_type, data)."""
        if not url.startswith("data:"):
            return None
        header, _, data = url[len("data:"):].partition(",")
        media_type = header.split(";")[0] if header else "image/png"
        if "base64" in header:
            return media_type, data
        return None
