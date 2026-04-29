"""
文档处理模块
============

借鉴 cherry-studio 的文档预处理设计，
为数学建模多Agent系统提供多格式文档读取能力。

支持的格式:
- Excel (.xlsx, .xls) - 已支持
- Word (.docx) - 通过 python-docx
- PDF (.pdf) - 通过 PyPDF2/pypdf（需安装）
- Markdown (.md) - 原生支持
- Text (.txt) - 原生支持
- CSV (.csv) - 通过 pandas

使用方法:
    from src.document_processing import DocumentLoader

    loader = DocumentLoader()

    # 自动检测格式并加载
    content = loader.load("data.pdf")

    # 批量加载
    contents = loader.load_directory("documents/")

    # 加载到知识库
    from src.knowledge import KnowledgeBase
    kb = KnowledgeBase()
    loader.load_to_knowledge_base("documents/", kb)
"""

from .loader import DocumentLoader, DocumentContent, LoadResult

__all__ = [
    "DocumentLoader",
    "DocumentContent",
    "LoadResult",
]
