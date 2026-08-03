# backend/tests/test_external_fact_checker_integration.py
"""验证外部核查接入后，冲突数字会拉低 passed。"""
from app.agents.langgraph_orchestrator import LangGraphConfig
from app.services.external_fact_checker import ExternalFactChecker
from app.services.fact_sources import get_source_registry


def test_conflict_breaks_passed():
    checker = ExternalFactChecker(get_source_registry())
    findings = checker.check_text("2025年土地出让收入为5.0万亿元。",
                                  known_aliases=["土地出让收入2025"])
    assert any(f.status == "CONFLICT" for f in findings)


def test_correct_value_passes():
    checker = ExternalFactChecker(get_source_registry())
    findings = checker.check_text("2025年土地出让收入为4.15万亿元。",
                                  known_aliases=["土地出让收入2025"])
    assert all(f.status in ("VERIFIED", "UNVERIFIED") for f in findings)


def test_langgraph_config_has_external_flag():
    cfg = LangGraphConfig()
    assert hasattr(cfg, "enable_external_fact_check")
    assert cfg.enable_external_fact_check is True


def test_unverified_near_miss_tracks_best_rel():
    # 无 known_aliases 全文档扫描：每个断言都能找到最近候选（best_rel 非 None）。
    # 与权威值同量级但判为无来源的（rel≤3）是"近似无来源"风险；
    # 量级完全无关的（rel>3）不算。
    checker = ExternalFactChecker(get_source_registry())
    findings = checker.check_text(
        "2024年商品房销售面积约为12亿平方米，而全国GDP总量约126万亿元。"
    )
    assert all(f.best_rel is not None for f in findings)
    by_assertion = {f.assertion: f for f in findings}
    assert any(f.best_rel <= 3.0 for f in findings)  # 销售面积12 vs 17.94 同量级
    assert any(f.best_rel > 3.0 for f in findings)   # GDP 126万亿 vs 隐性债务 143000亿 量级差大
