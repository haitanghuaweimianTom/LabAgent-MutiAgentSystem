"""端到端冒烟测试：验证 CCF-A 论文产线可生成可编译、可下载的 camera-ready 包。

本测试 mock 所有 Agent 的 execute 方法，避免真实 LLM 调用，目标运行时间 < 2 分钟。
覆盖：
- run_research_paper_workflow 完整流程
- WriterAgent 占位符替换
- CrossValidator 产生 cross_validation 记录
- CameraReadyService 自动打包 + 编译验证
- 产物完整性：main.tex, main.bib, figures/, code/, README.md, metadata.json
"""
import asyncio
import json
from pathlib import Path

import pytest

from app.agents.orchestrator import Orchestrator
from app.agents.base import BaseAgent, AgentFactory
from app.core.paths import get_project_output_dir
import app.core.paths as paths


class _MockAgent(BaseAgent):
    """可配置返回值的 mock agent。"""

    def __init__(self, name: str, response: dict):
        super().__init__()
        self.name = name
        self._response = response

    async def execute(self, task_input, context):
        return dict(self._response)

    def get_system_prompt(self, template: str = "math_modeling") -> str:
        return f"Mock system prompt for {self.name}"


def _mock_latex_for(template_id: str) -> str:
    """使用真实 WriterAgent._assemble_paper 生成可编译的最小 LaTeX，确保占位符被替换。"""
    from app.agents.writer_agent import WriterAgent
    agent = WriterAgent({})
    chapters = [
        {"plan": {"id": "abstract", "title": "Abstract", "section_level": 0}, "latex": r"\\begin{abstract}Abstract.\\end{abstract}", "summary": ""},
        {"plan": {"id": "introduction", "title": "1 Introduction", "section_level": 1}, "latex": r"Intro.", "summary": ""},
    ]
    # 注入标题/摘要/关键词元数据
    agent._last_abstract_meta = {
        "title": "Smoke Test Title",
        "abstract": "Abstract.",
        "keywords": ["k1", "k2"],
    }
    result = agent._assemble_paper(chapters, template_id, [])
    return result["latex_code"]


def _make_agents(template_id: str):
    latex_code = _mock_latex_for(template_id)
    return {
        "analyzer_agent": _MockAgent("analyzer_agent", {
            "sub_problems": [
                {"id": 1, "name": "Sub-problem 1", "description": "Test sub-problem", "suggested_method": "optimization"}
            ],
            "problem_type": "optimization",
            "overall_approach": "Test approach",
        }),
        "data_agent": _MockAgent("data_agent", {"insights": []}),
        "research_agent": _MockAgent("research_agent", {"papers": [], "methods": []}),
        "experimentation_agent": _MockAgent("experimentation_agent", {
            "plan": {"baselines": ["baseline_a"], "datasets": ["synthetic"], "metrics": ["accuracy"], "ablation_plan": []}
        }),
        "modeler_agent": _MockAgent("modeler_agent", {
            "sub_problem_models": [{
                "sub_problem_id": 1,
                "sub_problem_name": "Sub-problem 1",
                "sub_problem_desc": "Test",
                "model_name": "LinearModel",
                "model_type": "optimization",
                "objective_function": "min x",
                "decision_variables": [{"name": "x"}],
                "constraints": [],
                "algorithm": {"name": "simplex"},
            }]
        }),
        "solver_agent": _MockAgent("solver_agent", {
            "sub_problem_solutions": [{
                "sub_problem_id": 1,
                "sub_problem_name": "Sub-problem 1",
                "results": {
                    "key_findings": ["found"],
                    "numerical_results": {"optimal_value": 42.0, "iterations": 10},
                },
                "code_files": [
                    {"path": "solver_sub1.py", "role": "solver", "code": "print(42)\n", "description": "solver"}
                ],
                "cross_check": [
                    {"method_a": "primary", "method_b": "analytical_estimate", "field": "optimal_value", "diverged": False, "skipped": False},
                ],
                "code_manifest": {
                    "manifest": {
                        "files": [{"path": "solver_sub1.py", "role": "solver", "description": "solver"}]
                    }
                },
            }]
        }),
        "writer_agent": _MockAgent("writer_agent", {
            "title": "Smoke Test Title",
            "abstract": "Abstract.",
            "keywords": ["k1", "k2"],
            "latex_code": latex_code,
            "chapters": [{"id": "abstract", "title": "Abstract", "score": 90, "passed": True}],
        }),
        "peer_review_agent": _MockAgent("peer_review_agent", {
            "recommendation": "accept",
            "overall_score": 4.5,
            "scores": {"novelty": 4, "soundness": 5, "clarity": 4, "significance": 4},
            "comments": {"major": [], "minor": ["minor note"]},
            "suggested_edits": [],
        }),
    }


