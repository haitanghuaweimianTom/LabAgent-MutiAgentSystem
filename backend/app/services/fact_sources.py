"""权威事实来源注册表。

用途：给事实核查（ExternalFactChecker）提供可查询的"权威来源库"。
每个来源 = 一个"指标名 → 权威数值 + 来源 + 年份 + 单位"。指标名支持
别名（key 与 aliases）。数值统一归一化为"基础单位数值"以便比对。

来源数据必须来自公开权威渠道（财政部/国家统计局/央行/金融监管总局等），
禁止写入编造值。新增来源只允许追加，不允许删除内置条目。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# 单位到"倍率"的映射（把单位值统一换算到"亿元"基准口径）
UNIT_MULT: dict = {
    "亿元": 1.0, "万亿元": 10000.0, "万元": 0.0001, "万平方米": 0.0001,
    "%": 1.0, "pp": 1.0, "万套": 1.0, "亿平方米": 1.0,
    "万亿": 10000.0, "亿": 1.0,
}


@dataclass
class FactSource:
    """一条权威事实。

    - metric: 规范化指标名（如 "土地出让收入2025"）
    - value:  数值或 "数值+单位" 字符串（如 "87051亿"）
    - unit:   基础单位（如 "亿元" / "万亿元" / "%" / "万套" / "亿平方米"）
    - source: 来源机构（如 "财政部"）
    - year:   数据年份
    - aliases: 别名列表（同义表述，如 ["2025年土地出让", "土地出让2025"]）
    """
    metric: str
    value: float | str
    unit: str
    source: str
    year: int
    aliases: List[str] = field(default_factory=list)

    def normalized_value(self) -> float:
        """返回以"亿元"为基准口径的数值（供外部事实核查比对）。

        数值为 float 时按 self.unit 倍率换算，如 4.15 万亿元 → 41500.0；
        数值为字符串时解析尾部单位，如 "87051亿" → 87051.0、"4.15万亿" → 41500.0。
        """
        if isinstance(self.value, (int, float)):
            return float(self.value) * UNIT_MULT.get(self.unit, 1.0)
        s = str(self.value).strip()
        m = re.match(r"^([-+]?\d+(?:\.\d+)?)\s*(万亿元|亿元|亿平方米|万平方米|万套|万亿|亿|万元|pp|%)?$", s)
        if not m:
            return float("nan")
        num = float(m.group(1))
        unit = m.group(2) or ""
        mult = UNIT_MULT.get(unit, 1.0)
        return num * mult


class FactSourceRegistry:
    """内置权威来源 + 运行时注册表。"""

    # 内置来源（全部核验自公开权威渠道，来源见 数据真实性声明）
    BUILTIN: List[FactSource] = [
        # —— 财政部 ——
        FactSource("土地出让收入2021", 87051.0, "亿元", "财政部", 2021,
                   aliases=["2021年土地出让收入", "土地出让峰值"]),
        FactSource("土地出让收入2025", 4.15, "万亿元", "财政部", 2025,
                   aliases=["2025年土地出让收入", "土地出让收入41518亿"]),
        FactSource("土地出让收入2024", 48699.0, "亿元", "财政部", 2024,
                   aliases=["2024年土地出让收入"]),
        FactSource("隐性债务2023末", 14.3, "万亿元", "财政部", 2023,
                   aliases=["隐性债务2023", "隐性债务余额2023"]),
        FactSource("隐性债务2024末", 11.0, "万亿元", "财政部", 2024,
                   aliases=["隐性债务2024"]),
        FactSource("隐性债务2028目标", 2.3, "万亿元", "财政部", 2028,
                   aliases=["2028年隐性债务目标"]),
        # —— 国家统计局 ——
        FactSource("商品房销售面积2024", 9.74, "亿平方米", "国家统计局", 2024,
                   aliases=["2024年销售面积"]),
        FactSource("商品房销售面积2021", 17.94, "亿平方米", "国家统计局", 2021,
                   aliases=["2021年销售面积", "销售面积峰值"]),
        FactSource("房价收入比2024中国", 29.6, "", "Numbeo", 2024,
                   aliases=["中国房价收入比"]),
        # —— 金融监管总局 ——
        FactSource("商业银行不良率2025Q2", 1.49, "%", "金融监管总局", 2025,
                   aliases=["不良贷款率2025", "不良率1.49"]),
        # —— 住房和城乡建设部 ——
        FactSource("保交楼2023", 300.0, "万套", "住房和城乡建设部", 2023,
                   aliases=["保交楼交付2023"]),
        FactSource("保交楼2024", 338.0, "万套", "住房和城乡建设部", 2024,
                   aliases=["保交楼交付2024"]),
    ]

    def __init__(self):
        self._sources: dict = {}
        for src in self.BUILTIN:
            self._add(src)

    def _add(self, src: FactSource) -> None:
        self._sources[src.metric] = src
        for alias in src.aliases:
            self._sources[alias] = src

    def register(self, src: FactSource) -> None:
        """运行时追加来源（不覆盖已有条目：指标名或别名冲突时跳过）。"""
        if src.metric in self._sources:
            return
        if any(alias in self._sources for alias in src.aliases):
            return
        self._add(src)

    def lookup(self, key: str) -> Optional[FactSource]:
        """按指标名或别名查找。"""
        return self._sources.get(key)

    def list_sources(self) -> List[FactSource]:
        """返回去重后的唯一来源列表（按指标名去重，保留插入顺序）。"""
        seen: dict = {}
        for src in self._sources.values():
            seen[src.metric] = src
        return list(seen.values())


_registry: Optional[FactSourceRegistry] = None


def get_source_registry() -> FactSourceRegistry:
    global _registry
    if _registry is None:
        _registry = FactSourceRegistry()
    return _registry
