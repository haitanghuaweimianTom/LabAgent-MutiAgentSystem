"""Provider 注册表"""
import logging
from typing import Callable, Dict, Optional, Type

from .base import PaperMetadataProvider

logger = logging.getLogger(__name__)


class MetadataProviderRegistry:
    """论文元数据 Provider 装饰器注册表。

    用法：
        @metadata_registry.register("semantic_scholar")
        class SemanticScholarProvider(PaperMetadataProvider):
            ...

        provider_class = metadata_registry.get("semantic_scholar")
    """

    def __init__(self):
        self._providers: Dict[str, Type[PaperMetadataProvider]] = {}

    def register(self, name: str) -> Callable[[Type[PaperMetadataProvider]], Type[PaperMetadataProvider]]:
        def decorator(cls: Type[PaperMetadataProvider]) -> Type[PaperMetadataProvider]:
            if not issubclass(cls, PaperMetadataProvider):
                raise TypeError(f"{cls.__name__} must inherit from PaperMetadataProvider")
            cls.name = name
            self._providers[name] = cls
            logger.debug(f"Registered metadata provider: {name}")
            return cls

        return decorator

    def get(self, name: str) -> Optional[Type[PaperMetadataProvider]]:
        return self._providers.get(name)

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())


metadata_registry = MetadataProviderRegistry()
