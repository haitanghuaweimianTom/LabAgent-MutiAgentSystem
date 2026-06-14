"""论文事实核查单元测试"""
import json
import tempfile
from pathlib import Path

import pytest

from app.services.fact_checker import get_fact_checker


@pytest.fixture
def checker():
    return get_fact_checker()


def test_extract_numbers_from_latex(checker):
    latex = r"""
    The optimal value is $123.45$ and the error rate is $0.05$.
    See \cite{smith2020} for related work.
    """
    nums = checker.extract_numbers_from_latex(latex)
    values = list(nums.values())
    assert 123.45 in values
    assert 0.05 in values
    assert 2020 not in values  # 引用年份应被过滤


def test_extract_numbers_from_solves(checker):
    solves = {
        "optimal_value": 123.45,
        "error_rate": 0.05,
        "nested": {"items": [1, 2, 3.5]},
    }
    nums = checker.extract_numbers_from_solves(solves)
    assert nums["optimal_value"] == 123.45
    assert nums["error_rate"] == 0.05
    assert nums["nested.items[2]"] == 3.5


def test_compare_detects_mismatch(checker):
    latex = {"optimal": 999.0}
    solves = {"optimal_value": 123.45}
    issues = checker.compare(latex, solves, threshold=0.05)
    assert len(issues) > 0
    assert any(i.latex_value == 999.0 for i in issues)


def test_compare_passes_when_close(checker):
    latex = {"optimal": 123.5}
    solves = {"optimal_value": 123.45}
    issues = checker.compare(latex, solves, threshold=0.05)
    assert len(issues) == 0


def test_check_end_to_end(checker):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        final_dir = tmp_path / "final"
        final_dir.mkdir()
        (final_dir / "main.tex").write_text(
            r"The optimal value is $123.45$.", encoding="utf-8"
        )
        (final_dir / "solves.json").write_text(
            json.dumps({"optimal_value": 123.45}), encoding="utf-8"
        )
        report = checker.check("task_test", tmp_path, threshold=0.05)
        assert report["passed"] is True
        assert report["latex_number_count"] >= 1
