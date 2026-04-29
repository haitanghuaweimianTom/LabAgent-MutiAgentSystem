"""
Anthropic Provider
==================

支持 Anthropic Claude API，包括：
- Claude 3.5 Sonnet
- Claude 3 Opus
- Claude 3 Haiku
- Claude 4 系列
"""

from typing import Optional, AsyncGenerator, Dict, Any
import httpx
import json

from ..base import BaseLLMProvider, ProviderConfig, LLMResponse, ProviderType


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API Provider"""

    DEFAULT_API_HOST = "https://api.anthropic.com"
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self, config: Optional[ProviderConfig] = None):
        if config is None:
            config = ProviderConfig.from_env(ProviderType.ANTHROPIC, self.DEFAULT_MODEL)
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
            raise ValueError("Anthropic Provider 需要 api_key")
        if not self.config.model:
            raise ValueError("Anthropic Provider 需要 model")

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)
        return headers

    def _build_request_body(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        if system_prompt:
            body["system"] = system_prompt
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens:
            body["max_tokens"] = max_tokens
        else:
            body["max_tokens"] = 4096
        return body

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """同步生成"""
        body = self._build_request_body(prompt, system_prompt, **kwargs)

        response = self.client.post(
            f"{self.config.api_host}/v1/messages",
            json=body
        )
        response.raise_for_status()
        data = response.json()

        content = ""
        if "content" in data and len(data["content"]) > 0:
            content = data["content"][0].get("text", "")

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
        body = self._build_request_body(prompt, system_prompt, **kwargs)

        async with httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=self._get_headers()
        ) as client:
            response = await client.post(
                f"{self.config.api_host}/v1/messages",
                json=body
            )
            response.raise_for_status()
            data = response.json()

        content = ""
        if "content" in data and len(data["content"]) > 0:
            content = data["content"][0].get("text", "")

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
        body = self._build_request_body(prompt, system_prompt, stream=True, **kwargs)

        async with httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=self._get_headers()
        ) as client:
            async with client.stream(
                "POST",
                f"{self.config.api_host}/v1/messages",
                json=body
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            if data.get("type") == "content_block_delta":
                                delta = data.get("delta", {})
                                if "text" in delta:
                                    yield delta["text"]
                        except (json.JSONDecodeError, KeyError):
                            continue
