"""
LLM Provider 工厂
=================

借鉴 cherry-studio 的 Provider 架构，
实现统一的 Provider 创建和管理。
"""

from typing import Dict, Optional, Type
import os

from .base import BaseLLMProvider, ProviderConfig, ProviderType
from .providers.openai_provider import OpenAIProvider
from .providers.anthropic_provider import AnthropicProvider
from .providers.gemini_provider import GeminiProvider
from .providers.ollama_provider import OllamaProvider
from .providers.claude_cli_provider import ClaudeCLIProvider


class LLMProviderFactory:
    """LLM Provider 工厂类"""

    _providers: Dict[ProviderType, Type[BaseLLMProvider]] = {
        ProviderType.OPENAI: OpenAIProvider,
        ProviderType.ANTHROPIC: AnthropicProvider,
        ProviderType.GEMINI: GeminiProvider,
        ProviderType.OLLAMA: OllamaProvider,
        ProviderType.CLAUDE_CLI: ClaudeCLIProvider,
    }

    @classmethod
    def create(
        cls,
        provider_type: ProviderType,
        config: Optional[ProviderConfig] = None
    ) -> BaseLLMProvider:
        """创建 Provider 实例"""
        provider_class = cls._providers.get(provider_type)
        if not provider_class:
            raise ValueError(f"不支持的 Provider 类型: {provider_type}")
        return provider_class(config)

    @classmethod
    def create_from_env(cls, provider_type: Optional[ProviderType] = None) -> BaseLLMProvider:
        """从环境变量自动创建 Provider"""
        if provider_type is None:
            provider_type = cls._detect_provider_from_env()
        return cls.create(provider_type)

    @classmethod
    def _detect_provider_from_env(cls) -> ProviderType:
        """根据环境变量自动检测 Provider 类型"""
        if os.getenv("OPENAI_API_KEY"):
            return ProviderType.OPENAI
        if os.getenv("ANTHROPIC_API_KEY"):
            return ProviderType.ANTHROPIC
        if os.getenv("GEMINI_API_KEY"):
            return ProviderType.GEMINI
        if os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_MODEL"):
            return ProviderType.OLLAMA
        return ProviderType.CLAUDE_CLI

    @classmethod
    def register(
        cls,
        provider_type: ProviderType,
        provider_class: Type[BaseLLMProvider]
    ) -> None:
        """注册自定义 Provider"""
        cls._providers[provider_type] = provider_class

    @classmethod
    def get_supported_providers(cls) -> Dict[ProviderType, str]:
        """获取支持的 Provider 列表"""
        return {
            ProviderType.OPENAI: "OpenAI API (兼容格式)",
            ProviderType.ANTHROPIC: "Anthropic Claude API",
            ProviderType.GEMINI: "Google Gemini API",
            ProviderType.OLLAMA: "Ollama 本地模型",
            ProviderType.CLAUDE_CLI: "Claude Code CLI",
        }


class LLMProviderManager:
    """LLM Provider 管理器"""

    def __init__(self):
        self._instances: Dict[ProviderType, BaseLLMProvider] = {}
        self._default_provider: Optional[ProviderType] = None

    def register(
        self,
        provider_type: ProviderType,
        config: Optional[ProviderConfig] = None
    ) -> BaseLLMProvider:
        """注册并初始化 Provider"""
        provider = LLMProviderFactory.create(provider_type, config)
        self._instances[provider_type] = provider
        if self._default_provider is None:
            self._default_provider = provider_type
        return provider

    def get(self, provider_type: Optional[ProviderType] = None) -> BaseLLMProvider:
        """获取 Provider 实例"""
        if provider_type is None:
            provider_type = self._default_provider
        if provider_type is None:
            raise ValueError("未设置默认 Provider")
        if provider_type not in self._instances:
            self.register(provider_type)
        return self._instances[provider_type]

    def set_default(self, provider_type: ProviderType) -> None:
        """设置默认 Provider"""
        self._default_provider = provider_type

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        provider_type: Optional[ProviderType] = None,
        **kwargs
    ) -> str:
        """使用指定 Provider 生成文本"""
        provider = self.get(provider_type)
        response = provider.generate(prompt, system_prompt, **kwargs)
        return response.content

    def list_providers(self) -> Dict[ProviderType, BaseLLMProvider]:
        """列出所有已注册的 Provider"""
        return self._instances.copy()


# 全局管理器实例
_default_manager: Optional[LLMProviderManager] = None


def get_provider_manager() -> LLMProviderManager:
    """获取全局 Provider 管理器"""
    global _default_manager
    if _default_manager is None:
        _default_manager = LLMProviderManager()
    return _default_manager
