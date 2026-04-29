"""
Ollama Provider
===============

支持 Ollama 本地部署的模型。
"""

from typing import Optional, AsyncGenerator, Dict, Any
import httpx
import json

from ..base import BaseLLMProvider, ProviderConfig, LLMResponse, ProviderType


class OllamaProvider(BaseLLMProvider):
    """Ollama API Provider"""

    DEFAULT_API_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "llama3.2"

    def __init__(self, config: Optional[ProviderConfig] = None):
        if config is None:
            config = ProviderConfig.from_env(ProviderType.OLLAMA, self.DEFAULT_MODEL)
        if not config.api_host:
            config.api_host = self.DEFAULT_API_HOST
        if not config.model:
            config.model = self.DEFAULT_MODEL
        super().__init__(config)
        self.client = httpx.Client(timeout=config.timeout)

    def _validate_config(self) -> None:
        if not self.config.model:
            raise ValueError("Ollama Provider 需要 model")

    def _build_request_body(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
            },
        }
        return body

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        body = self._build_request_body(prompt, system_prompt, **kwargs)
        response = self.client.post(
            f"{self.config.api_host}/api/chat",
            json=body
        )
        response.raise_for_status()
        data = response.json()

        content = ""
        if "message" in data:
            content = data["message"].get("content", "")

        usage = {}
        if "prompt_eval_count" in data:
            usage = {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            }

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
        body = self._build_request_body(prompt, system_prompt, **kwargs)
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                f"{self.config.api_host}/api/chat",
                json=body
            )
            response.raise_for_status()
            data = response.json()

        content = ""
        if "message" in data:
            content = data["message"].get("content", "")

        usage = {}
        if "prompt_eval_count" in data:
            usage = {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            }

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
        body = self._build_request_body(prompt, system_prompt, stream=True, **kwargs)
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.config.api_host}/api/chat",
                json=body
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "message" in data:
                            delta = data["message"].get("content", "")
                            if delta:
                                yield delta
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