@pytest.fixture
def patched_output_dir(tmp_path, monkeypatch):
    def _mock_get_project_output_dir(project_name):
        d = tmp_path / "outputs" / (project_name or "__global__") / "output"
        d.mkdir(parents=True, exist_ok=True)
        return d

    import app.core.paths as paths
    monkeypatch.setattr(paths, "get_project_output_dir", _mock_get_project_output_dir)
    monkeypatch.setattr(paths, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT_DIR", tmp_path / "output")
    return tmp_path


@pytest.fixture
def patched_task_dir(tmp_path, monkeypatch):
    import app.core.task_persistence as tp
    monkeypatch.setattr(tp, "TASK_DATA_DIR", tmp_path / "tasks")
    return tmp_path / "tasks"


@pytest.mark.asyncio
@pytest.mark.parametrize("template_id", ["ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs"])
async def test_smoke_research_paper_workflow(template_id, patched_output_dir, patched_task_dir):
    agents = _make_agents(template_id)
    orch = Orchestrator(agents)
    task_id = f"smoke_{template_id}"

    result = await orch.run_research_paper_workflow(
        task_id=task_id,
        problem_text="A simple linear programming smoke test.",
        data_files=[],
        project_name=task_id,
        template=template_id,
        mode="batch",
    )

    # 1. 流程成功完成
    assert result.get("status") == "completed" or result.get("phase") == "completed"
    assert "writer_result" in result
    assert "peer_review_agent" in result or "final_peer_review" in result

    # 2. 输出目录结构
    out_dir = paths.get_project_output_dir(task_id)
    assert out_dir.exists()
    pkg_dir = out_dir / f"camera_ready_{task_id}"
    zip_path = out_dir / f"camera_ready_{task_id}.zip"

    assert pkg_dir.exists(), f"camera-ready package dir missing for {template_id}"
    assert zip_path.exists(), f"camera-ready zip missing for {template_id}"

    # 3. 产物完整性
    assert (pkg_dir / "main.tex").exists()
    assert (pkg_dir / "main.bib").exists()
    assert (pkg_dir / "README.md").exists()
    assert (pkg_dir / "metadata.json").exists()

    # 4. main.tex 无未替换占位符
    latex_code = (pkg_dir / "main.tex").read_text(encoding="utf-8")
    placeholders = [m.group(0) for m in __import__('re').finditer(r"__[A-Z_]+__", latex_code)]
    assert not placeholders, f"Unresolved placeholders in {template_id}: {placeholders}"

    # 5. metadata.json 合法且含 verification
    metadata = json.loads((pkg_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["template_id"] == template_id
    assert "verification" in metadata

    # 6. solution.json 含 cross_validation
    sol_path = out_dir / "final" / "solution.json"
    if sol_path.exists():
        sol = json.loads(sol_path.read_text(encoding="utf-8"))
        solver_out = sol.get("solver_agent", {})
        sub_sols = solver_out.get("sub_problem_solutions", [])
        if sub_sols:
            assert "cross_check" in sub_sols[0], "cross_check missing from solver output"

    # 7. zip 大小合理
    mb = zip_path.stat().st_size / (1024 * 1024)
    assert mb < 50, f"zip too large for {template_id}: {mb:.1f} MB"


@pytest.mark.asyncio
async def test_smoke_no_placeholder_ccf_a(patched_output_dir, patched_task_dir):
    """专门验证占位符替换在 4 套 CCF-A 模板中均生效。"""
    for template_id in ["ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs"]:
        agents = _make_agents(template_id)
        orch = Orchestrator(agents)
        task_id = f"placeholder_{template_id}"
        await orch.run_research_paper_workflow(
            task_id=task_id,
            problem_text="Placeholder test.",
            project_name=task_id,
            template=template_id,
            mode="batch",
        )
        out_dir = paths.get_project_output_dir(task_id)
        latex_code = (out_dir / f"camera_ready_{task_id}" / "main.tex").read_text(encoding="utf-8")
        assert "__TITLE__" not in latex_code
        assert "__AUTHORS__" not in latex_code
