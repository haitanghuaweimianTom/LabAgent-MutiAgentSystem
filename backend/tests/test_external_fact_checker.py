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
    # 论文写 5.0 万亿(=50000亿)，但权威值为 4.15万亿(=41500亿)
    findings = checker.check_text(
        "2025年土地出让收入高达5.0万亿元。",
        known_aliases=["土地出让收入2025"],
    )
    assert findings[0].status == "CONFLICT"
    assert findings[0].reported == pytest.approx(50000.0, abs=1)
    assert findings[0].authoritative == pytest.approx(41500.0, abs=1)


def test_marks_unverified(checker):
    # 无来源库匹配 → UNVERIFIED
    findings = checker.check_text(
        "某神秘指标为42亿元。",
        known_aliases=["神秘指标2025"],
    )
    assert findings[0].status == "UNVERIFIED"


def test_big_deviation_is_conflict_not_unverified(checker):
    # 锚定到指标源但数值大偏差 → CONFLICT（不能轻易放过造假，R-「全部拦住」）
    findings = checker.check_text(
        "2025年土地出让收入为9.0万亿元。",
        known_aliases=["土地出让收入2025"],
    )
    assert all(f.status == "CONFLICT" for f in findings)


def test_bare_number_skipped(checker):
    # 无单位裸数字（年份/编号）不构成断言 → 不产生 finding，也不误报 CONFLICT
    findings = checker.check_text("2025年发生重大变化。")
    assert findings == []
    assert not any(f.status == "CONFLICT" for f in findings)


def test_unverified_does_not_conflict(checker):
    # 无锚定源的预测值/未收录指标 → UNVERIFIED，不是 CONFLICT
    findings = checker.check_text("某预测值为1.62亿元。")
    unv = [f for f in findings if f.status == "UNVERIFIED"]
    assert unv
    assert not any(f.status == "CONFLICT" for f in findings)
