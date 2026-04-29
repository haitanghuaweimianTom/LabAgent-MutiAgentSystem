"""
Gemini Provider
===============

支持 Google Gemini API。
"""

from typing import Optional, AsyncGenerator, Dict, Any
import httpx
import json

from ..base import BaseLLMProvider, ProviderConfig, LLMResponse, ProviderType


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider"""

    DEFAULT_API_HOST = "https://generativelanguage.googleapis.com"
    DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(self, config: Optional[ProviderConfig] = None):
        if config is None:
            config = ProviderConfig.from_env(ProviderType.GEMINI, self.DEFAULT_MODEL)
        if not config.api_host:
            config.api_host = self.DEFAULT_API_HOST
        if not config.model:
            config.model = self.DEFAULT_MODEL
        super().__init__(config)
        self.client = httpx.Client(timeout=config.timeout)

    def _validate_config(self) -> None:
        if not self.config.api_key:
            raise ValueError("Gemini Provider 需要 api_key")
        if not self.config.model:
            raise ValueError("Gemini Provider 需要 model")

    def _build_request_body(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        if system_prompt:
            # Gemini uses systemInstruction at top level
            pass

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", self.config.temperature),
            },
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens:
            body["generationConfig"]["maxOutputTokens"] = max_tokens
        return body

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        body = self._build_request_body(prompt, system_prompt, **kwargs)
        model_name = self.config.model
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"

        url = f"{self.config.api_host}/v1beta/{model_name}:generateContent?key={self.config.api_key}"
        response = self.client.post(url, json=body)
        response.raise_for_status()
        data = response.json()

        content = ""
        if "candidates" in data and len(data["candidates"]) > 0:
            candidate = data["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                for part in candidate["content"]["parts"]:
                    content += part.get("text", "")

        usage = {}
        if "usageMetadata" in data:
            um = data["usageMetadata"]
            usage = {
                "prompt_tokens": um.get("promptTokenCount", 0),
                "completion_tokens": um.get("candidatesTokenCount", 0),
                "total_tokens": um.get("totalTokenCount", 0),
            }

        return LLMResponse(
            content=content,
            model=self.config.model,
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
        model_name = self.config.model
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"

        url = f"{self.config.api_host}/v1beta/{model_name}:generateContent?key={self.config.api_key}"
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            data = response.json()

        content = ""
        if "candidates" in data and len(data["candidates"]) > 0:
            candidate = data["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                for part in candidate["content"]["parts"]:
                    content += part.get("text", "")

        usage = {}
        if "usageMetadata" in data:
            um = data["usageMetadata"]
            usage = {
                "prompt_tokens": um.get("promptTokenCount", 0),
                "completion_tokens": um.get("candidatesTokenCount", 0),
                "total_tokens": um.get("totalTokenCount", 0),
            }

        return LLMResponse(
            content=content,
            model=self.config.model,
            usage=usage,
            raw_response=data
        )

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        body = self._build_request_body(prompt, system_prompt, **kwargs)
        model_name = self.config.model
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"

        url = f"{self.config.api_host}/v1beta/{model_name}:streamGenerateContent?alt=sse&key={self.config.api_key}"
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            async with client.stream("POST", url, json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            if "candidates" in data and len(data["candidates"]) > 0:
                                candidate = data["candidates"][0]
                                if "content" in candidate and "parts" in candidate["content"]:
                                    for part in candidate["content"]["parts"]:
                                        text = part.get("text", "")
                                        if text:
                                            yield text
                        except (json.JSONDecodeError, KeyError):
                            continue
