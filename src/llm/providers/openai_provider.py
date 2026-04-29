"""
OpenAI Provider
===============

支持 OpenAI API 及所有兼容 OpenAI API 格式的服务商，包括：
- OpenAI 官方
- Azure OpenAI
- DeepSeek
- SiliconFlow
- 其他兼容 OpenAI API 的服务商
"""

import os
from typing import Optional, AsyncGenerator, Dict, Any
import httpx
import json

from ..base import BaseLLMProvider, ProviderConfig, LLMResponse, ProviderType


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API Provider"""

    DEFAULT_API_HOST = "https://api.openai.com"
    DEFAULT_MODEL = "gpt-4o"

    def __init__(self, config: Optional[ProviderConfig] = None):
        if config is None:
            config = ProviderConfig.from_env(ProviderType.OPENAI, self.DEFAULT_MODEL)
        if not config.api_host:
            config.api_host = self.DEFAULT_API_HOST
        if not config.model:
            config.model = self.DEFAULT_MODEL
        super().__init__(config)
        self.client = httpx.Client(
            timeout=config.timeout,
            headers=self._get_headers()
        )

    def _validate_config(self) -> None:
        if not self.config.api_key:
            raise ValueError("OpenAI Provider 需要 api_key")
        if not self.config.model:
            raise ValueError("OpenAI Provider 需要 model")

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)
        return headers

    def _build_request_body(
        self,
        messages: list,
        stream: bool = False,
        **kwargs
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
        **kwargs
    ) -> LLMResponse:
        """同步生成"""
        messages = self._build_messages(prompt, system_prompt)
        body = self._build_request_body(messages, **kwargs)

        response = self.client.post(
            f"{self.config.api_host}/v1/chat/completions",
            json=body
        )
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=data.get("model", self.config.model),
            usage=usage,
            raw_response=data
        )

    async def generate_async(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """异步生成"""
        messages = self._build_messages(prompt, system_prompt)
        body = self._build_request_body(messages, **kwargs)

        async with httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=self._get_headers()
        ) as client:
            response = await client.post(
                f"{self.config.api_host}/v1/chat/completions",
                json=body
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=data.get("model", self.config.model),
            usage=usage,
            raw_response=data
        )

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式生成"""
        messages = self._build_messages(prompt, system_prompt)
        body = self._build_request_body(messages, stream=True, **kwargs)

        async with httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=self._get_headers()
        ) as client:
            async with client.stream(
                "POST",
                f"{self.config.api_host}/v1/chat/completions",
                json=body
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
                        except (json.JSONDecodeError, KeyError):
                            continue
