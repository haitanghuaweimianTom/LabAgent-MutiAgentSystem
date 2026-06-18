"""Tests for experiment execution services."""
import tempfile
from pathlib import Path

import pytest

from app.services.code_sandbox import CodeSandbox, SandboxConfig
from app.services.experiment_result_aggregator import ExperimentResultAggregator
from app.services.experiment_runner import ExperimentBatchResult, ExperimentRunResult, ExperimentRunner


# ---------------------------------------------------------------------------
# CodeSandbox tests
# ---------------------------------------------------------------------------


def test_scan_code_text_blocks_dangerous_patterns():
    """静态扫描应识别危险调用。"""
    code = """
import os
os.system("rm -rf /")
result = eval("1+1")
"""
    violations = CodeSandbox.scan_code_text(code)
    assert any("os.system" in v for v in violations)
    assert any("eval" in v for v in violations)


def test_scan_code_text_allows_safe_code():
    """安全代码不应触发扫描违规。"""
    code = """
import json
print(json.dumps({"accuracy": 0.95}))
"""
    violations = CodeSandbox.scan_code_text(code)
    assert violations == []


def test_run_file_rejects_missing_file():
    sandbox = CodeSandbox(config=SandboxConfig())
    result = sandbox.run_file(Path("/nonexistent/script.py"))
    assert result.success is False
    assert "不存在" in result.message or "not found" in result.message.lower()


def test_run_file_executes_simple_script():
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "hello.py"
        script.write_text('print("hello")\n', encoding="utf-8")
        sandbox = CodeSandbox(config=SandboxConfig())
        result = sandbox.run_file(script)
        assert result.success is True
        assert "hello" in result.stdout


def test_run_file_rejects_dangerous_script(tmp_path):
    script = tmp_path / "danger.py"
    script.write_text('import os\nos.system("echo hacked")\n', encoding="utf-8")
    sandbox = CodeSandbox(config=SandboxConfig())
    result = sandbox.run_file(script)
    assert result.success is False
    assert len(result.safety_violations) > 0


def test_run_command_rejects_unknown_prefix():
    sandbox = CodeSandbox(config=SandboxConfig())
    result = sandbox.run_command(["rm", "-rf", "/"])
    assert result.success is False
    assert "不在白名单" in result.message or "not allowed" in result.message.lower()


# ---------------------------------------------------------------------------
# ExperimentResultAggregator tests
# ---------------------------------------------------------------------------


def test_aggregator_builds_tables():
    batch = ExperimentBatchResult(
        success=True,
        main=ExperimentRunResult(
            name="Our Method",
            role="main",
            success=True,
            metrics={"accuracy": 0.95, "loss": 0.1},
        ),
        baselines=[
            ExperimentRunResult(
                name="Baseline A",
                role="baseline",
                success=True,
                metrics={"accuracy": 0.90, "loss": 0.15},
            ),
            ExperimentRunResult(
                name="Baseline B",
                role="baseline",
                success=True,
                metrics={"accuracy": 0.92, "loss": 0.12},
            ),
        ],
        ablations=[
            ExperimentRunResult(
                name="w/o attention",
                role="ablation",
                success=True,
                metrics={"accuracy": 0.88},
            ),
        ],
    )
    agg = ExperimentResultAggregator(primary_metric="accuracy").aggregate(batch)
    assert agg.success is True
    assert agg.best_baseline == "Baseline B"
    assert "Our Method" in agg.markdown_table
    assert "Baseline B" in agg.markdown_table
    assert "\\begin{table}" in agg.latex_table
    assert len(agg.ablation_table) == 1


def test_aggregator_summary_improvement():
    batch = ExperimentBatchResult(
        success=True,
        main=ExperimentRunResult(
            name="Our Method",
            role="main",
            success=True,
            metrics={"accuracy": 0.95},
        ),
        baselines=[
            ExperimentRunResult(
                name="Baseline A",
                role="baseline",
                success=True,
                metrics={"accuracy": 0.90},
            ),
        ],
    )
    agg = ExperimentResultAggregator(primary_metric="accuracy").aggregate(batch)
    assert "提升" in agg.summary_text


# ---------------------------------------------------------------------------
# ExperimentRunner tests
# ---------------------------------------------------------------------------


def test_runner_run_experiment_success(tmp_path):
    """运行一个真实脚本并提取指标。"""
    from app.services.experiment_runner import ExperimentScript

    script = tmp_path / "metrics.py"
    script.write_text(
        'import json\nprint(json.dumps({"accuracy": 0.93, "loss": 0.07}))\n',
        encoding="utf-8",
    )
    runner = ExperimentRunner()
    batch = runner.run_experiment(
        main_script=ExperimentScript(
            name="metrics",
            path=script,
            role="main",
        ),
        output_dir=tmp_path / "out",
    )
    assert batch.main is not None
    assert batch.main.success is True
    assert batch.main.metrics.get("accuracy") == 0.93
    assert batch.main.metrics.get("loss") == 0.07


def test_runner_extracts_metrics():
    """指标提取应解析 JSON 行。"""
    runner = ExperimentRunner()
    from app.services.code_sandbox import SandboxResult
    sandbox_result = SandboxResult(
        success=True,
        returncode=0,
        stdout='{"accuracy": 0.93}\n{"loss": 0.05}\n',
    )
    metrics = runner._extract_metrics(sandbox_result)
    assert metrics.get("accuracy") == 0.93
    assert metrics.get("loss") == 0.05


# ---------------------------------------------------------------------------
# ExperimentExecutor integration test (mocked)
# ---------------------------------------------------------------------------


def test_executor_returns_error_when_no_datasets(monkeypatch):
    """当实验计划没有数据集时，executor 应返回未执行。"""
    from app.services.experiment_executor import ExperimentExecutor

    executor = ExperimentExecutor()
    # mock dataset_manager so it has no known datasets
    monkeypatch.setattr(
        executor.dataset_manager,
        "get_dataset_info",
        lambda name: None,
    )
    monkeypatch.setattr(
        executor.dataset_manager,
        "download_and_preprocess",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("no dataset")),
    )

    result = executor.execute_experiment_plan(
        plan={"datasets": [], "baselines": [], "ablation_plan": []},
        project_name="test_proj",
        task_id="test_task",
    )
    assert result.executed is False
    assert any("未获取到任何可用数据集" in e for e in result.errors)
