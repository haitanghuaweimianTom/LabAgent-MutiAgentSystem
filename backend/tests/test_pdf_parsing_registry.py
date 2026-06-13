"""backend.app.pdf_parsing 新解析器抽象层的最小回归测试。"""
import pytest

from app.pdf_parsing import (
    PDFParser,
    ParseResult,
    ParseStatus,
    parser_registry,
)


def test_registry_lists_known_parsers():
    names = {p["name"] for p in parser_registry.list_parsers()}
    assert "pymupdf4llm" in names
    assert "mineru" in names


def test_registry_auto_selects_available_parser():
    parser = parser_registry.get_parser()
    assert parser is not None
    # 在当前开发环境 magic_pdf 未安装，应自动降级到 pymupdf4llm
    assert parser.name == "pymupdf4llm"


def test_registry_unknown_name_returns_none():
    assert parser_registry.get_parser("not-a-parser") is None


@pytest.mark.asyncio
async def test_parse_nonexistent_file_returns_failed_result(tmp_path):
    parser = parser_registry.get_parser("pymupdf4llm")
    assert parser is not None
    result = await parser.parse(str(tmp_path / "does-not-exist.pdf"))
    assert result.status == ParseStatus.FAILED
    assert "not found" in (result.error or "").lower()


def test_failed_factory_sets_status():
    r = ParseResult.failed("boom", method="pymupdf4llm")
    assert r.status == ParseStatus.FAILED
    assert r.method == "pymupdf4llm"
    assert r.to_dict()["status"] == "failed"
