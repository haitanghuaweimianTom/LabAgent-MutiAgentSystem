"""PyMuPDF4LLM / PyMuPDF 保底 PDF 解析器"""
import logging
from pathlib import Path
from typing import Any, Dict

import fitz  # PyMuPDF

from ..base import PDFParser, ParseResult, ParseStatus
from ..registry import parser_registry

logger = logging.getLogger(__name__)


def _get_pymupdf4llm() -> Any:
    """尝试导入 pymupdf4llm，未安装则返回 None。"""
    try:
        import pymupdf4llm
        return pymupdf4llm
    except ImportError:
        return None


@parser_registry.register("pymupdf4llm", priority=100, free=True, fast=True, supports_ocr=False)
class PyMuPDF4LLMParser(PDFParser):
    """基于 PyMuPDF4LLM / PyMuPDF 的免费 PDF 解析器。

    - 优先使用 pymupdf4llm.to_markdown() 生成 Markdown（含表格结构）。
    - 若未安装 pymupdf4llm，回退到 fitz 原生 get_text()。
    """

    name = "pymupdf4llm"

    async def parse(self, pdf_path: str) -> ParseResult:
        path = Path(pdf_path)
        if not path.exists():
            return ParseResult.failed(f"PDF file not found: {pdf_path}", method=self.name)

        try:
            pymupdf4llm = _get_pymupdf4llm()
            if pymupdf4llm:
                md_text = pymupdf4llm.to_markdown(str(path))
                plain_text = self._markdown_to_plain(md_text)
            else:
                md_text, plain_text = self._extract_with_fitz(str(path))

            page_count = self._get_page_count(str(path))
            has_images = self._has_images(str(path))

            return ParseResult(
                text=plain_text,
                markdown=md_text,
                page_count=page_count,
                has_images=has_images,
                method=self.name,
                status=ParseStatus.COMPLETED,
            )
        except Exception as e:
            logger.warning(f"PyMuPDF4LLM parser failed for {pdf_path}: {e}")
            return ParseResult.failed(str(e), method=self.name)

    @staticmethod
    def _markdown_to_plain(markdown: str) -> str:
        """简单把 Markdown 转成纯文本（去掉 #、* 等标记）。"""
        lines = markdown.split("\n")
        cleaned = []
        for line in lines:
            line = line.strip()
            if line.startswith("#"):
                line = line.lstrip("#").strip()
            line = line.replace("**", "").replace("*", "").replace("`", "")
            if line:
                cleaned.append(line)
        return "\n".join(cleaned)

    @staticmethod
    def _extract_with_fitz(pdf_path: str) -> tuple[str, str]:
        """使用 fitz 原生方法提取文本。"""
        doc = fitz.open(pdf_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        plain = "\n\n".join(text_parts)
        # 简单包装成 markdown：按段落
        md = plain.replace("\n\n", "\n\n")
        return md, plain

    @staticmethod
    def _get_page_count(pdf_path: str) -> int:
        try:
            doc = fitz.open(pdf_path)
            count = doc.page_count
            doc.close()
            return count
        except Exception:
            return 0

    @staticmethod
    def _has_images(pdf_path: str) -> bool:
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                if page.get_images():
                    doc.close()
                    return True
            doc.close()
            return False
        except Exception:
            return False

    @classmethod
    def is_available(cls) -> bool:
        try:
            import fitz  # noqa: F401
            return True
        except ImportError:
            return False
