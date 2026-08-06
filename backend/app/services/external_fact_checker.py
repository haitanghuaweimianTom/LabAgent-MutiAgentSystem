"""外部事实核查器（确定性权威来源核验）。

作用：把论文文本中的"数字断言"抽取出来，与权威来源库(FactSourceRegistry)
比对，给出三态判定，打破"两个造假者互相对口供"的死结：
- VERIFIED:    论文数字与权威来源一致（容差内 tolerance=0.02）→ 标注来源
- CONFLICT:    论文数字与权威来源冲突（来源库命中指标但数值超容差）
                → 必须打回人工、拉低 passed
- UNVERIFIED:  论文数字在来源库找不到命中指标 → 仅提示风险，不拦

命中规则：来源只有"指标名或别名出现在论文文本 / 或由 known_aliases 明确锚定"
才算命中；未命中的数字一律 UNVERIFIED（不凭空给数值挂靠最近来源）。
论文数字按字面数值（不再跨单位换算）与来源的 normalized_value() 比对——
registry 中各来源数值已保持自身单位口径，双方口径一致才可比较。

本类只消费 FactSourceRegistry 中的核验数据，不产生任何"权威数字"。
无网络调用。容差 tolerance=0.02 是本地一项决策（学术标准：合理性阈值须本地明确），
避免多任务判定双标。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .fact_sources import FactSource, FactSourceRegistry

_NUM_UNIT_RE = re.compile(
    r"([-+]?\d+(?:\.\d+)?)\s*(万亿元|亿元|亿平方米|万平方米|万套|pp|%)?"
)


@dataclass
class CheckFinding:
    assertion: str          # 论文中的原始数字表述（数字串 + 单位）
    reported: Optional[float]
    authoritative: Optional[float]
    status: str             # VERIFIED | CONFLICT | UNVERIFIED
    metric: Optional[str]
    detail: str = ""


class ExternalFactChecker:
    """把论文文本中的数字断言与权威来源库比对（确定性规则）。"""

    def __init__(self, registry: FactSourceRegistry, tolerance: float = 0.02):
        self.registry = registry
        self.tolerance = tolerance

    def _extract_assertions(self, text: str) -> List[Tuple[str, str]]:
        """抽取 (数字串, 单位) 断言对。纯 4 位年份（1900–2099，如 2025 年）跳过。"""
        out = []
        for m in _NUM_UNIT_RE.finditer(text):
            num = m.group(1).strip()
            unit = m.group(2) or ""
            if not unit and num.isdigit():
                year = int(num)
                if 1900 <= year <= 2099:
                    continue
            out.append((num, unit))
        return out

    def _normalize(self, val: float) -> float:
        """防御性口径统一：registry 的 normalized_value() 已按自身单位归一化，
        论文数字按字面数值比对其口径一致，这里保持原值。"""
        return val

    def _candidate_sources(
        self, text: str, known_aliases: Optional[List[str]]
    ) -> List[FactSource]:
        """确定命中的权威来源：known_aliases 锚定的 + 文本中出现的指标名/别名。"""
        candidates: List[FactSource] = []
        seen = set()

        def add(src: Optional[FactSource]) -> None:
            if src is not None and id(src) not in seen:
                seen.add(id(src))
                candidates.append(src)

        for alias in known_aliases or []:
            add(self.registry.lookup(alias))
        for src in self.registry.list_sources():
            if src.metric in text or any(a in text for a in src.aliases):
                add(src)
        return candidates

    def check_text(
        self, text: str, known_aliases: Optional[List[str]] = None
    ) -> List[CheckFinding]:
        """对一段文本做外部核验。

        known_aliases: 调用方提示该文本可能对应的权威指标别名（用于精确锚定）。
        策略：对每个数字断言，在命中的来源中找数值最接近的；若在容差内
        → VERIFIED；命中指标但超容差 → CONFLICT；来源库无命中 → UNVERIFIED。
        """
        findings: List[CheckFinding] = []
        candidates = self._candidate_sources(text, known_aliases)

        for num, _unit in self._extract_assertions(text):
            reported = self._normalize(float(num))
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

            if best is None:
                findings.append(CheckFinding(num, reported, None, "UNVERIFIED", None,
                                             "来源库无匹配指标"))
            elif best_rel is not None and best_rel <= self.tolerance:
                findings.append(CheckFinding(
                    num, reported, best.normalized_value(), "VERIFIED",
                    best.metric, f"来源：{best.source}（{best.year}）"))
            else:
                findings.append(CheckFinding(
                    num, reported, best.normalized_value(), "CONFLICT",
                    best.metric,
                    f"权威值 {best.normalized_value():g}（{best.source}）与论文 {reported:g} 冲突"))
        return findings
