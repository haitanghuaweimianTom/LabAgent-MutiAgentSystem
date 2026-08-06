# backend/tests/test_external_fact_checker.py
"""外部事实核查器测试：论文数字断言 vs 权威来源库。"""
import pytest
from app.services.external_fact_checker import ExternalFactChecker
from app.services.fact_sources import get_source_registry


@pytest.fixture
def checker():
    return ExternalFactChecker(get_source_registry())


def test_verifies_matching_number(checker):
    # 论文中土地出让收入2025 = 4.15 万亿，来源库有 4.15（财政部）
    findings = checker.check_text(
        "2025年土地出让收入为4.15万亿元。",
        known_aliases=["土地出让收入2025"],
    )
    assert findings[0].status == "VERIFIED"
    assert "财政部" in findings[0].detail


def test_marks_conflict(checker):
    # 论文写 5.0 万亿，但权威值为 4.15
    findings = checker.check_text(
        "2025年土地出让收入高达5.0万亿元。",
        known_aliases=["土地出让收入2025"],
    )
    assert findings[0].status == "CONFLICT"
    assert findings[0].reported == pytest.approx(5.0, abs=0.01)
    assert findings[0].authoritative == pytest.approx(4.15, abs=0.01)


def test_marks_unverified(checker):
    # 无来源库匹配 → UNVERIFIED
    findings = checker.check_text(
        "某神秘指标为42亿元。",
        known_aliases=["神秘指标2025"],
    )
    assert findings[0].status == "UNVERIFIED"


def test_extracts_numbers_with_units(checker):
    nums = checker._extract_assertions("2024年销售面积9.74亿平方米，不良率1.49%。")
    assert ("9.74", "亿平方米") in nums or 9.74 in [n[0] for n in nums]


def test_unverified_does_not_fail(checker):
    # UNVERIFIED 不应拉低 passed（预测值/未收录指标是合法的）
    findings = checker.check_text("土地面积约为1000万亩。")
    unv = [f for f in findings if f.status == "UNVERIFIED"]
    assert unv  # 有 UNVERIFIED 条目
    assert not any(f.status == "CONFLICT" for f in findings)
