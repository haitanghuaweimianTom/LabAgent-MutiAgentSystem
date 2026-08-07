# backend/tests/test_fact_correction.py
"""fact_correction 测试：CONFLICT 拦截后自动纠偏（确定性替换 + LLM 降级）。"""
import pytest

from app.services.fact_correction import correct_latex


def _finding(assertion, reported, authoritative, status="CONFLICT", metric="土地出让收入2025"):
    return {
        "assertion": assertion,
        "reported": reported,
        "authoritative": authoritative,
        "status": status,
        "metric": metric,
    }


@pytest.mark.asyncio
async def test_auto_replaces_unique_assertion_with_authoritative_value():
    # 唯一命中、单位可还原 → 确定性替换为权威值（保持原单位）
    latex = "2025年土地出让收入高达5.0万亿元，创历史新高。"
    findings = [_finding("5.0万亿元", 50000.0, 41500.0)]

    result = await correct_latex(latex, findings)

    assert "4.15万亿元" in result.latex
    assert "5.0万亿元" not in result.latex
    corr = result.corrections[0]
    assert corr["method"] == "auto"
    assert corr["metric"] == "土地出让收入2025"


@pytest.mark.asyncio
async def test_does_not_touch_verified_or_unverified():
    latex = "土地出让收入为4.15万亿元，某预测值为1.62亿元。"
    findings = [
        _finding("4.15万亿元", 41500.0, 41500.0, status="VERIFIED"),
        _finding("1.62亿元", 1.62, None, status="UNVERIFIED"),
    ]

    result = await correct_latex(latex, findings)

    assert result.latex == latex
    assert result.corrections == []


@pytest.mark.asyncio
async def test_ambiguous_multi_occurrence_goes_to_llm():
    # 同一断言文本出现两次 → 不盲改，走 LLM
    latex = "5.0万亿元。相关讨论见后文5.0万亿元。"
    findings = [_finding("5.0万亿元", 50000.0, 41500.0)]
    seen = []

    async def fake_llm(messages):
        seen.append(messages)
        return {"choices": [{"message": {"content": "4.15万亿元。相关讨论见后文5.0万亿元。"}}]}

    result = await correct_latex(latex, findings, llm_call=fake_llm)

    assert seen, "LLM 应被调用"
    assert "4.15万亿元。相关讨论见后文5.0万亿元。" in result.latex
    assert result.corrections[0]["method"] == "llm"


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_failed_not_crash():
    latex = "5.0万亿元。相关讨论见后文5.0万亿元。"
    findings = [_finding("5.0万亿元", 50000.0, 41500.0)]

    async def broken_llm(messages):
        raise RuntimeError("LLM 挂了")

    result = await correct_latex(latex, findings, llm_call=broken_llm)

    assert result.latex == latex  # 不改原文
    assert result.failed[0]["metric"] == "土地出让收入2025"


@pytest.mark.asyncio
async def test_nonzero_authoritative_required_for_auto():
    # authoritative 缺失/为零 → 不自动替换
    latex = "某指标为5.0万亿元。"
    findings = [_finding("5.0万亿元", 50000.0, None)]

    result = await correct_latex(latex, findings)

    assert result.latex == latex
    assert result.corrections == []
    assert len(result.failed) == 1