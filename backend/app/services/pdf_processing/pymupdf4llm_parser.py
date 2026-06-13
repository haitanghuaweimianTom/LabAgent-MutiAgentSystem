"""PyMuPDF4LLM PDF 解析器 —— 保底方案"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import PdfParser, PdfParserResult, pdf_parser_registry

logger = logging.getLogger(__name__)


@pdf_parser_registry.register("pymupdf4llm")
class PyMuPDF4LLMParser(PdfParser):
    """基于 PyMuPDF4LLM 的 PDF 解析器。

    优势：
    - 纯本地，无需外部服务
    - 保留标题、段落、表格的 Markdown 结构
    - 支持页面范围选择

    局限：
    - 对复杂扫描版 PDF 效果一般
    - 公式识别依赖文本层质量
    """

    name = "pymupdf4llm"
    label = "PyMuPDF4LLM"
    description = "本地 Markdown 文本提取（保底方案）"

    def is_available(self) -> bool:
        try:
            import pymupdf4llm  # noqa: F401
            return True
        except Exception:
            return False

    async def parse(
        self,
        file_path: Path,
        pages: Optional[List[int]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> PdfParserResult:
        options = options or {}
        result = PdfParserResult()

        try:
            import pymupdf4llm
            import fitz  # PyMuPDF
        except ImportError as e:
            result.errors.append(f"PyMuPDF4LLM 未安装: {e}")
            return result

        try:
            # 先获取总页数和元数据
            doc = fitz.open(str(file_path))
            total_pages = len(doc)
            result.metadata = {
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "creator": doc.metadata.get("creator", ""),
                "total_pages": total_pages,
            }
            doc.close()

            # 页面范围转换：1-based -> 0-based 页码索引
            page_chunks = None
            if pages:
                page_chunks = [max(0, p - 1) for p in pages if 1 <= p <= total_pages]
                if not page_chunks:
                    result.errors.append("指定的页码范围无效")
                    return result

            # 调用 PyMuPDF4LLM 提取 Markdown
            md_text = pymupdf4llm.to_markdown(
                str(file_path),
                pages=page_chunks,
                **{k: v for k, v in options.items() if k not in ("pages",)},
            )

            result.markdown = md_text or ""
            result.text = self._markdown_to_text(result.markdown)
            result.pages = len(page_chunks) if page_chunks else total_pages

            # 构建逐页内容（按分页符近似）
            result.page_contents = self._split_pages(result.markdown, page_chunks or list(range(total_pages)))

        except Exception as e:
            logger.exception("PyMuPDF4LLM 解析失败")
            result.errors.append(f"解析失败: {e}")

        return result

    @staticmethod
    def _markdown_to_text(markdown: str) -> str:
        """简单将 Markdown 转换为纯文本（保留可读性）"""
        if not markdown:
            return ""
        # 移除图片链接但保留 alt 文本
        import re
        text = re.sub(r"!\[(.*?)\]\(.*?\)", r"\1", markdown)
        # 移除链接保留文本
        text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
        # 移除粗体/斜体标记
        text = re.sub(r"\*\*|__|\\\*\*|\\__", "", text)
        return text.strip()

    @staticmethod
    def _split_pages(markdown: str, page_indices: List[int]) -> List[Dict[str, Any]]:
        """按页面分隔符拆分 Markdown。"""
        import re
        if not markdown:
            return []

        # PyMuPDF4LLM 默认用 "\n---\n" 作为分页符
        parts = re.split(r"\n---\n", markdown)
        page_contents = []
        for i, idx in enumerate(page_indices):
            if i < len(parts):
                page_contents.append({
                    "page_number": idx + 1,
                    "text": parts[i].strip(),
                    "markdown": parts[i].strip(),
                    "images": [],
                    "tables": [],
                })
        return page_contents
