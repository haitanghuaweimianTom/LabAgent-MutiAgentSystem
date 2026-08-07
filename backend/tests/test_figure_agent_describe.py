# backend/tests/test_figure_agent_describe.py
"""figure_agent._describe_data 测试：递归展开嵌套数值，让 LLM 看到真实预测数据。"""
import pytest

from app.agents.figure_agent import FigureAgent


def _make_agent():
    """构造一个不依赖完整 provider 的 FigureAgent 实例（仅用 _describe_data）。"""
    # FigureAgent.__init__ 需要最小参数；_describe_data 是纯函数不碰网络
    from app.agents.figure_agent import FigureAgent
    return FigureAgent(model="test", api_key="x", api_base_url="x", provider_id="test")


def test_describe_flat_dict_shows_values():
    agent = _make_agent()
    desc = agent._describe_data({"gdp_2025": 5.0, "unemployment": 4.15})
    assert "gdp_2025" in desc
    assert "5.0" in desc


def test_describe_list_of_dicts_recurses_into_numerical_results():
    """关键场景：solver 产出 sub_problem_solutions 是 list of dicts，
    其内 numerical_results 含真实预测数值。_describe_data 必须递归展开，
    让 LLM 看到实际数字，而非只列顶层 key 名。"""
    agent = _make_agent()
    data = {
        "sub_problem_solutions": [
            {
                "numerical_results": {
                    "GDP_growth_2025": 4.66,
                    "Unemployment_2025": 4.15,
                },
                "sub_problem_name": "情景构建",
            },
        ]
    }
    desc = agent._describe_data(data)
    # 必须能看到真实数值，不能只看到 "list of 1 dicts, keys: numerical_results"
    assert "GDP_growth_2025" in desc
    assert "4.66" in desc
    assert "Unemployment_2025" in desc
    assert "4.15" in desc


def test_describe_nested_dict_recurses_one_level():
    agent = _make_agent()
    data = {"forecast": {"2025": 4.66, "2026": 4.5}}
    desc = agent._describe_data(data)
    assert "2025" in desc
    assert "4.66" in desc
