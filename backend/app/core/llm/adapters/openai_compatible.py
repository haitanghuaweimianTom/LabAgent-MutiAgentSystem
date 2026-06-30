"""Generic OpenAI-compatible adapter.

Used for third-party providers that expose the /chat/completions endpoint.
"""
from .openai import OpenAIAdapter
from ..registry import register_adapter


@register_adapter
class OpenAICompatibleAdapter(OpenAIAdapter):
    provider_type = "openai_compatible"
