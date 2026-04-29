"""
LLM 多提供商支持模块
===================

借鉴 cherry-studio 的 Provider 架构设计，
为数学建模多Agent系统提供统一的多 LLM 提供商支持。

使用方法:
    from src.llm import get_provider_manager, ProviderType

    # 方式1: 自动从环境变量创建
    manager = get_provider_manager()
    manager.register(ProviderType.OPENAI)
    result = manager.generate("你好，请介绍一下自己")

    # 方式2: 手动配置
    from src.llm import ProviderConfig, OpenAIProvider
    config = ProviderConfig(
        provider_type=ProviderType.OPENAI,
        name="my-openai",
        api_key="sk-...",
        model="gpt-4o"
    )
    provider = OpenAIProvider(config)
    response = provider.generate("你好")

    # 方式3: 直接使用工厂
    from src.llm import LLMProviderFactory
    provider = LLMProviderFactory.create_from_env()
    response = provider.generate("你好")

环境变量配置:
    OPENAI_API_KEY      - OpenAI API Key
    OPENAI_API_HOST     - OpenAI API 地址 (默认: https://api.openai.com)
    OPENAI_MODEL        - 默认模型 (默认: gpt-4o)

    ANTHROPIC_API_KEY   - Anthropic API Key
    ANTHROPIC_API_HOST  - Anthropic API 地址 (默认: https://api.anthropic.com)
    ANTHROPIC_MODEL     - 默认模型 (默认: claude-3-5-sonnet-20241022)

    GEMINI_API_KEY      - Google Gemini API Key
    GEMINI_API_HOST     - Gemini API 地址
    GEMINI_MODEL        - 默认模型 (默认: gemini-1.5-flash)

    OLLAMA_API_HOST     - Ollama 地址 (默认: http://localhost:11434)
    OLLAMA_MODEL        - 默认模型 (默认: llama3.2)
"""

from .base import (
    BaseLLMProvider,
    ProviderConfig,
    LLMMessage,
    LLMResponse,
    ProviderType,
)
from .factory import (
    LLMProviderFactory,
    LLMProviderManager,
    get_provider_manager,
)
from .providers.openai_provider import OpenAIProvider
from .providers.anthropic_provider import AnthropicProvider
from .providers.gemini_provider import GeminiProvider
from .providers.ollama_provider import OllamaProvider
from .providers.claude_cli_provider import ClaudeCLIProvider

__all__ = [
    "BaseLLMProvider",
    "ProviderConfig",
    "LLMMessage",
    "LLMResponse",
    "ProviderType",
    "LLMProviderFactory",
    "LLMProviderManager",
    "get_provider_manager",
    "OpenAIProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "OllamaProvider",
    "ClaudeCLIProvider",
]
