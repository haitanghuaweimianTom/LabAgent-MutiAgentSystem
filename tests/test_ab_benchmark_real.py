"""Tests for ab_benchmark --real instrumentation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

import ab_benchmark as ab


class TestMetricsFromResult:
    def test_score_and_tokens(self):
        result = {
            "total_tokens_used": 5000,
            "peer_review": {"overall_score": 4.0, "recommendation": "accept"},
            "folder": "/tmp/x",
        }
        m = ab.metrics_from_result(result, injected=True)
        assert m["score"] == pytest.approx(0.8)
        assert m["tokens"] == 5000
        assert m["retry"] == 0
        assert m["injected"] is True

    def test_revise_counts_as_retry(self):
        result = {
            "total_tokens_used": 1000,
            "peer_review": {"overall_score": 2.5, "recommendation": "revise"},
        }
        m = ab.metrics_from_result(result, injected=False)
        assert m["retry"] == 1

    def test_missing_review_defaults(self):
        result = {"total_tokens_used": 0}
        m = ab.metrics_from_result(result, injected=False)
        assert m["score"] == 0.0
        assert m["retry"] == 1  # no accept verdict => treated as needing work


class TestRunRealAb:
    def test_controls_and_isolates_evolution(self, tmp_path):
        calls = []

        async def fake_runner(problem, template, enable_evolution, output_dir, evo_dir):
            calls.append({
                "problem": problem,
                "template": template,
                "on": enable_evolution,
                "evo_dir": str(evo_dir),
            })
            result = {
                "total_tokens_used": 3000,
                "peer_review": {"overall_score": 4.0, "recommendation": "accept"},
            }
            return result, False

        on_metrics, off_metrics, report = ab.run_real_ab(
            pipeline_runner=fake_runner,
            output_root=tmp_path,
            n_evolution=True,
        )
        # 3 problems x 2 arms = 6 runs
        assert len(calls) == 6
        on_calls = [c for c in calls if c["on"]]
        off_calls = [c for c in calls if not c["on"]]
        assert len(on_calls) == 3 and len(off_calls) == 3
        # evolution dirs differ between arms
        assert {c["evo_dir"] for c in on_calls} != {c["evo_dir"] for c in off_calls}

    def test_report_rendered(self, tmp_path):
        async def fake_runner(problem, template, enable_evolution, output_dir, evo):
            result = {"total_tokens_used": 1, "peer_review": {"overall_score": 3.0, "recommendation": "accept"}}
            return result, False

        on_metrics, off_metrics, report = ab.run_real_ab(fake_runner, output_root=tmp_path)
        assert "重试率" in report
        assert "ab" in on_metrics.keys() or "n_runs" in on_metrics