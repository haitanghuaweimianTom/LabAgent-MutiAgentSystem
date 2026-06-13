"""PDF 处理服务入口"""
import asyncio
import logging
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from ...core.paths import get_data_dir, get_project_data_dir
from ...schemas.pdf import PdfFileInfo, PdfParseResult, PdfSource
from .base import pdf_parser_registry
from .pymupdf4llm_parser import PyMuPDF4LLMParser
from .vision_parser import VisionPdfParser

logger = logging.getLogger(__name__)


class PdfProcessingService:
    """PDF 处理服务：上传、下载、解析、管理"""

    def __init__(self, upload_dir: Optional[Path] = None):
        self.upload_dir = upload_dir or get_data_dir()
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        # 注册默认解析器
        self._ensure_default_parsers()

    def _ensure_default_parsers(self) -> None:
        """确保默认解析器已实例化并注册"""
        if pdf_parser_registry.get("pymupdf4llm") is None:
            pdf_parser_registry.register("pymupdf4llm")(PyMuPDF4LLMParser)
        if pdf_parser_registry.get("vision") is None:
            pdf_parser_registry.register("vision")(VisionPdfParser)

    def get_storage_dir(self, project_name: Optional[str] = None) -> Path:
        if project_name:
            return get_project_data_dir(project_name)
        return self.upload_dir

    async def upload_pdf(
        self,
        file_bytes: bytes,
        filename: str,
        project_name: Optional[str] = None,
    ) -> PdfFileInfo:
        """保存上传的 PDF 文件"""
        storage_dir = self.get_storage_dir(project_name)
        file_id = uuid4().hex[:12]
        safe_name = Path(filename).name
        save_name = f"{file_id}_{safe_name}"
        save_path = storage_dir / save_name

        with open(save_path, "wb") as f:
            f.write(file_bytes)

        pages = self._count_pages(save_path)
        return PdfFileInfo(
            file_id=file_id,
            filename=safe_name,
            size=len(file_bytes),
            pages=pages,
            source=PdfSource.UPLOAD,
            uploaded_at=asyncio.get_event_loop().time(),
        )

    async def download_pdf(
        self,
        url: str,
        filename: Optional[str] = None,
        project_name: Optional[str] = None,
        timeout: float = 60.0,
    ) -> PdfFileInfo:
        """从 URL 下载 PDF"""
        # 支持 arXiv 摘要页自动转换
        if "arxiv.org" in url and "/abs/" in url:
            arxiv_id = url.split("/abs/")[-1].split("?")[0].strip()
            url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            filename = filename or f"{arxiv_id}.pdf"

        parsed = urlparse(url)
        if not filename:
            filename = Path(parsed.path).name or "downloaded.pdf"
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        storage_dir = self.get_storage_dir(project_name)
        file_id = uuid4().hex[:12]
        save_name = f"{file_id}_{filename}"
        save_path = storage_dir / save_name

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.content
            if not content:
                raise ValueError("下载内容为空")

        with open(save_path, "wb") as f:
            f.write(content)

        pages = self._count_pages(save_path)
        source = PdfSource.ARXIV if "arxiv.org" in url else PdfSource.URL
        return PdfFileInfo(
            file_id=file_id,
            filename=filename,
            size=len(content),
            pages=pages,
            source=source,
            url=url,
            uploaded_at=asyncio.get_event_loop().time(),
        )

    async def parse(
        self,
        file_id: str,
        strategy: str = "auto",
        pages: Optional[List[int]] = None,
        project_name: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> PdfParseResult:
        """解析 PDF"""
        options = options or {}
        file_path = self._find_file(file_id, project_name)
        if not file_path:
            return PdfParseResult(
                file_id=file_id,
                filename="",
                source=PdfSource.UPLOAD,
                strategy=strategy,
                errors=["文件不存在"],
            )

        filename = file_path.name
        source = PdfSource.UPLOAD
        if "_arxiv_" in filename or (file_id.startswith("arxiv_")):
            source = PdfSource.ARXIV

        # 自动选择策略
        actual_strategy = strategy
        if strategy == "auto":
            actual_strategy = self._auto_select_strategy(file_path, options)

        parser = pdf_parser_registry.get(actual_strategy)
        if parser is None:
            # fallback 到 pymupdf4llm
            parser = PyMuPDF4LLMParser()
            actual_strategy = "pymupdf4llm"

        parse_result = await parser.parse(file_path, pages=pages, options=options)

        return PdfParseResult(
            file_id=file_id,
            filename=filename,
            source=source,
            strategy=actual_strategy,
            pages=parse_result.pages,
            text=parse_result.text,
            markdown=parse_result.markdown,
            page_contents=parse_result.page_contents,
            metadata=parse_result.metadata,
            errors=parse_result.errors,
        )

    def list_files(self, project_name: Optional[str] = None) -> List[PdfFileInfo]:
        """列出所有 PDF 文件"""
        storage_dir = self.get_storage_dir(project_name)
        files = []
        for f in storage_dir.glob("*.pdf"):
            # 解析 file_id 前缀
            file_id = f.stem.split("_")[0] if "_" in f.stem else f.stem
            stat = f.stat()
            files.append(
                PdfFileInfo(
                    file_id=file_id,
                    filename=f.name,
                    size=stat.st_size,
                    pages=self._count_pages(f),
                    source=PdfSource.UPLOAD,
                    uploaded_at=stat.st_mtime,
                )
            )
        return sorted(files, key=lambda x: x.uploaded_at, reverse=True)

    def get_file_path(self, file_id: str, project_name: Optional[str] = None) -> Optional[Path]:
        return self._find_file(file_id, project_name)

    def delete_file(self, file_id: str, project_name: Optional[str] = None) -> bool:
        file_path = self._find_file(file_id, project_name)
        if file_path and file_path.exists():
            file_path.unlink()
            return True
        return False

    def _find_file(self, file_id: str, project_name: Optional[str] = None) -> Optional[Path]:
        storage_dir = self.get_storage_dir(project_name)
        # 优先精确匹配 file_id 前缀
        for f in storage_dir.glob(f"{file_id}_*.pdf"):
            return f
        # 回退：任何包含 file_id 的 pdf
        for f in storage_dir.glob("*.pdf"):
            if file_id in f.name:
                return f
        return None

    @staticmethod
    def _count_pages(file_path: Path) -> Optional[int]:
        try:
            import fitz
            doc = fitz.open(str(file_path))
            pages = len(doc)
            doc.close()
            return pages
        except Exception:
            return None

    @staticmethod
    def _auto_select_strategy(file_path: Path, options: Dict[str, Any]) -> str:
        """根据文件特征自动选择解析策略"""
        # 如果有 vision_provider 且文件页数少，可尝试 vision
        use_vision = options.get("use_vision", False)
        if use_vision and options.get("vision_provider"):
            try:
                import fitz
                doc = fitz.open(str(file_path))
                pages = len(doc)
                doc.close()
                if pages <= (options.get("vision_max_pages") or 5):
                    return "vision"
            except Exception:
                pass
        return "pymupdf4llm"

    # ====================================================================
    # Phase 5: 统一 PDF 解析入口（直接传路径，绕过 file_id 抽象）
    # ====================================================================

    async def parse_file(
        self,
        file_path: Path,
        mode: str = "auto",
        pages: Optional[List[int]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> "PdfParseResult":
        """Phase 5 统一入口：直接传文件路径。

        Args:
            file_path: 本地 PDF 绝对路径。
            mode: ``"auto"`` / ``"pymupdf4llm"`` / ``"vision"`` / ``"mineru"``。
                ``auto`` 时按启发式（pages<20 && size<5MB → pymupdf；else → vision/mineru）
            pages: 页码列表（1-based）；None 表示全部。
            options: 透传到 parser（如 vision_provider / vision_max_pages）。

        Returns:
            :class:`PdfParseResult` 统一结构。失败时 ``errors`` 非空。
        """
        options = options or {}
        if not file_path.exists():
            return PdfParseResult(
                text="", errors=[f"file not found: {file_path}"]
            )

        # 自动选择策略
        actual_mode = mode
        if mode == "auto":
            actual_mode = self._auto_select_strategy_for_path(file_path, options)

        parser = pdf_parser_registry.get(actual_mode)
        if parser is None:
            # fallback 到 pymupdf4llm
            logger.debug(f"parser '{actual_mode}' not available; fall back to pymupdf4llm")
            parser = PyMuPDF4LLMParser()
            actual_mode = "pymupdf4llm"

        try:
            return await parser.parse(file_path, pages=pages, options=options)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"parse_file failed for {file_path} (mode={actual_mode}): {exc}")
            return PdfParseResult(
                text="", errors=[f"parse failed (mode={actual_mode}): {exc}"],
            )

    @staticmethod
    def _auto_select_strategy_for_path(file_path: Path, options: Dict[str, Any]) -> str:
        """Phase 5 启发式：按页数 + 文件大小 + 视觉请求选 strategy。

        - 显式 ``use_vision=True`` + vision_provider → vision
        - pages < 20 && size < 5MB → pymupdf4llm（快）
        - pages >= 20 || size >= 5MB → vision（高质量，但需要 vision provider）
        - 默认 → pymupdf4llm
        """
        use_vision = options.get("use_vision", False)
        if use_vision and options.get("vision_provider"):
            return "vision"
        try:
            size_mb = file_path.stat().st_size / (1024 * 1024)
            import fitz
            doc = fitz.open(str(file_path))
            pages = len(doc)
            doc.close()
            if pages >= 20 or size_mb >= 5:
                return "vision"  # 长文档或大文件建议 vision
            return "pymupdf4llm"
        except Exception:
            return "pymupdf4llm"


# 全局服务实例
_pdf_service: Optional[PdfProcessingService] = None


def get_pdf_service() -> PdfProcessingService:
    global _pdf_service
    if _pdf_service is None:
        _pdf_service = PdfProcessingService()
    return _pdf_service
