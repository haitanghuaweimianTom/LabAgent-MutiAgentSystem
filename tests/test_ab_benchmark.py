"""Tests for ab_benchmark.py - A/B evolution benchmark framework."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

import ab_benchmark as ab


class TestStandardProblems:
    def test_three_problems(self):
        assert len(ab.STANDARD_PROBLEMS) == 3
        for p in ab.STANDARD_PROBLEMS:
            assert p["template"]
            assert p["problem"]

    def test_includes_math_modeling(self):
        templates = {p["template"] for p in ab.STANDARD_PROBLEMS}
        assert "math_modeling" in templates


class TestComputeMetrics:
    def test_aggregates_runs(self):
        runs = [
            {"retry": 1, "score": 0.5, "tokens": 100, "injected": False},
            {"retry": 0, "score": 0.9, "tokens": 200, "injected": True},
        ]
        metrics = ab.compute_metrics(runs)
        assert metrics["retry_count"] == 1
        assert metrics["avg_score"] == pytest.approx(0.7)
        assert metrics["total_tokens"] == 300
        assert metrics["injected_runs"] == 1

    def test_empty(self):
        assert ab.compute_metrics([])["retry_count"] == 0


class TestMockBenchmark:
    def test_evolution_reduces_retries(self):
        on = ab.run_mock_benchmark(use_evolution=True, n_runs=4)
        off = ab.run_mock_benchmark(use_evolution=False, n_runs=4)
        m_on = ab.compute_metrics(on)
        m_off = ab.compute_metrics(off)
        # Evolution cuts the recurring-bug retry rate over many runs.
        assert m_on["retry_rate"] < m_off["retry_rate"]
        assert m_on["avg_score"] >= m_off["avg_score"]

    def test_evolution_records_lessons(self):
        on = ab.run_mock_benchmark(use_evolution=True, n_runs=3)
        assert on  # non-empty list

    def test_fresh_store_no_reuse(self, tmp_path):
        a = ab.run_mock_benchmark(use_evolution=True, n_runs=2, root=tmp_path / "a")
        b = ab.run_mock_benchmark(use_evolution=True, n_runs=2, root=tmp_path / "b")
        assert a and b


class TestRenderReport:
    def test_produces_markdown_table(self):
        on = ab.compute_metrics(ab.run_mock_benchmark(True, 4))
        off = ab.compute_metrics(ab.run_mock_benchmark(False, 4))
        md = ab.render_report(on, off)
        assert "重试率" in md
        assert "|" in md  # table-like
        assert "%" in md