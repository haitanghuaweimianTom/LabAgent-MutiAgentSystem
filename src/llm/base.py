"""
LLM Provider 抽象基类
===================

借鉴 cherry-studio 的 Provider 架构设计，
实现多 LLM 提供商的统一抽象接口。

支持的提供商类型:
- openai: OpenAI API 兼容格式
- anthropic: Anthropic Claude API
- gemini: Google Gemini API
- ollama: Ollama 本地模型
- claude_cli: Claude Code CLI (向后兼容)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, AsyncGenerator
from enum import Enum
import os
import json


class ProviderType(str, Enum):
    """支持的 LLM 提供商类型"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    CLAUDE_CLI = "claude_cli"


@dataclass
class LLMMessage:
    """LLM 消息"""
    role: str  # system, user, assistant
    content: str


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    model: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    raw_response: Optional[Any] = None


@dataclass
class ProviderConfig:
    """Provider 配置"""
    provider_type: ProviderType
    name: str
    api_key: Optional[str] = None
    api_host: Optional[str] = None
    api_version: Optional[str] = None
    model: str = ""
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    timeout: int = 120
    extra_headers: Optional[Dict[str, str]] = None
    enabled: bool = True

    @classmethod
    def from_env(cls, provider_type: ProviderType, model: str = "") -> "ProviderConfig":
        """从环境变量创建配置"""
        env_prefix = provider_type.value.upper()
        return cls(
            provider_type=provider_type,
            name=provider_type.value,
            api_key=os.getenv(f"{env_prefix}_API_KEY") or os.getenv("LLM_API_KEY"),
            api_host=os.getenv(f"{env_prefix}_API_HOST"),
            model=model or os.getenv(f"{env_prefix}_MODEL", ""),
            temperature=float(os.getenv(f"{env_prefix}_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv(f"{env_prefix}_MAX_TOKENS", "0")) or None,
            timeout=int(os.getenv(f"{env_prefix}_TIMEOUT", "120")),
        )


class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._validate_config()

    @abstractmethod
    def _validate_config(self) -> None:
        """验证配置是否完整"""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """同步生成文本"""
        pass

    @abstractmethod
    async def generate_async(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """异步生成文本"""
        pass

    @abstractmethod
    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式生成文本"""
        pass

    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """构建消息列表"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _safe_json_parse(self, text: str) -> Optional[Dict]:
        """安全解析 JSON"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.config.name}, model={self.config.model})"
