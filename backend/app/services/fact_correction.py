# backend/app/services/fact_correction.py
"""事实核查拦截后的自动纠偏服务。

当外部核查检测到 CONFLICT（论文数字与权威来源冲突）时，本服务把论文
修正为权威值，形成"拦截 → 修正 → 重验"闭环，而不是只打回人工：

- 确定性替换：断言文本唯一出现、权威值非零 → 直接替换为权威值（保持原单位）。
- LLM 纠偏：断言多次出现（无法唯一定位）或单位无法还原时，把上下文交给
  LLM 重写；LLM 缺失/失败 → 标记 failed，绝不崩溃、绝不盲改。

本服务只消费外部核查产出的 findings（dict 形态，兼容 orchestrator 的
c.__dict__ 序列化），不自行产生权威数字。权威值来自 FactSourceRegistry。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .external_fact_checker import _NUM_UNIT_RE, ExternalFactChecker

_UNIT_MULT = ExternalFactChecker._UNIT_MULT


@dataclass
class CorrectionResult:
    latex: str
    corrections: List[Dict[str, Any]] = field(default_factory=list)
    failed: List[Dict[str, Any]] = field(default_factory=list)


def _unit_of(assertion: str) -> str:
    """从断言文本尾部还原单位（与 _NUM_UNIT_RE 提取方式一致）。"""
    m = re.search(r"(万亿元|亿元|亿平方米|万平方米|万套|万亿|亿|万元|pp|%)$", assertion)
    return m.group(1) if m else ""


def _authoritative_in_unit(auth_value: float, unit: str) -> Optional[str]:
    """把亿元口径权威值还原为断言原单位的文本表示；无法表示 → None。"""
    if unit not in _UNIT_MULT:
        return None
    mult = _UNIT_MULT[unit]
    if mult <= 0:
        return None
    raw = auth_value / mult
    text = f"{raw:g}"
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text}{unit}"


def _needs_llm(latex: str, assertion: str, authoritative: float) -> bool:
    """确定性替换不可用时才需要 LLM：多次出现或单位无法还原。"""
    unit = _unit_of(assertion)
    new_assertion = _authoritative_in_unit(authoritative, unit)
    if new_assertion is None:
        return True
    if latex.count(assertion) != 1:
        return True
    return False


async def correct_latex(
    latex: str,
    findings: List[Dict[str, Any]],
    llm_call: Optional[Callable[[List[dict]], Any]] = None,
) -> CorrectionResult:
    """对 CONFLICT 断言做纠偏。返回修正后文本 + 修正记录 + 失败清单。"""
    result = CorrectionResult(latex=latex)
    conflicts = [f for f in findings if f.get("status") == "CONFLICT"]

    pending: List[Dict[str, Any]] = []
    for finding in conflicts:
        assertion = str(finding.get("assertion", ""))
        authoritative = finding.get("authoritative")
        if not assertion:
            continue
        if authoritative is None or authoritative == 0:
            result.failed.append(finding)
            continue

        unit = _unit_of(assertion)
        new_assertion = _authoritative_in_unit(authoritative, unit)

        if new_assertion is not None and latex.count(assertion) == 1:
            new_latex = latex.replace(assertion, new_assertion)
            if new_latex != latex:
                latex = new_latex
                result.corrections.append({
                    "assertion": assertion,
                    "reported": finding.get("reported"),
                    "authoritative": authoritative,
                    "metric": finding.get("metric"),
                    "method": "auto",
                    "replacement": new_assertion,
                })
                continue

        pending.append(finding)

    for finding in pending:
        assertion = str(finding.get("assertion", ""))
        authoritative = finding.get("authoritative")
        try:
            if llm_call is None:
                raise RuntimeError("no llm_call")
            unit = _unit_of(assertion)
            new_assertion = _authoritative_in_unit(authoritative, unit)
            target = new_assertion or f"权威值 {authoritative:g}（亿元口径）"
            prompt = [
                {"role": "system", "content": (
                    "你是科研论文事实修正助手。论文中有一段数字与权威来源冲突。"
                    "请仅把冲突数字替换为给出的权威值，保持句子其余语义、语气、"
                    "LaTeX 结构与单位完全不变。直接输出修改后的整段文本，不要解释。"
                )},
                {"role": "user", "content": (
                    f"权威指标：{finding.get('metric')}\n"
                    f"论文断言「{assertion}」应修正为「{target}」。\n"
                    f"原文段落：\n{latex}"
                )},
            ]
            response = await llm_call(prompt)
            content = ""
            if isinstance(response, dict):
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            elif isinstance(response, str):
                content = response
            if not content or content.strip() == latex:
                raise RuntimeError("empty llm response")
            latex = content
            result.corrections.append({
                "assertion": assertion,
                "reported": finding.get("reported"),
                "authoritative": authoritative,
                "metric": finding.get("metric"),
                "method": "llm",
                "replacement": target,
            })
        except Exception as exc:
            result.failed.append({**finding, "reason": f"LLM 纠偏失败：{exc}"})

    result.latex = latex
    return result
