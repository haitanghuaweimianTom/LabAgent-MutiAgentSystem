"""验证外部核查接入后，冲突数字会拉低 passed。"""
from app.services.external_fact_checker import ExternalFactChecker
from app.services.fact_sources import get_source_registry


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
