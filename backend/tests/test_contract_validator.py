"""Agent 输出契约校验单元测试"""
import pytest

from app.services.contract_validator import get_contract_validator


@pytest.fixture
def validator():
    return get_contract_validator()


def test_analyst_valid(validator):
    output = {
        "sub_problems": [{"description": "子问题1"}],
        "problem_type": "优化",
        "difficulty": "中等",
    }
    result = validator.validate("analyzer_agent", output)
    assert result["valid"] is True
    assert result["agent"] == "analyzer_agent"


def test_analyst_missing_sub_problems(validator):
    output = {"problem_type": "优化"}
    result = validator.validate("analyzer_agent", output)
    assert result["valid"] is False
    assert any("sub_problems" in e for e in result["errors"])


def test_solver_warning_when_no_numerical(validator):
    output = {"execution_success": True, "numerical_results": {}}
    result = validator.validate("solver_agent", output)
    assert result["valid"] is True
    assert any("numerical_results" in w for w in result["warnings"])


def test_unknown_agent_skipped(validator):
    result = validator.validate("unknown_agent", {"foo": 1})
    assert result["valid"] is True
    assert any("未定义" in w for w in result["warnings"])
