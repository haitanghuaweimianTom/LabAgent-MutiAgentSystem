"""backend.app.agents.demo_code_templates 的回归测试。

Phase 1D 整改后：
- 7 段 CUMCM 演示代码模板迁出到 [demo_code_templates.py](../app/agents/demo_code_templates.py)
- base.py 的 ``_select_demo_code_template`` 按关键词匹配选取
- 这些模板 **仅在 LLM Key 缺失时**（``_mock_response`` 路径）被使用
- 真实 LLM 路径走模板 system prompt，不依赖本模块
"""
import pytest

from app.agents.base import BaseAgent
from app.agents.demo_code_templates import (
    DEMO_CODE_TEMPLATES,
    DEMO_KEYWORD_TO_TEMPLATE,
    OPTICS_MULTI,
    OPTICS_DOUBLE,
    NEWSVENDOR,
    FORECAST,
    SENSITIVITY,
    TOPSIS,
    LP_FALLBACK,
)


# ---------- 1. 模板存在性 ----------

def test_all_template_ids_have_a_string():
    for tpl_id, tpl_str in DEMO_CODE_TEMPLATES.items():
        assert isinstance(tpl_str, str) and tpl_str.strip(), f"Empty template: {tpl_id}"


def test_every_template_has_python_signature():
    for tpl_id, tpl_str in DEMO_CODE_TEMPLATES.items():
        assert "import " in tpl_str, f"{tpl_id} missing import"
        assert ("def " in tpl_str) or tpl_id == "lp_fallback", f"{tpl_id} missing function def"


def test_keyword_to_template_keys_match_templates():
    for entry_id, (tpl_id, kws) in DEMO_KEYWORD_TO_TEMPLATE.items():
        assert tpl_id in DEMO_CODE_TEMPLATES, (
            f"Entry '{entry_id}' references unknown template '{tpl_id}'"
        )


def test_keyword_to_template_covers_all_domain_keys():
    """每个 keyword entry 必须有非空关键词列表。"""
    for entry_id, (tpl_id, kws) in DEMO_KEYWORD_TO_TEMPLATE.items():
        assert kws, f"Empty keywords for {entry_id}"


# ---------- 2. _select_demo_code_template 行为 ----------

# 反向索引用于断言
_STR_TO_ID = {v: k for k, v in DEMO_CODE_TEMPLATES.items()}


@pytest.mark.parametrize("text,expected_id", [
    # 多光束干涉关键词组
    ("多光束干涉", "optics_multi"),
    ("多束反射 airy 拟合", "optics_multi"),
    ("硅晶圆样品分析", "optics_multi"),
    # 双光束干涉 / 红外反射 / 薄膜
    ("双光束干涉", "optics_double"),
    ("红外反射光谱", "optics_double"),
    ("SiC 外延层厚度", "optics_double"),
    ("折射率与光程差", "optics_double"),
    # 报童 / 库存
    ("报童模型", "newsvendor"),
    ("库存订货优化", "newsvendor"),
    ("蔬菜随机需求", "newsvendor"),
    # ARIMA / 时间序列
    ("ARIMA 模型", "forecast"),
    ("时间序列预测", "forecast"),
    ("需求预测销量", "forecast"),
    # 灵敏度
    ("灵敏度分析", "sensitivity"),
    ("稳健性参数扰动", "sensitivity"),
    # TOPSIS / 综合评价
    ("TOPSIS 综合评价", "topsis"),
    ("AHP 层次分析", "topsis"),
    ("综合评价品类排序", "topsis"),
    # 兜底
    ("某通用问题", "lp_fallback"),
    ("一般优化问题", "lp_fallback"),
    ("", "lp_fallback"),
])
def test_select_demo_code_template(text, expected_id):
    got = BaseAgent._select_demo_code_template(text.lower())
    got_id = _STR_TO_ID.get(got, "?")
    assert got_id == expected_id, f"text={text!r} got={got_id} expected={expected_id}"


# ---------- 3. 优先级：多光束优先于双光束 ----------

def test_optics_multi_takes_priority_over_optics_double():
    """当一段文本同时含"多光束"和"红外"时，应优先匹配 optics_multi。"""
    text = "多光束红外反射光谱"
    got = BaseAgent._select_demo_code_template(text.lower())
    got_id = _STR_TO_ID[got]
    assert got_id == "optics_multi"


# ---------- 4. 模板字符串内容 sanity ----------

def test_optics_multi_uses_airy():
    assert "Airy" in OPTICS_MULTI or "airy" in OPTICS_MULTI


def test_newsvendor_uses_norm_ppf():
    assert "norm.ppf" in NEWSVENDOR


def test_forecast_uses_arima():
    assert "ARIMA" in FORECAST


def test_topsis_uses_normalization():
    assert "norm_matrix" in TOPSIS


def test_sensitivity_returns_dict():
    assert "results[param_name]" in SENSITIVITY


def test_lp_fallback_uses_linprog():
    assert "linprog" in LP_FALLBACK


# ---------- 5. 真实 LLM 路径不依赖本模块（架构边界保护） ----------

def test_demo_templates_not_imported_by_solvers_or_writers():
    """sanity 检查：solver_agent / writer_agent 不直接 import demo_code_templates。
    本模块只在 _mock_response（fallback 路径）使用，真实 LLM 路径完全独立。"""
    import app.agents.solver_agent as s
    import app.agents.writer_agent as w
    src_s = open(s.__file__, encoding="utf-8").read()
    src_w = open(w.__file__, encoding="utf-8").read()
    assert "demo_code_templates" not in src_s, "solver_agent unexpectedly imports demo_code_templates"
    assert "demo_code_templates" not in src_w, "writer_agent unexpectedly imports demo_code_templates"
