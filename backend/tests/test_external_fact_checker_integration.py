"""验证外部核查接入后，冲突数字会拉低 passed。"""
import pytest

from app.services.external_fact_checker import ExternalFactChecker
from app.services.fact_sources import get_source_registry
from app.services.fact_correction import correct_latex


def test_conflict_breaks_passed():
    checker = ExternalFactChecker(get_source_registry())
    findings = checker.check_text("2025年土地出让收入为9.0万亿元。",
                                  known_aliases=["土地出让收入2025"])
    assert any(f.status == "CONFLICT" for f in findings)


def test_correct_value_passes():
    checker = ExternalFactChecker(get_source_registry())
    findings = checker.check_text("2025年土地出让收入为4.15万亿元。",
                                  known_aliases=["土地出让收入2025"])
    assert all(f.status in ("VERIFIED", "UNVERIFIED") for f in findings)


def test_unverified_does_not_fail_passed():
    checker = ExternalFactChecker(get_source_registry())
    findings = checker.check_text("某预测值为1.62个百分点。")
    assert all(f.status != "CONFLICT" for f in findings)


@pytest.mark.asyncio
async def test_correct_latex_closes_loop_conflict_to_verified():
    # 核心闭环：拦截的 CONFLICT 数字，纠偏后应变为 VERIFIED（不再搬倒 passed）
    checker = ExternalFactChecker(get_source_registry())
    latex = "2025年土地出让收入为9.0万亿元。"
    findings = checker.check_text(latex, known_aliases=["土地出让收入2025"])
    assert any(f.status == "CONFLICT" for f in findings)

    result = await correct_latex(latex, [f.__dict__ for f in findings])

    assert result.corrections and result.failed == []
    rechecked = checker.check_text(result.latex, known_aliases=["土地出让收入2025"])
    assert all(f.status != "CONFLICT" for f in rechecked)
    assert any(f.status == "VERIFIED" for f in rechecked)
