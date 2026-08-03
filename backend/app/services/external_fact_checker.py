"""外部事实核查器。

作用：把论文/图表中的"数字断言"抽取出来，与权威来源库(FactSourceRegistry)
比对，给出三态判定：
- VERIFIED:    论文数字与权威来源一致（容差内）→ 标注来源
- CONFLICT:    论文数字与同一指标权威值冲突（相对差在 conflict_threshold 内）→ 必须人工复核/打回
- UNVERIFIED:  来源库中无相关权威值 → 提示风险

统一比较基准：亿元。论文中的"万亿"断言会被缩放为亿元口径后再与
normalized_value()（同为亿元口径）比对。

本核查器不产生任何"权威数字"，只消费 FactSourceRegistry 中的核验数据。
无网络调用；如需联网核验新指标，由调用方先把来源注册进 registry 再调用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .fact_sources import UNIT_MULT, FactSource, FactSourceRegistry

_NUM_UNIT_RE = re.compile(
    r"([-+]?\d+(?:\.\d+)?)\s*"
    r"(万亿元|亿元|亿平方米|万平方米|万套|万亿|亿|万元|pp|%)?"
)


@dataclass
class CheckFinding:
    assertion: str       # 论文中的原始表述片段
    reported: Optional[float]  # 亿元口径下的论文数字
    authoritative: Optional[float]  # 亿元口径下的权威值
    status: str          # VERIFIED | CONFLICT | UNVERIFIED
    metric: Optional[str]
    detail: str = ""


class ExternalFactChecker:
    """把论文文本中的数字断言与权威来源库比对（亿元基准）。"""

    def __init__(self, registry: FactSourceRegistry,
                 tolerance: float = 0.02,
                 conflict_threshold: float = 0.3):
        self.registry = registry
        self.tolerance = tolerance
        self.conflict_threshold = conflict_threshold

    def _extract_assertions(self, text: str) -> List[Tuple[str, Optional[float]]]:
        """抽取 (原文片段, 亿元口径数值) 断言。单位按 UNIT_MULT 缩放。"""
        out: List[Tuple[str, Optional[float]]] = []
        for m in _NUM_UNIT_RE.finditer(text):
            num = float(m.group(1))
            unit = m.group(2) or ""
            if not unit:
                continue  # 无单位的裸数字（如年份"2025"）不构成数字断言
            mult = UNIT_MULT.get(unit, 1.0)
            out.append((m.group(0), num * mult))
        return out

    def check_text(self, text: str, known_aliases: Optional[List[str]] = None) -> List[CheckFinding]:
        """对一段文本做外部核验。

        known_aliases: 调用方提供该文本可能对应的权威指标别名（用于精确匹配）。
        - 若 known_aliases 命中来源库指标 → 只在这些候选内匹配；
          全部未命中 → 该断言 UNVERIFIED（无相关权威）。
        - 未提供 known_aliases → 在所有来源中找相对差最小者。
        """
        findings: List[CheckFinding] = []
        candidates: List[FactSource] = []
        if known_aliases:
            seen = set()
            for alias in known_aliases:
                src = self.registry.lookup(alias)
                if src is not None and id(src) not in seen:
                    candidates.append(src)
                    seen.add(id(src))
        else:
            candidates = list(self.registry.list_sources())

        for raw, reported in self._extract_assertions(text):
            if reported is None:
                findings.append(CheckFinding(raw, None, None, "UNVERIFIED", None,
                                             "无法解析数字"))
                continue
            best: Optional[FactSource] = None
            best_rel: Optional[float] = None
            for src in candidates:
                auth = src.normalized_value()
                if auth != auth:  # nan
                    continue
                if reported == 0 or auth == 0:
                    rel = abs(reported - auth)
                else:
                    rel = abs(reported - auth) / max(abs(auth), 1e-9)
                if best is None or rel < best_rel:
                    best, best_rel = src, rel
            if best is None or best_rel is None:
                findings.append(CheckFinding(raw, reported, None, "UNVERIFIED", None,
                                             "无可用来源"))
                continue
            auth_val = best.normalized_value()
            if best_rel <= self.tolerance:
                findings.append(CheckFinding(
                    raw, reported, auth_val, "VERIFIED",
                    best.metric, f"来源：{best.source}（{best.year}）"))
            elif best_rel <= self.conflict_threshold:
                findings.append(CheckFinding(
                    raw, reported, auth_val, "CONFLICT",
                    best.metric,
                    f"权威值 {auth_val:g}（{best.source}）与论文 {reported:g} 冲突"))
            else:
                findings.append(CheckFinding(
                    raw, reported, None, "UNVERIFIED", None, "无匹配来源"))
        return findings
