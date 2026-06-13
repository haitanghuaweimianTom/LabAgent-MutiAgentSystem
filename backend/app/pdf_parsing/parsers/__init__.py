"""PDF 解析器实现集合。

新解析器只需：
1. 继承 ``PDFParser``
2. 用 ``@parser_registry.register("name", priority=...)`` 装饰
3. 实现 ``async def parse(self, pdf_path: str) -> ParseResult``

模块导入时会自动把所有解析器注册到全局 ``parser_registry``。
"""
from .pymupdf_parser import PyMuPDF4LLMParser
from .mineru_parser import MinerUParser

__all__ = ["PyMuPDF4LLMParser", "MinerUParser"]
