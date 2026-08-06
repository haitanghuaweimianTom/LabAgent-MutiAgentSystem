"""模型合理性 LLM 判定测试（R3）。"""
import pytest
from app.services.model_reasonableness import ModelReasonableness

SAMPLE_MODEL_CODE = "# real_estate_cycle_model.py\ndef project(years, elasticity):\n    return [base * (1 + elasticity / 100) ** y for y in years]\n"


@pytest.mark.asyncio
async def test_no_llm_degrades_to_reasonable():
    checker = ModelReasonableness(llm_call=None)
    verdict = await checker.judge(
        paper_modeling_section="多因子回归，弹性-0.737。",
        model_code=SAMPLE_MODEL_CODE,
        model_output_csv="year,value\n2021,8.71\n2030,5.22",
        observed_values={"弹性": -0.74, "不良率": 1.49},
    )
    assert verdict.status == "REASONABLE"


@pytest.mark.asyncio
async def test_llm_on_concern_sets_warning_not_fail():
    async def fake_llm(messages):
        return {"choices": [{"message": {"content": '{"verdict": "ON_CONCERN", "reasons": ["未做样本外验证"]}'}}]}

    checker = ModelReasonableness(llm_call=fake_llm)
    verdict = await checker.judge(
        paper_modeling_section="模型合理性描述", model_code="",
        model_output_csv="", observed_values={},
    )
    assert verdict.status == "ON_CONCERN"
    assert verdict.warning


@pytest.mark.asyncio
async def test_llm_error_degrades_to_reasonable():
    async def boom(messages):
        raise RuntimeError("llm down")

    verdict = await ModelReasonableness(llm_call=boom).judge(
        paper_modeling_section="x", model_code="",
        model_output_csv="", observed_values={},
    )
    assert verdict.status == "REASONABLE"