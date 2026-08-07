"""外部事实核查器（确定性权威来源核验）。

把论文文本中的"数字断言"抽取出来，与权威来源库(FactSourceRegistry)
比对，给出三态判定，打破"两个造假者互相对口供"的死结：
- VERIFIED:    论文数字与权威来源一致（相对差 ≤ tolerance=0.02）→ 标注来源
- CONFLICT:    锚定了权威指标源，但论文数字与之偏差超过 tolerance
                → 必须打回人工、拉低 passed（造假/抄错，一律拦）
- UNVERIFIED:  来源库无命中指标（预测值/未收录指标）→ 仅提示风险，不拦

统一比较基准：亿元（与 FactSource.normalized_value() 同口径）。论文中的
"X亿/X万亿/X万套..."等都会缩放为"亿元"口径后再比对，避免"4.15万亿"
与"4.15亿"被误判一致。

命中规则：来源只有"指标名或别名出现在论文文本 / 或由 known_aliases 明确锚定"
才算命中；未命中的数字一律 UNVERIFIED（不笔误给数值挂靠最近来源）。
只要锚定到指标源，数值对不上就是 CONFLICT——绝不因"帮忙怀疑 Y 像造假"而
把大偏差轻判为 UNVERIFIED。

本类只消费 FactSourceRegistry 中的核验数据，不产生任何"权威数字"。
无网络调用。容差 tolerance 是本地一项决策（学术标准：合理性阈值须本地明确），
避免多任务判定双标。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .fact_sources import FactSource, FactSourceRegistry

_NUM_UNIT_RE = re.compile(
    r"([-+]?\d+(?:\.\d+)?)\s*"
    r"(万亿元|亿元|亿平方米|万平方米|万套|万亿|亿|万元|pp|%)?"
)


@dataclass
class CheckFinding:
    assertion: str               # 论文中的原始数字表述（数字串 + 单位）
    reported: Optional[float]    # 亿元口径下的论文数字
    authoritative: Optional[float]  # 亿元口径下的权威值
    status: str                  # VERIFIED | CONFLICT | UNVERIFIED
    metric: Optional[str]
    detail: str = ""
    best_rel: Optional[float] = None   # 命中候选中最小的相对差（无候选时为 None）


class ExternalFactChecker:
    """把论文文本中的数字断言与权威来源库比对（确定性规则，亿元基准）。"""

    _UNIT_MULT = {
        "万亿元": 10000.0, "亿元": 1.0, "万亿": 10000.0,
        "亿": 1.0, "万元": 0.0001, "万平方米": 0.0001,
        "亿平方米": 1.0, "万套": 1.0, "pp": 1.0, "%": 1.0,
        "万": 1.0,
    }

    def __init__(
        self,
        registry: FactSourceRegistry,
        tolerance: float = 0.02,
    ):
        self.registry = registry
        self.tolerance = tolerance

    def _extract_assertions(self, text: str) -> List[Tuple[str, Optional[float]]]:
        """抽取 (数字串, 亿元口径数值) 断言。无单位的裸数字（年份/编号）跳过。"""
        out = []
        for m in _NUM_UNIT_RE.finditer(text):
            num = m.group(1).strip()
            unit = m.group(2) or ""
            if not unit:
                continue  # 裸数字（"2025"年份、"x^2"指数）不构成数字断言
            reported = float(num) * self._UNIT_MULT.get(unit, 1.0)
            out.append((m.group(0), reported))
        return out

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
        → VERIFIED；锚定源存在但偏差超容差 → CONFLICT；无锚定源 → UNVERIFIED。
        """
        findings: List[CheckFinding] = []
        candidates = self._candidate_sources(text, known_aliases)

        for raw, reported in self._extract_assertions(text):
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
                                             "来源库无匹配指标"))
                continue
            auth_val = best.normalized_value()
            if best_rel <= self.tolerance:
                findings.append(CheckFinding(
                    raw, reported, auth_val, "VERIFIED",
                    best.metric, f"来源：{best.source}（{best.year}）", best_rel))
            else:
                findings.append(CheckFinding(
                    raw, reported, auth_val, "CONFLICT",
                    best.metric,
                    f"权威值 {auth_val:g}（{best.source}）与论文 {reported:g} 冲突，"
                    f"相对差 {best_rel:.1%}，超容差 {self.tolerance:.0%}",
                    best_rel))
        return findings