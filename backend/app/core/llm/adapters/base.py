"""Base adapter for the unified LLM provider layer."""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from ..types import LLMRequest, NormalizedResponse

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """Provider adapter base class.

    Each adapter is responsible for converting a provider-agnostic
    :class:`LLMRequest` into the target provider's native API call and
    returning an OpenAI-compatible normalized response dict.
    """

    provider_type: str = ""

    @abstractmethod
    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        """Execute a chat completion and return a normalized response."""
        ...

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _bearer_headers(self, request: LLMRequest, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Authorization: Bearer <api_key> plus optional extra headers."""
        headers = {"Authorization": f"Bearer {request.api_key()}"}
        if extra:
            headers.update(extra)
        return headers

    def _x_api_key_headers(self, request: LLMRequest, version: str = "2023-06-01") -> Dict[str, str]:
        """Anthropic-style x-api-key headers."""
        return {
            "x-api-key": request.api_key(),
            "anthropic-version": version,
            "content-type": "application/json",
        }

    def _auth_token_headers(self, request: LLMRequest, version: str = "2023-06-01") -> Dict[str, str]:
        """Anthropic auth-token style headers (e.g. Alibaba Cloud TokenPlan)."""
        return {
            "Authorization": f"Bearer {request.api_key()}",
            "anthropic-version": version,
            "content-type": "application/json",
        }

    def _default_timeout(self, request: LLMRequest) -> float:
        return request.timeout or (600.0 if (request.max_tokens or 0) >= 4096 else 300.0)

    def _openai_style_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """Return tools as-is when already in OpenAI format."""
        if not tools:
            return None
        return tools

    def _anthropic_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """Convert OpenAI-style tool specs to Anthropic tool schema."""
        if not tools:
            return None
        out = []
        for t in tools:
            fn = t.get("function", t) if isinstance(t.get("function"), dict) else t
            out.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {}),
                }
            )
        return out

    async def _http_post(
        self,
        request: LLMRequest,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Shared async HTTP POST with retries on timeout/connection errors."""
        timeout = self._default_timeout(request)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)

        async def _post(t: float) -> httpx.Response:
            async with httpx.AsyncClient(timeout=t, limits=limits, proxy=None) as client:
                return await client.post(url, headers=headers, content=body)

        try:
            response = await _post(timeout)
            response.raise_for_status()
            return response.json()
        except httpx.ReadTimeout:
            logger.warning(f"[{self.provider_type}] ReadTimeout ({timeout}s), retrying once...")
            response = await _post(timeout * 1.5)
            response.raise_for_status()
            return response.json()
        except (httpx.RemoteProtocolError, httpx.PoolTimeout, httpx.ConnectError, httpx.NetworkError, OSError) as e:
            logger.warning(f"[{self.provider_type}] Connection error: {e}, retrying once...")
            response = await _post(timeout * 2)
            response.raise_for_status()
            return response.json()

    def _handle_http_error(self, request: LLMRequest, exc: httpx.HTTPStatusError) -> None:
        """Log and raise a clean RuntimeError for HTTP failures."""
        try:
            err_text = exc.response.content.decode("utf-8", errors="replace")[:400]
        except Exception:
            err_text = "unable to read response"
        logger.error(f"[{self.provider_type}] HTTP {exc.response.status_code}: {err_text}")
        raise RuntimeError(
            f"[{self.provider_type}] HTTP {exc.response.status_code}: {err_text}"
        ) from exc

    def _handle_exception(self, request: LLMRequest, exc: Exception) -> None:
        """Log and raise a clean RuntimeError for unexpected failures."""
        logger.error(f"[{self.provider_type}] call failed: {exc}")
        raise RuntimeError(f"[{self.provider_type}] call failed: {exc}") from exc

    @staticmethod
    def _strip_base_url(host: str) -> str:
        """Remove trailing slashes from a base URL."""
        return host.rstrip("/")
