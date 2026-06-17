"""PDF 解析抽象层（Phase 5：与 services/pdf_processing 统一）。

历史：本目录 [base.py](base.py) + [registry.py](registry.py) + [parsers/](parsers/)
是上一提交引入的独立 PDF 抽象层（仅在 LLM Key 缺失的 mock 路径下被使用）。

Phase 5 统一后，本目录作为兼容 shim，所有解析任务统一走
[services/pdf_processing/PdfProcessingService.parse_file()](../services/pdf_processing/pdf_service.py)。
新代码请直接用 PdfProcessingService。

[parsers/pymupdf_parser.py](parsers/pymupdf_parser.py) /
[parsers/mineru_parser.py](parsers/mineru_parser.py) 仍作为独立实现保留
（不会调用 main flow），便于演示 / 实验 / 自定义部署。
"""
from .base import PDFParser, ParseResult, ParseStatus
from .registry import parser_registry  # noqa: F401 兼容旧 import

# 自动导入并注册 parsers 目录下的解析器实现
from . import parsers  # noqa: F401

# Phase 5 兼容：暴露与新服务一致的 ParseResult 别名
ParseOutcome = ParseResult  # 别名

__all__ = [
    "PDFParser",
    "ParseResult",
    "ParseStatus",
    "ParseOutcome",
    "parser_registry",
]
