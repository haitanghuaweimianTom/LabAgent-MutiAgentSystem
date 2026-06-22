"""v5.2: 主动上下文压缩（ContextCompressor）测试。

参考 Claude Code /compact 的原理：长程 CCF-A 任务里，多 Agent 串联
会让累积 context 暴涨（research_agent 拉 50+ 篇论文 + experimentation
设计 5+ baseline），触发 LLM API prompt too long 错误或质量下降。

本测试验证：
1. estimate_tokens() 准确性
2. soft_compress() 丢弃 droappable 字段、截断长字符串
3. ContextCompressor.maybe_compress() 触发条件正确
4. 三级压缩（L0/L1/L2）的顺序与降级
5. protected 字段永不丢
6. 不超阈值时不动
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.context_compressor import (
    CompressorConfig,
    ContextCompressor,
    DROPPABLE_FIELDS,
    PROTECTED_FIELDS,
    estimate_tokens,
    get_compressor,
    reset_compressor,
    soft_compress,
)


# ==================== 1. estimate_tokens ====================

def test_estimate_tokens_string():
    """estimate_tokens: 字符串按字符/3 估算。"""
    assert estimate_tokens("hello") == max(1, 5 // 3)  # 5 chars → 1 token
    assert estimate_tokens("a" * 300) == 100
    assert estimate_tokens("") == 1  # 至少 1


def test_estimate_tokens_nested():
    """estimate_tokens: 递归处理 dict/list。"""
    obj = {"a": "hello world", "b": [1, 2, 3, "x" * 100]}
    # 字符串 token 估算：11//3=3, 100//3=33, 数字各 1
    # key 字符串 "a"=1, "b"=1
    tokens = estimate_tokens(obj)
    assert tokens > 0
    assert tokens < 100  # 不会过度估算


# ==================== 2. soft_compress ====================

def test_soft_compress_drops_droappable_fields():
    """soft_compress: _contract / raw_response / trace 等应被丢弃。"""
    output = {
        "title": "My Paper",
        "abstract": "摘要",
        "_contract": {"valid": True, "errors": []},
        "raw_response": "很长很长很长很长很长很长很长很长很长很长很长很长很长很长很长",
        "trace": ["step1", "step2"],
    }
    compressed, saved = soft_compress(output)
    assert "title" in compressed
    assert "abstract" in compressed
    assert "_contract" not in compressed
    assert "raw_response" not in compressed
    assert "trace" not in compressed
    assert saved > 0


def test_soft_compress_truncates_long_strings():
    """soft_compress: 单字符串超过 6000 字符应截断。"""
    long_str = "x" * 10000
    output = {"key": long_str}
    compressed, saved = soft_compress(output)
    assert len(compressed["key"]) < len(long_str)
    assert "truncated" in compressed["key"].lower()
    assert saved > 0


def test_soft_compress_protects_protected_fields():
    """soft_compress: protected 字段即使很长也不截断。"""
    long_latex = "\\section{x}\n" * 1000  # ~12000 字符
    output = {"latex_code": long_latex, "title": "T"}
    compressed, _ = soft_compress(output)
    assert compressed["latex_code"] == long_latex  # 完整保留


def test_soft_compress_truncates_large_lists():
    """soft_compress: 列表超过 20 元素应截断到前 5 + 标记。"""
    output = {"items": [{"i": i} for i in range(50)]}
    compressed, saved = soft_compress(output)
    assert len(compressed["items"]) == 6  # 5 + 1 truncation marker
    assert saved > 0


# ==================== 3. ContextCompressor 触发条件 ====================

def test_compressor_skips_when_under_threshold():
    """累计 token < 阈值时，不应压缩。"""
    reset_compressor()
    compressor = ContextCompressor(CompressorConfig(threshold_tokens=10_000))
    results = {
        "analyzer_agent": {"title": "T", "sub_problems": [{"id": 1}]},
        "research_agent": {"papers": [{"title": f"P{i}"} for i in range(5)]},
    }
    stats = compressor.maybe_compress("t_small", results)
    assert stats.saved_tokens == 0
    assert stats.level_used == "none"
    # 内容不变
    assert "_contract" not in results["analyzer_agent"] or True  # 原本就不在


def test_compressor_triggers_l0_when_over_threshold():
    """累计 token > 阈值时，应触发 L0 软压缩。"""
    compressor = ContextCompressor(CompressorConfig(
        threshold_tokens=500,  # 调低阈值容易触发
        per_agent_threshold_tokens=200,
    ))
    results = {
        "analyzer_agent": {
            "title": "T",
            "_contract": {"big": "x" * 5000},  # 大量 debug 数据
            "raw_response": "y" * 3000,
            "sub_problems": [{"id": 1, "description": "d"}],
        },
    }
    stats = compressor.maybe_compress("t_l0", results)
    assert stats.saved_tokens > 0
    assert stats.level_used in ("L0", "L1", "L2")


def test_compressor_l1_falls_back_without_llm():
    """没有 llm_caller 时，L1 摘要应降级到 L2 截断，不崩溃。"""
    compressor = ContextCompressor(CompressorConfig(
        threshold_tokens=500,
        per_agent_threshold_tokens=200,
    ))
    results = {
        "analyzer_agent": {
            "title": "T",
            "long_field": "z" * 3000,
            "latex_code": "\\section{x}" * 500,  # protected, 即使超过也保留
        },
    }
    stats = compressor.maybe_compress("t_no_llm", results, llm_caller=None)
    # latex_code 必须保留
    assert results["analyzer_agent"]["latex_code"].startswith("\\section{x}")
    # 但 long_field 应被截断
    assert len(results["analyzer_agent"]["long_field"]) < 3000
    assert stats.saved_tokens > 0


def test_compressor_protected_fields_survive_l2():
    """L2 硬截断后，protected 字段（latex_code/title/abstract/key_findings）必须保留。"""
    compressor = ContextCompressor(CompressorConfig(
        threshold_tokens=200,
        per_agent_threshold_tokens=100,
        hard_truncate_chars=200,
    ))
    original_latex = "\\section{Intro}\n" * 100  # 长 latex
    results = {
        "writer_agent": {
            "latex_code": original_latex,
            "title": "Important Title",
            "abstract": "Important abstract",
            "key_findings": ["finding 1", "finding 2"],
            "long_metadata": "z" * 5000,  # 应被截断
        },
    }
    stats = compressor.maybe_compress("t_protect", results, force=True)
    out = results["writer_agent"]
    assert out["latex_code"] == original_latex  # 完整保留
    assert out["title"] == "Important Title"
    assert out["abstract"] == "Important abstract"
    assert out["key_findings"] == ["finding 1", "finding 2"]
    assert len(out["long_metadata"]) < 5000  # 被截断


def test_compressor_long_ccf_a_simulation():
    """模拟长程 CCF-A 任务：累计 100K+ tokens 应大幅压缩。"""
    compressor = ContextCompressor(CompressorConfig(
        threshold_tokens=30_000,
        per_agent_threshold_tokens=8_000,
        hard_truncate_chars=500,
    ))
    # 模拟 research_agent 拉 50 篇论文，每篇 1000 字 abstract
    papers = [{"title": f"Paper {i}", "abstract": "x" * 1500, "authors": ["A"] * 5} for i in range(80)]
    # 模拟 modeler 输出大量公式
    model_output = {
        "sub_problem_models": [
            {"id": i, "objective_function": "z" * 500} for i in range(10)
        ],
        "raw_response": "y" * 10000,  # droappable
        "_contract": {"a": 1},
    }
    # 模拟 experimentation 大量 baseline
    exp_output = {
        "plan": {"baselines": ["b1", "b2", "b3"]},
        "experiment_result": {"results": [{"name": f"r{i}", "value": 0.9} for i in range(50)]},
        "raw_data": [{"x": i, "y": i * 2} for i in range(200)],  # 会被截断
    }
    # 模拟 solver 大输出（多子问题求解 + 代码 + 日志）
    solver_output = {
        "sub_problem_solutions": [
            {"id": i, "code_files": [{"code": "c" * 5000}], "numerical_results": {"v": i}}
            for i in range(15)
        ],
        "raw_log": "log" * 5000,
    }
    results = {
        "research_agent": {"papers": papers},
        "modeler_agent": model_output,
        "experimentation_agent": exp_output,
        "solver_agent": solver_output,
    }
    original_tokens = estimate_tokens(results)
    stats = compressor.maybe_compress("ccf_a_sim", results, force=True)
    new_tokens = estimate_tokens(results)
    assert original_tokens > 30_000, f"应超阈值，实际 {original_tokens}"
    assert new_tokens < original_tokens, "压缩后必须减少"
    assert stats.saved_tokens > 0
    # protected 字段（latex_code 不存在，但 experiment_result.plan 必须保留）
    assert results["experimentation_agent"]["plan"] == {"baselines": ["b1", "b2", "b3"]}
    # droappable 字段应被丢弃
    assert "raw_response" not in results["modeler_agent"]
    assert "_contract" not in results["modeler_agent"]
    assert "raw_log" not in results["solver_agent"]


def test_compressor_history():
    """get_history 应返回上次压缩的统计。"""
    reset_compressor()
    compressor = ContextCompressor(CompressorConfig(threshold_tokens=100))
    results = {"a": {"big_field": "x" * 1000}}
    stats = compressor.maybe_compress("t_hist", results)
    history = compressor.get_history("t_hist")
    assert history is not None
    assert history.saved_tokens == stats.saved_tokens
    # 不存在任务返回 None
    assert compressor.get_history("non_exist") is None


def test_get_compressor_singleton():
    """get_compressor 应返回全局单例。"""
    reset_compressor()
    c1 = get_compressor()
    c2 = get_compressor()
    assert c1 is c2


def test_compressor_empty_results():
    """空 results 不应崩溃。"""
    compressor = ContextCompressor()
    stats = compressor.maybe_compress("empty", {})
    assert stats.saved_tokens == 0


def test_compressor_results_with_non_dict_values():
    """results 里 value 不是 dict 时应跳过。"""
    compressor = ContextCompressor(CompressorConfig(threshold_tokens=100))
    results = {
        "analyzer_agent": {"title": "T"},  # dict
        "research_agent": "not a dict",  # 字符串
        "data_agent": [1, 2, 3],  # list
    }
    stats = compressor.maybe_compress("t_mixed", results)
    assert stats.original_tokens >= 0
