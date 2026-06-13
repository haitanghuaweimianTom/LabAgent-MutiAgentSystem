"""PDF 解析抽象层。

对外暴露：
- `PDFParser`、``ParseResult``、``ParseStatus``：解析器抽象与结果数据类。
- ``parser_registry``：可插拔的全局解析器注册表。
- ``PyMuPDF4LLMParser``、``MinerUParser``：默认注册的实现，按优先级自动选择。

调用方推荐使用 ``parser_registry.get_parser()`` 而非直接 import 具体类，
以便在某个解析器不可用（如未安装 magic_pdf）时自动回退。
"""
from .base import PDFParser, ParseResult, ParseStatus
from .registry import ParserRegistry, parser_registry
from .parsers.pymupdf_parser import PyMuPDF4LLMParser
from .parsers.mineru_parser import MinerUParser

__all__ = [
    "PDFParser",
    "ParseResult",
    "ParseStatus",
    "ParserRegistry",
    "parser_registry",
    "PyMuPDF4LLMParser",
    "MinerUParser",
]
