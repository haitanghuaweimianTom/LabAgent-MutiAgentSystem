# backend/tests/test_fact_sources.py
"""外部事实核查来源库测试。"""
import pytest
from app.services.fact_sources import get_source_registry, FactSource


def test_registry_loads_builtin_sources():
    reg = get_source_registry()
    assert len(reg.list_sources()) > 0


def test_lookup_land_revenue_2025():
    reg = get_source_registry()
    src = reg.lookup("土地出让收入2025")
    assert src is not None
    assert src.value == pytest.approx(4.15, abs=0.01)
    assert "财政部" in src.source


def test_lookup_unknown_returns_none():
    reg = get_source_registry()
    assert reg.lookup("完全不存在指标xyz") is None


def test_fact_source_normalizes_value():
    # 字符串值也能解析（"87051亿" → 87051.0）
    fs = FactSource(metric="test", value="87051亿", unit="亿元", source="财政部", year=2021)
    assert fs.normalized_value() == pytest.approx(87051.0, abs=0.5)


def test_register_custom_source():
    reg = get_source_registry()
    reg.register(FactSource(metric="自定义指标", value=1.0, unit="万元", source="测试", year=2025))
    assert reg.lookup("自定义指标") is not None
