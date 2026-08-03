# backend/tests/test_fact_sources.py
"""外部事实核查来源库测试。"""
import pytest
from app.services.fact_sources import FactSource, FactSourceRegistry, get_source_registry


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


def test_normalized_value_scales_float_by_unit():
    # float 值按 unit 换算到"亿元"基准（4.15 万亿元 → 41500）
    fs = FactSource(metric="x", value=4.15, unit="万亿元", source="财政部", year=2025)
    assert fs.normalized_value() == pytest.approx(41500.0, abs=50.0)


def test_normalized_value_wan_pingfang_meter():
    # 97400 万平方米 → 9.74 亿平方米（万平方米 = 0.0001 亿平方米）
    fs = FactSource(metric="x", value=97400, unit="万平方米", source="统计局", year=2024)
    assert fs.normalized_value() == pytest.approx(9.74, abs=0.01)


@pytest.mark.parametrize("metric,expected", [
    ("土地出让收入2025", 41500.0),
    ("土地出让收入2021", 87051.0),
    ("隐性债务2023末", 143000.0),
    ("房价收入比2024中国", 29.6),
    ("商业银行不良率2025Q2", 1.49),
    ("保交楼2023", 300.0),
    ("商品房销售面积2024", 9.74),
])
def test_builtin_normalized_values_yuan_basis(metric, expected):
    reg = get_source_registry()
    src = reg.lookup(metric)
    assert src is not None
    assert src.normalized_value() == pytest.approx(expected, rel=1e-6)


def test_register_custom_source():
    # 用全新注册表，避免污染模块级单例（保证测试顺序无关）
    reg = FactSourceRegistry()
    reg.register(FactSource(metric="自定义指标", value=1.0, unit="万元", source="测试", year=2025))
    assert reg.lookup("自定义指标") is not None


def test_register_does_not_override_builtin():
    reg = FactSourceRegistry()
    reg.register(FactSource(metric="土地出让收入2025", value=999.0, unit="万亿元", source="恶意", year=2025))
    src = reg.lookup("土地出让收入2025")
    assert src.source == "财政部"


def test_register_does_not_override_builtin_alias():
    # 别名冲突同样跳过（"土地出让峰值" 是内置别名）
    reg = FactSourceRegistry()
    reg.register(FactSource(metric="新增指标", value=1.0, unit="亿元", source="测试", year=2025,
                            aliases=["土地出让峰值"]))
    assert reg.lookup("新增指标") is None
    assert reg.lookup("土地出让峰值").source == "财政部"


def test_list_sources_dedupes_aliases():
    reg = FactSourceRegistry()
    sources = reg.list_sources()
    metrics = [s.metric for s in sources]
    assert len(metrics) == len(set(metrics))
    assert len(sources) == len(reg.BUILTIN)
