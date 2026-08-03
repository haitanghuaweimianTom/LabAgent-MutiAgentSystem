# backend/tests/test_external_fact_checker.py
"""外部事实核查器测试：论文数字断言 vs 权威来源库。"""
import pytest
from app.services.external_fact_checker import ExternalFactChecker
from app.services.fact_sources import FactSource, get_source_registry


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
