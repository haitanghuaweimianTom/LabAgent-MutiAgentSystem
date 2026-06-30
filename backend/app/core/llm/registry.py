"""Provider registry for the unified LLM client."""
from __future__ import annotations

from typing import Dict, Type

from .adapters.base import BaseAdapter


class ProviderRegistry:
    """Maps provider type strings to adapter classes."""

    def __init__(self):
        self._adapters: Dict[str, Type[BaseAdapter]] = {}
        self._aliases: Dict[str, str] = {}

    def register(self, adapter_cls: Type[BaseAdapter]) -> Type[BaseAdapter]:
        """Decorator / imperative registration."""
        self._adapters[adapter_cls.provider_type] = adapter_cls
        return adapter_cls

    def register_alias(self, alias: str, target_type: str) -> None:
        """Register a type alias (e.g. ``gemini`` -> ``google_gemini``)."""
        self._aliases[alias] = target_type

    def get(self, provider_type: str) -> Type[BaseAdapter]:
        target = self._aliases.get(provider_type, provider_type)
        try:
            return self._adapters[target]
        except KeyError as exc:
            raise ValueError(f"Unsupported provider type: {provider_type}") from exc

    def supported_types(self) -> list[str]:
        return list(self._adapters.keys()) + list(self._aliases.keys())


# Global registry populated by adapter modules on import.
_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    return _registry


def register_adapter(adapter_cls: Type[BaseAdapter]) -> Type[BaseAdapter]:
    return _registry.register(adapter_cls)


def register_alias(alias: str, target_type: str) -> None:
    _registry.register_alias(alias, target_type)
