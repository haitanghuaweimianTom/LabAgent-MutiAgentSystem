"""PDF 解析器注册表"""
import logging
from typing import Any, Callable, Dict, List, Optional, Type

from .base import PDFParser

logger = logging.getLogger(__name__)


class ParserRegistry:
    """可插拔 PDF 解析器注册表。

    用法：
        @parser_registry.register("pymupdf4llm", priority=100)
        class PyMuPDF4LLMParser(PDFParser):
            ...

        parser = parser_registry.get_parser("pymupdf4llm")
        parser = parser_registry.get_parser()  # 自动选择
    """

    def __init__(self):
        self._parsers: Dict[str, Type[PDFParser]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        priority: int = 0,
        **meta: Any,
    ) -> Callable[[Type[PDFParser]], Type[PDFParser]]:
        """装饰器：注册一个 PDF 解析器。"""

        def decorator(cls: Type[PDFParser]) -> Type[PDFParser]:
            if not issubclass(cls, PDFParser):
                raise TypeError(f"{cls.__name__} must inherit from PDFParser")
            cls.name = name
            self._parsers[name] = cls
            self._metadata[name] = {"priority": priority, **meta}
            logger.debug(f"Registered PDF parser: {name} (priority={priority})")
            return cls

        return decorator

    def get_parser(self, name: Optional[str] = None) -> Optional[PDFParser]:
        """获取解析器实例。"""
        if name:
            cls = self._parsers.get(name)
            if cls and cls.is_available():
                return cls()
            logger.warning(f"Requested PDF parser '{name}' not available")
            return None

        # 自动选择：按优先级降序，选择第一个可用的
        available = [
            (n, m)
            for n, m in self._metadata.items()
            if self._parsers[n].is_available()
        ]
        available.sort(key=lambda x: x[1]["priority"], reverse=True)
        if not available:
            logger.warning("No PDF parser available")
            return None

        selected_name, _ = available[0]
        return self._parsers[selected_name]()

    def list_parsers(self) -> List[Dict[str, Any]]:
        """列出所有已注册解析器及其可用性。"""
        return [
            {
                "name": n,
                "available": self._parsers[n].is_available(),
                **self._metadata[n],
            }
            for n in self._parsers
        ]

    def is_available(self, name: str) -> bool:
        cls = self._parsers.get(name)
        return cls.is_available() if cls else False


parser_registry = ParserRegistry()
