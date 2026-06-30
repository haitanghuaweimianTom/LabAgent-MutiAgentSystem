"""LLM provider adapters.

Importing this package (or calling ``import_all_adapters``) registers every
adapter with the global :class:`ProviderRegistry`.
"""

_ORDERS = [
    "openai",
    "openai_responses",
    "openai_assistants",
    "azure_openai",
    "openai_compatible",
    "anthropic",
    "anthropic_bedrock",
    "anthropic_vertex",
    "anthropic_batch",
    "dashscope",
    "zhipu",
    "google_gemini",
    "ollama",
    "custom_http",
]


def import_all_adapters() -> None:
    """Import all adapter modules to populate the registry."""
    for name in _ORDERS:
        __import__(f"app.core.llm.adapters.{name}", fromlist=["app"])


# Auto-register on first import of this package.
import_all_adapters()

# Backwards-compatible aliases for legacy provider type names.
from ..registry import register_alias

register_alias("gemini", "google_gemini")
