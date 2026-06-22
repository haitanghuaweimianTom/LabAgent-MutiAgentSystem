"""ConsistencyChecker 测试。

跨章节一致性验证器：在 writer 完成后跑一次，检查：
1. 术语一致性（同一概念不混用不同术语）
2. 模型名一致性（paper_memory 登记的名字在 LaTeX 实际出现）
3. 结论一致性（摘要与结论的数字呼应）
4. 引用一致性（bib 条目不被孤立）
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.consistency_checker import (
    ConsistencyChecker,
    get_consistency_checker,
)


# ==================== 1. 术语一致性 ====================

def test_terminology_inconsistent_detected():
    """同一论文里混用"神经网络"和"深度学习模型"应被检测。"""
    checker = ConsistencyChecker()
    latex = (
        r"\section{方法}本文使用神经网络进行分类。"
        r"\section{结果}深度学习模型效果显著。"
    )
    report = checker.check("t1", latex_code=latex)
    assert report.stats["terminology_issues"] >= 1
    # 中等严重度——不阻塞 passed
    assert any(i.severity == "medium" for i in report.issues)


def test_terminology_consistent_pass():
    """全文统一使用一个术语应通过。"""
    checker = ConsistencyChecker()
    latex = r"\section{方法}本文使用神经网络。\section{结果}神经网络效果显著。"
    report = checker.check("t1", latex_code=latex)
    assert report.stats["terminology_issues"] == 0


# ==================== 2. 模型名一致性 ====================

def test_model_name_unused_warns():
    """paper_memory 登记的模型名在 LaTeX 找不到，应警告。"""
    checker = ConsistencyChecker()
    latex = r"\section{方法}本文使用 CNN 进行分类。"
    pm = {"model_names": ["CNN", "LSTM"], "algorithms": ["Adam"], "datasets": []}
    report = checker.check("t1", latex_code=latex, paper_memory=pm)
    # LSTM 未出现 → 应该警告
    model_issues = [i for i in report.issues if i.category == "model_name"]
    assert any("LSTM" in i.message for i in model_issues)


# ==================== 3. 结论一致性 ====================

def test_conclusion_missing_number_detected():
    """摘要提到 42.0 但结论没呼应该数字。"""
    checker = ConsistencyChecker()
    chapters = [
        {"id": "abstract", "title": "摘要", "summary": "本文最优解为 42.0，误差 0.05。"},
        {"id": "conclusion", "title": "结论", "summary": "本文取得一定成果。"},  # 没呼应该数字
    ]
    report = checker.check("t1", latex_code="", chapter_summaries=chapters)
    concl_issues = [i for i in report.issues if i.category == "conclusion"]
    assert len(concl_issues) >= 1
    assert any("42" in i.message for i in concl_issues)


def test_conclusion_consistent_pass():
    """摘要和结论都提到 42.0，应通过。"""
    checker = ConsistencyChecker()
    chapters = [
        {"id": "abstract", "title": "摘要", "summary": "最优解为 42.0"},
        {"id": "conclusion", "title": "结论", "summary": "本文最优解为 42.0，验证了方法有效性。"},
    ]
    report = checker.check("t1", latex_code="", chapter_summaries=chapters)
    concl_issues = [i for i in report.issues if i.category == "conclusion"]
    assert len(concl_issues) == 0


# ==================== 4. 引用一致性 ====================

def test_orphan_bib_detected():
    """bib 中的孤立条目应被检测。"""
    checker = ConsistencyChecker()
    latex = r"\section{方法}本文方法基于早期工作\cite{ref_used}。"
    bib = [
        {"key": "ref_used", "title": "A"},
        {"key": "ref_orphan", "title": "B"},  # 没被引用
    ]
    report = checker.check("t1", latex_code=latex, bib_entries=bib)
    orphan_issues = [i for i in report.issues if i.category == "citation"]
    assert any("ref_orphan" in i.message for i in orphan_issues)
    assert not any("ref_used" in i.message for i in orphan_issues)


def test_all_bib_used_pass():
    """所有 bib 都被引用，应通过。"""
    checker = ConsistencyChecker()
    latex = r"\section{方法}见\cite{ref_a}和\cite{ref_b}。"
    bib = [{"key": "ref_a", "title": "A"}, {"key": "ref_b", "title": "B"}]
    report = checker.check("t1", latex_code=latex, bib_entries=bib)
    cite_issues = [i for i in report.issues if i.category == "citation"]
    assert len(cite_issues) == 0


# ==================== 5. 数值一致性 ====================

def test_solver_number_not_in_latex_warns():
    """solver 输出 42.05 但 LaTeX 没出现该数字。"""
    checker = ConsistencyChecker()
    latex = r"\section{结果}实验取得成功。"  # 没数字
    solver = {"sub_problem_solutions": [{"numerical_results": {"optimal": 42.05}}]}
    report = checker.check("t1", latex_code=latex, solver_numerical_results=solver)
    num_issues = [i for i in report.issues if i.category == "number"]
    assert any("42" in i.message for i in num_issues)


# ==================== 6. 综合 ====================

def test_get_checker_singleton():
    """get_consistency_checker 应返回单例。"""
    c1 = get_consistency_checker()
    c2 = get_consistency_checker()
    assert c1 is c2


def test_empty_input():
    """空输入不崩溃。"""
    checker = ConsistencyChecker()
    report = checker.check("t_empty")
    assert report.issue_count == 0
    assert report.passed


def test_report_to_dict():
    """to_dict 应返回可序列化的字典。"""
    checker = ConsistencyChecker()
    report = checker.check("t", latex_code=r"\section{X}")
    d = report.to_dict()
    assert "task_id" in d
    assert "issues" in d
    assert "stats" in d
    assert isinstance(d["issues"], list)


def test_real_ccf_a_style_latex():
    """类 CCF-A 论文风格 LaTeX：术语一致 + 引用完整 + 数值呼应。"""
    checker = ConsistencyChecker()
    latex = r"""
\section{Abstract}
We propose a neural network for image classification.
Our method achieves 94.5% accuracy on CIFAR-10.

\section{Method}
Our neural network consists of three convolutional layers.

\section{Experiments}
We compare with ResNet \cite{ref_resnet} and VGG \cite{ref_vgg}.
Our neural network achieves 94.5% accuracy, outperforming baselines.

\section{Conclusion}
The proposed neural network achieves 94.5% accuracy.
"""
    bib = [
        {"key": "ref_resnet", "title": "Deep Residual Learning"},
        {"key": "ref_vgg", "title": "Very Deep Convolutional Networks"},
    ]
    pm = {"model_names": ["neural network"], "algorithms": [], "datasets": []}
    report = checker.check("t_real", latex_code=latex, paper_memory=pm, bib_entries=bib)
    # 没有术语不一致（全文统一用 "neural network"）
    # 没有模型名遗漏（neural network 出现在 latex）
    # 没有引用孤立（ref_resnet 和 ref_vgg 都被引用）
    # 没有数值遗漏（94.5 出现在多处）
    assert report.stats["terminology_issues"] == 0
    assert report.stats["model_name_issues"] == 0
    assert report.stats["citation_issues"] == 0
