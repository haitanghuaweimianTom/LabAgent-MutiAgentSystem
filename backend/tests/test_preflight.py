"""Preflight 决策服务单元测试"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.preflight import (
    PreflightDecisionService,
    PreflightReport,
    DataAdequacy,
)


@pytest.fixture
def preflight_service():
    with patch("app.services.preflight._PreflightLLMClient") as MockClient:
        svc = PreflightDecisionService(api_key="test", api_base_url="http://test", model="test-model")
        svc._client = MockClient()
        yield svc


@pytest.mark.asyncio
async def test_decide_with_data(preflight_service):
    preflight_service._schema_extractor.extract = MagicMock(return_value={
        "file_name": "data.csv",
        "row_count": 100,
        "column_count": 5,
        "columns": [{"name": "x", "dtype": "int64"}],
    })
    preflight_service._list_template_ids = MagicMock(return_value=["math_modeling", "neurips_2024"])

    raw = {
        "problem_type": "优化",
        "has_data_confidence": 0.9,
        "data_subjects": ["工程测量"],
        "recommended_template": "neurips_2024",
        "recommended_workflow": "standard",
        "recommended_mode": "batch",
        "data_adequacy": "sufficient",
        "llm_should_collect": False,
        "collection_plan": "",
    }
    preflight_service._call_llm_for_decision = AsyncMock(return_value=raw)

    report = await preflight_service.decide(
        problem_text="优化某供应链成本",
        data_files=["/tmp/data.csv"],
    )

    assert isinstance(report, PreflightReport)
    assert report.data_adequacy == DataAdequacy.SUFFICIENT
    assert report.recommended_template == "neurips_2024"
    assert report.has_data_confidence == 0.9


@pytest.mark.asyncio
async def test_decide_without_data_triggers_collection(preflight_service):
    preflight_service._schema_extractor.extract = MagicMock(return_value=None)
    preflight_service._list_template_ids = MagicMock(return_values=["math_modeling"])
    preflight_service._call_llm_for_decision = AsyncMock(return_value={
        "problem_type": "预测",
        "has_data_confidence": 0.0,
        "data_subjects": [],
        "recommended_template": "math_modeling",
        "recommended_workflow": "standard",
        "recommended_mode": "batch",
        "data_adequacy": "missing",
        "llm_should_collect": True,
        "collection_plan": "搜索 Kaggle 时序数据集",
    })

    report = await preflight_service.decide(
        problem_text="预测未来一周气温",
        data_files=[],
    )

    assert report.data_adequacy == DataAdequacy.MISSING
    assert report.llm_should_collect is True
    assert "Kaggle" in report.collection_plan or "搜索" in report.collection_plan


@pytest.mark.asyncio
async def test_data_mismatch_warning(preflight_service):
    preflight_service._schema_extractor.extract = MagicMock(return_value={
        "file_name": "finance.csv", "row_count": 10, "column_count": 3, "columns": []
    })
    preflight_service._list_template_ids = MagicMock(return_value=["math_modeling"])
    preflight_service._call_llm_for_decision = AsyncMock(return_value={
        "problem_type": "物理",
        "has_data_confidence": 0.3,
        "data_subjects": ["金融时序"],
        "recommended_template": "math_modeling",
        "recommended_workflow": "standard",
        "recommended_mode": "batch",
        "data_adequacy": "insufficient",
        "llm_should_collect": False,
        "collection_plan": "",
    })

    report = await preflight_service.decide(
        problem_text="计算双缝干涉条纹间距",
        data_files=["/tmp/finance.csv"],
    )

    assert report.data_mismatch_warning is not None
