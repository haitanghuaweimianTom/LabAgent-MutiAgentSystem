"""MinerU PDF 解析器（预留接口）"""
import logging
from pathlib import Path
from typing import Any, Dict

from ..base import PDFParser, ParseResult, ParseStatus
from ..registry import parser_registry

logger = logging.getLogger(__name__)


@parser_registry.register("mineru", priority=90, free=True, chinese_optimized=True, supports_ocr=True)
class MinerUParser(PDFParser):
    """MinerU PDF 解析器（可选安装）。

    MinerU 对中文/CJK 文档、复杂学术排版（公式、表格、图片）效果最好。
    若未安装 magic-pdf，则自动不可用，注册表会回退到其他解析器。
    """

    name = "mineru"

    async def parse(self, pdf_path: str) -> ParseResult:
        path = Path(pdf_path)
        if not path.exists():
            return ParseResult.failed(f"PDF file not found: {pdf_path}", method=self.name)

        try:
            from magic_pdf.data.data_reader_writer import FileBasedDataWriter
            from magic_pdf.data.dataset import PymuDocDataset
            from magic_pdf.model.mk_kernel import analyze_pdf

            pdf_name = path.stem
            output_dir = path.parent / f"{pdf_name}_mineru"
            output_dir.mkdir(parents=True, exist_ok=True)

            image_dir = output_dir / "images"
            image_dir.mkdir(parents=True, exist_ok=True)

            # 读取 PDF 字节
            pdf_bytes = path.read_bytes()
            ds = PymuDocDataset(pdf_bytes)
            analyze_pdf(ds)

            # 获取 markdown 结果（MinerU API 可能因版本不同而变化，这里做通用处理）
            md_text = ""
            if hasattr(ds, "get_markdown"):
                md_text = ds.get_markdown()
            elif hasattr(ds, "to_markdown"):
                md_text = ds.to_markdown()

            plain_text = md_text.replace("#", "").replace("*", "").replace("`", "")

            return ParseResult(
                text=plain_text,
                markdown=md_text,
                page_count=getattr(ds, "page_count", 0),
                has_images=any(image_dir.iterdir()) if image_dir.exists() else False,
                method=self.name,
                status=ParseStatus.COMPLETED,
                metadata={"output_dir": str(output_dir)},
            )
        except Exception as e:
            logger.warning(f"MinerU parser failed for {pdf_path}: {e}")
            return ParseResult.failed(str(e), method=self.name)

    @classmethod
    def is_available(cls) -> bool:
        try:
            import magic_pdf  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def supports_ocr(self) -> bool:
        return True

    @property
    def supports_chinese(self) -> bool:
        return True
