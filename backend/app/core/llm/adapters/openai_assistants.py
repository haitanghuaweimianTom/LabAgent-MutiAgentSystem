"""OpenAI Assistants API adapter (minimal polling implementation)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

import httpx

from .base import BaseAdapter
from ..registry import register_adapter
from ..types import LLMRequest, NormalizedResponse

logger = logging.getLogger(__name__)


@register_adapter
class OpenAIAssistantsAdapter(BaseAdapter):
    provider_type = "openai_assistants"

    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        if request.tools:
            logger.warning(f"[{self.provider_type}] Tool use via Assistants API not yet implemented; ignoring tools.")

        host = self._strip_base_url(request.api_host())
        headers = {
            "Authorization": f"Bearer {request.api_key()}",
            "Content-Type": "application/json; charset=utf-8",
            "OpenAI-Beta": "assistants=v2",
        }

        # 1. Create thread with initial user messages.
        thread_url = f"{host}/threads"
        thread_payload = {"messages": request.messages}
        thread_data = await self._http_post(request, thread_url, headers, thread_payload)
        thread_id = thread_data.get("id")
        if not thread_id:
            raise RuntimeError(f"[{self.provider_type}] Failed to create thread: {thread_data}")

        # 2. Create run.
        run_payload: Dict[str, Any] = {
            "assistant_id": request.meta().get("assistant_id", "default"),
            "model": request.effective_model(),
        }
        if request.max_tokens is not None:
            run_payload["max_completion_tokens"] = request.max_tokens
        if request.temperature is not None:
            run_payload["temperature"] = request.temperature

        run_data = await self._http_post(request, f"{host}/threads/{thread_id}/runs", headers, run_payload)
        run_id = run_data.get("id")
        if not run_id:
            raise RuntimeError(f"[{self.provider_type}] Failed to create run: {run_data}")

        # 3. Poll until terminal status.
        status = run_data.get("status", "")
        timeout = self._default_timeout(request)
        poll_deadline = asyncio.get_event_loop().time() + timeout
        while status not in ("completed", "failed", "cancelled", "expired", "incomplete"):
            if asyncio.get_event_loop().time() > poll_deadline:
                raise RuntimeError(f"[{self.provider_type}] Assistant run polling timed out")
            await asyncio.sleep(1.0)
            run_data = await self._http_get(request, f"{host}/threads/{thread_id}/runs/{run_id}", headers)
            status = run_data.get("status", "")

        if status != "completed":
            raise RuntimeError(f"[{self.provider_type}] Assistant run ended with status={status}: {run_data}")

        # 4. Fetch latest assistant message.
        messages_data = await self._http_get(request, f"{host}/threads/{thread_id}/messages", headers)
        for m in messages_data.get("data", []):
            if m.get("role") == "assistant":
                parts = []
                for c in m.get("content", []):
                    if c.get("type") == "text":
                        parts.append(c.get("text", {}).get("value", ""))
                return NormalizedResponse.from_text("\n".join(parts))
        return NormalizedResponse.from_text("")

    async def _http_get(self, request: LLMRequest, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        timeout = self._default_timeout(request)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
