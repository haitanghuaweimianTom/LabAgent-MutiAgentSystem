"""PDF 解析器抽象基类与注册表"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type


@dataclass
class PdfParserResult:
    """解析器统一返回结果"""
    text: str = ""
    markdown: Optional[str] = None
    pages: int = 0
    page_contents: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class PdfParser(ABC):
    """PDF 解析器抽象基类"""

    name: str = ""
    label: str = ""
    description: str = ""

    @abstractmethod
    async def parse(
        self,
        file_path: Path,
        pages: Optional[List[int]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> PdfParserResult:
        """解析 PDF 文件。

        Args:
            file_path: PDF 文件路径
            pages: 指定页码列表（1-based），None 表示全部
            options: 解析器特定选项
        """
        raise NotImplementedError

    def is_available(self) -> bool:
        """当前解析器是否可用（依赖是否已安装）"""
        return True


class PdfParserRegistry:
    """PDF 解析器注册表"""

    def __init__(self):
        self._parsers: Dict[str, Type[PdfParser]] = {}

    def register(self, name: str) -> Callable[[Type[PdfParser]], Type[PdfParser]]:
        def decorator(cls: Type[PdfParser]) -> Type[PdfParser]:
            if not issubclass(cls, PdfParser):
                raise TypeError(f"{cls.__name__} must inherit from PdfParser")
            cls.name = name
            self._parsers[name] = cls
            return cls

        return decorator

    def get(self, name: str) -> Optional[PdfParser]:
        cls = self._parsers.get(name)
        return cls() if cls else None

    def list(self) -> List[Dict[str, str]]:
        return [
            {"name": cls.name, "label": cls.label, "description": cls.description}
            for cls in self._parsers.values()
        ]


pdf_parser_registry = PdfParserRegistry()
