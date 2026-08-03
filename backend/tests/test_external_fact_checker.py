# backend/tests/test_external_fact_checker.py
"""外部事实核查器测试：论文数字断言 vs 权威来源库。"""
import pytest
from app.services.external_fact_checker import ExternalFactChecker
from app.services.fact_sources import get_source_registry


@pytest.fixture
def checker():
    return ExternalFactChecker(get_source_registry())


def test_verifies_matching_number(checker):
    # 论文中土地出让收入2025 = 4.15 万亿 = 41500 亿，来源库归一化为 41500（财政部）
    findings = checker.check_text(
        "2025年土地出让收入为4.15万亿元。",
        known_aliases=["土地出让收入2025"],
    )
    assert findings[0].status == "VERIFIED"
    assert findings[0].reported == pytest.approx(41500.0, abs=50.0)
    assert findings[0].authoritative == pytest.approx(41500.0, abs=50.0)
    assert "财政部" in findings[0].detail


def test_marks_conflict(checker):
    # 论文写 5.0 万亿（=50000 亿），权威值为 4.15 万亿（=41500 亿）
    findings = checker.check_text(
        "2025年土地出让收入高达5.0万亿元。",
        known_aliases=["土地出让收入2025"],
    )
    assert findings[0].status == "CONFLICT"
    assert findings[0].reported == pytest.approx(50000.0, abs=50.0)
    assert findings[0].authoritative == pytest.approx(41500.0, abs=50.0)


def test_marks_unverified(checker):
    # known_aliases 指向来源库中不存在的指标 → 无相关权威 → UNVERIFIED
    findings = checker.check_text(
        "某神秘指标为42亿元。",
        known_aliases=["神秘指标2025"],
    )
    assert findings[0].status == "UNVERIFIED"


def test_extracts_numbers_with_units(checker):
    nums = checker._extract_assertions("2024年销售面积9.74亿平方米，不良率1.49%。")
    assert any(abs(v - 9.74) < 0.01 for _, v in nums)
    assert any(abs(v - 1.49) < 0.01 for _, v in nums)


def test_wan_pingfang_meter_scales_to_yi(checker):
    # 97400 万平方米 = 9.74 亿平方米，来源库归一化为 9.74（国家统计局）
    findings = checker.check_text(
        "2024年销售面积为97400万平方米。",
        known_aliases=["商品房销售面积2024"],
    )
    assert findings[0].status == "VERIFIED"
    assert findings[0].reported == pytest.approx(9.74, abs=0.01)


def test_bare_numbers_are_skipped(checker):
    # 无单位的裸数字（如年份）不构成数字断言
    assert checker._extract_assertions("研究于2025年启动，覆盖全国。") == []


def test_no_known_aliases_uses_all_sources(checker):
    # 未提供 known_aliases → 回退到全部来源，命中商品房销售面积2024
    findings = checker.check_text("全国商品房销售面积约为9.74亿平方米。")
    assert any(f.status == "VERIFIED" for f in findings)
