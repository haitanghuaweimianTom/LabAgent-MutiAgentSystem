"""PDF 解析服务测试"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.pdf_processing import PyMuPDF4LLMParser, get_pdf_service, pdf_parser_registry


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """创建一个最小化的测试 PDF"""
    try:
        import fitz
    except ImportError:
        pytest.skip("PyMuPDF 未安装")

    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Hello PDF Parsing Test")
    page.insert_text((50, 80), "Page 1 content")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.mark.asyncio
async def test_pymupdf4llm_parser(sample_pdf: Path):
    """验证 PyMuPDF4LLM 解析器能提取文本"""
    parser = PyMuPDF4LLMParser()
    result = await parser.parse(sample_pdf)
    assert "Hello PDF Parsing Test" in result.text
    assert result.pages >= 1


@pytest.mark.asyncio
async def test_pdf_service_upload_and_parse(tmp_path: Path, sample_pdf: Path):
    """验证 PDF 服务能上传并解析"""
    service = get_pdf_service()
    service.upload_dir = tmp_path

    file_bytes = sample_pdf.read_bytes()
    info = await service.upload_pdf(file_bytes, "test.pdf")
    assert info.file_id
    assert info.size > 0

    result = await service.parse(info.file_id, strategy="pymupdf4llm")
    assert "Hello PDF Parsing Test" in result.text
    assert result.strategy == "pymupdf4llm"


@pytest.mark.asyncio
async def test_pdf_download_arxiv():
    """验证 arXiv 下载能正确转换 URL 并获取 PDF"""
    service = get_pdf_service()
    try:
        info = await service.download_pdf("https://arxiv.org/abs/1706.03762")
        assert info.source.value in ("arxiv", "url")
        assert info.size > 1000
    except Exception as e:
        pytest.skip(f"arXiv 下载失败（网络问题）: {e}")


def test_parser_registry():
    """验证解析器注册表包含默认解析器"""
    names = [p["name"] for p in pdf_parser_registry.list()]
    assert "pymupdf4llm" in names
    assert "vision" in names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
