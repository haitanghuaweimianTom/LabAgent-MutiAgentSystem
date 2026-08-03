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
