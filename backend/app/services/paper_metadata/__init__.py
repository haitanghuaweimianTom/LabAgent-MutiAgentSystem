"""论文元数据增强 Provider 包"""
from .base import PaperMetadataProvider
from .registry import metadata_registry
from .semantic_scholar import SemanticScholarProvider


def get_metadata_enricher(name: str) -> PaperMetadataProvider:
    """根据名称获取已注册的 Provider 实例。

    Args:
        name: provider 名称，如 "semantic_scholar"。

    Returns:
        Provider 实例。

    Raises:
        ValueError: 未找到对应 provider。
    """
    cls = metadata_registry.get(name)
    if not cls:
        raise ValueError(f"Unknown metadata provider: {name}. Available: {metadata_registry.list_providers()}")
    return cls()


__all__ = [
    "PaperMetadataProvider",
    "metadata_registry",
    "SemanticScholarProvider",
    "get_metadata_enricher",
]
