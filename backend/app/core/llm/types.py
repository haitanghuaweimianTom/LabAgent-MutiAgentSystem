"""Shared types and response helpers for the unified LLM provider layer."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


ToolSpec = Dict[str, Any]
Message = Dict[str, Any]


@dataclass
class LLMRequest:
    """Provider-agnostic LLM request parameters."""

    provider: Dict[str, Any]
    messages: List[Message]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[List[ToolSpec]] = None
    timeout: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def effective_model(self) -> str:
        if self.model:
            return self.model
        models = self.provider.get("models", [])
        enabled = [m for m in models if m.get("enabled")]
        first = enabled[0] if enabled else (models[0] if models else {})
        name = first.get("name") if isinstance(first, dict) else first
        if not name:
            raise ValueError("No model configured for provider")
        return name

    def api_key(self) -> str:
        return self.provider.get("api_key", "")

    def api_host(self) -> str:
        return self.provider.get("api_host", "")

    def meta(self) -> Dict[str, Any]:
        return self.provider.get("meta", {}) or {}


class NormalizedResponse:
    """Utilities to normalize provider responses to an OpenAI-like dict."""

    @staticmethod
    def from_text(text: str) -> Dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": text,
                    }
                }
            ]
        }

    @staticmethod
    def from_openai(data: Dict[str, Any]) -> Dict[str, Any]:
        """Pass-through OpenAI-compatible response, fixing common fields."""
        choices = data.get("choices", [])
        if not choices:
            return NormalizedResponse.from_text("")
        msg = choices[0].get("message", {})
        normalized_msg: Dict[str, Any] = {
            "role": msg.get("role", "assistant"),
            "content": msg.get("content", "") or "",
        }
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            normalized_msg["tool_calls"] = [
                {
                    "id": tc.get("id"),
                    "type": tc.get("type", "function"),
                    "function": {
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", ""),
                    },
                }
                for tc in tool_calls
            ]
        return {"choices": [{"message": normalized_msg}]}

    @staticmethod
    def from_anthropic(data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Anthropic Messages API response.

        Handles thinking-enabled models (e.g. MiMo) that emit ``thinking``
        blocks before ``text`` blocks.  When max_tokens is small the model
        may spend all budget on thinking with no text left — in that case
        we fall back to the thinking content so callers get *something*.
        """
        content_text = ""
        thinking_text = ""
        tool_calls = []
        for block in data.get("content", []):
            btype = block.get("type", "")
            if btype == "text":
                content_text += block.get("text", "")
            elif btype == "thinking":
                thinking_text += block.get("thinking", "")
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                        },
                    }
                )
        # thinking-enabled models: if no text block, fall back to thinking content
        if not content_text and thinking_text:
            content_text = thinking_text
        msg: Dict[str, Any] = {"role": "assistant", "content": content_text}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return {"choices": [{"message": msg}]}

    @staticmethod
    def from_ollama(data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Ollama /api/chat response."""
        msg = data.get("message", {})
        content = msg.get("content", "") or ""
        normalized: Dict[str, Any] = {"role": "assistant", "content": content}
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            normalized["tool_calls"] = [
                {
                    "id": tc.get("id") or f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": tc.get("function", {}).get("name", "") if isinstance(tc.get("function"), dict) else tc.get("name", ""),
                        "arguments": json.dumps(
                            tc.get("function", {}).get("arguments", {})
                            if isinstance(tc.get("function"), dict)
                            else tc.get("arguments", {}),
                            ensure_ascii=False,
                        ),
                    },
                }
                for i, tc in enumerate(tool_calls)
            ]
        return {"choices": [{"message": normalized}]}
