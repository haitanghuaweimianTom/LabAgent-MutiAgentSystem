"""
MiniMax Provider
===============

MiniMax-M3 模型（OpenAI 兼容 API）。
默认上下文窗口 256K tokens，推理 Agent 512K，自动压缩阈值 90%。

通过 .env 配置：
    MINIMAX_API_KEY=sk-...
    MINIMAX_API_HOST=https://api.minimaxi.com
    MINIMAX_MODEL=MiniMax-M3
    LLM_MAX_CONTEXT_LENGTH=256000
    LLM_REASONING_CONTEXT_LENGTH=512000
    LLM_AUTO_COMPRESS_RATIO=0.9
"""
import os
from typing import Optional, AsyncGenerator, Dict, Any

from ..base import BaseLLMProvider, ProviderConfig, LLMResponse, ProviderType


class MiniMaxProvider(BaseLLMProvider):
    """MiniMax API Provider（OpenAI 兼容格式）"""

    DEFAULT_API_HOST = "https://api.minimaxi.com"
    DEFAULT_MODEL = "MiniMax-M3"
    DEFAULT_MAX_CONTEXT_LENGTH = 500_000
    DEFAULT_AUTO_COMPRESS_RATIO = 0.9
    CHAT_COMPLETIONS_PATH = "/v1/text/chatcompletion_v2"

    def __init__(self, config: Optional[ProviderConfig] = None):
        if config is None:
            config = ProviderConfig.from_env(ProviderType.MINIMAX, self.DEFAULT_MODEL)
        if not config.api_host:
            config.api_host = self.DEFAULT_API_HOST
        if not config.model:
            config.model = self.DEFAULT_MODEL
        if config.max_context_length is None:
            config.max_context_length = self.DEFAULT_MAX_CONTEXT_LENGTH
        if config.auto_compress_ratio <= 0 or config.auto_compress_ratio > 1:
            config.auto_compress_ratio = self.DEFAULT_AUTO_COMPRESS_RATIO
        super().__init__(config)

    def _validate_config(self) -> None:
        if not self.config.api_key:
            raise ValueError("MiniMax Provider 需要 api_key")
        if not self.config.model:
            raise ValueError("MiniMax Provider 需要 model")
        if self.config.max_context_length <= 0:
            raise ValueError("MiniMax Provider 需要 max_context_length > 0")

    def _build_request_body(
        self,
        messages: list,
        stream: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        body = {
            "model": self.config.model,
            "messages": messages,
            "stream": stream,
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens:
            body["max_tokens"] = max_tokens
        return body

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        messages = self._build_messages(prompt, system_prompt)
        body = self._build_request_body(messages, **kwargs)

        import httpx

        with httpx.Client(
            timeout=self.config.timeout,
            headers=self._get_headers(),
        ) as client:
            response = client.post(
                f"{self.config.api_host}{self.CHAT_COMPLETIONS_PATH}",
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=data.get("model", self.config.model),
            usage=usage,
            raw_response=data,
        )

    async def generate_async(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        messages = self._build_messages(prompt, system_prompt)
        body = self._build_request_body(messages, **kwargs)

        import httpx

        async with httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=self._get_headers(),
        ) as client:
            response = await client.post(
                f"{self.config.api_host}{self.CHAT_COMPLETIONS_PATH}",
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=data.get("model", self.config.model),
            usage=usage,
            raw_response=data,
        )

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        import httpx
        import json

        messages = self._build_messages(prompt, system_prompt)
        body = self._build_request_body(messages, stream=True, **kwargs)

        async with httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=self._get_headers(),
        ) as client:
            async with client.stream(
                "POST",
                f"{self.config.api_host}{self.CHAT_COMPLETIONS_PATH}",
                json=body,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0]["delta"]
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)
        return headers

    @property
    def auto_compress_threshold(self) -> int:
        """触发自动压缩的 token 阈值。默认 max_context_length × ratio。"""
        return int(self.config.max_context_length * self.config.auto_compress_ratio)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.config.name}, "
            f"model={self.config.model}, max_ctx={self.config.max_context_length}, "
            f"compress_at={self.auto_compress_threshold})"
        )
