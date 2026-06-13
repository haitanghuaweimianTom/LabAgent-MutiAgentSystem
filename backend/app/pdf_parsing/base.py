"""PDF 解析器抽象基类与数据模型"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ParseStatus(str, Enum):
    """PDF 解析状态"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ParseResult:
    """PDF 解析结果"""

    text: str = ""                      # 提取的纯文本
    markdown: str = ""                  # Markdown 格式文本
    page_count: int = 0                 # 页数
    has_images: bool = False            # 是否包含图片
    method: str = ""                    # 使用的解析器名称
    status: ParseStatus = ParseStatus.COMPLETED
    error: Optional[str] = None         # 失败原因
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "markdown": self.markdown,
            "page_count": self.page_count,
            "has_images": self.has_images,
            "method": self.method,
            "status": self.status.value,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def failed(cls, error: str, method: str = "") -> "ParseResult":
        return cls(error=error, method=method, status=ParseStatus.FAILED)


class PDFParser(ABC):
    """PDF 解析器抽象基类。"""

    name: str = ""

    @abstractmethod
    async def parse(self, pdf_path: str) -> ParseResult:
        """解析 PDF 文件，返回 ParseResult。

        Args:
            pdf_path: 本地 PDF 文件绝对路径。

        Returns:
            ParseResult: 解析结果。
        """
        raise NotImplementedError

    @classmethod
    def is_available(cls) -> bool:
        """当前解析器是否可用（依赖是否安装）。默认返回 True。"""
        return True

    @property
    def supports_ocr(self) -> bool:
        """是否支持 OCR 扫描版 PDF。"""
        return False

    @property
    def supports_chinese(self) -> bool:
        """是否针对中文/CJK 优化。"""
        return False
