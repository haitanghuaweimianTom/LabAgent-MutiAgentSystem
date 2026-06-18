"""Phase 3 第二组测试：solver 强制 CodeManifest + tasks router camera-ready 端点。"""
import json
import ast
from pathlib import Path

import pytest

from app.agents.solver_agent import SolverAgent


# ==================== 1. Solver _build_manifest_report ====================

@pytest.fixture
def solver():
    return SolverAgent.__new__(SolverAgent)


def test_manifest_report_method_exists(solver):
    assert hasattr(solver, "_build_manifest_report")


def test_manifest_report_empty(solver):
    r = solver._build_manifest_report([], sub_problem_id=1)
    assert r["valid"] is False
    assert r["issues"] == ["empty code_files"]
    assert r["file_count"] == 0
    assert r["sub_problem_id"] == 1


def test_manifest_report_single_short_file(solver):
    r = solver._build_manifest_report([{"filename": "s.py", "code": "x=1"}], sub_problem_id=2)
    assert r["file_count"] == 1
    assert "manifest" in r


def test_manifest_report_rejects_single_400_loc_file(solver):
    """单文件 > 300 行 → 报告 invalid（软约束，记录但不阻塞主流程）。"""
    long_code = "x=1\n" * 400
    r = solver._build_manifest_report([{"filename": "solver.py", "code": long_code}], sub_problem_id=3)
    assert r["valid"] is False
    assert any("300" in i for i in r["issues"])


def test_manifest_report_normalizes_filename_to_path(solver):
    """LLM 可能用 'filename' 而非 'path'，应兼容。"""
    r = solver._build_manifest_report(
        [{"filename": "data.py", "code": "x=1\n" * 50},
         {"filename": "main.py", "code": "import data"}],
        sub_problem_id=4,
    )
    assert r["valid"] is True
    paths = [f["path"] for f in r["manifest"]["files"]]
    assert "data.py" in paths
    assert "main.py" in paths


def test_manifest_report_handles_string_list(solver):
    """LLM 偶尔直接返回 [str]，应归一化为单文件。"""
    r = solver._build_manifest_report(["print(1)", "print(2)"], sub_problem_id=5)
    assert r["file_count"] == 2
    # 全部规约到 path='solver.py', role='solver'
    for f in r["manifest"]["files"]:
        assert f["path"] == "solver.py"
        assert f["role"] == "solver"


def test_manifest_report_well_formed_multi_file(solver):
    r = solver._build_manifest_report([
        {"filename": "data_process_sub1.py", "role": "data_processing", "code": "x=1\n" * 50},
        {"filename": "main.py", "code": "import dp", "entry_point": True},
    ], sub_problem_id=6)
    assert r["valid"] is True
    assert r["file_count"] == 2


# ==================== 2. router 端点存在 + 签名 ====================

def test_router_tasks_camera_ready_endpoints():
    """tasks router 必须有 /camera-ready 的 POST 和 GET 端点。"""
    src = Path(__file__).parent.parent / "app" / "routers" / "tasks.py"
    src = src.read_text(encoding="utf-8")
    assert '@router.post("/{task_id}/camera-ready")' in src
    assert '@router.get("/{task_id}/camera-ready")' in src


def test_router_tasks_post_camera_ready_signature():
    src = Path(__file__).parent.parent / "app" / "routers" / "tasks.py"
    src = src.read_text(encoding="utf-8")
    # 解析 AST 找 build_camera_ready
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "build_camera_ready":
            found = True
            arg_names = [a.arg for a in node.args.args]
            assert "task_id" in arg_names
            # req 是 Optional[dict]
            assert any("req" in a.arg for a in node.args.args + node.args.kwonlyargs)
            break
    assert found, "build_camera_ready not found"


def test_router_tasks_get_camera_ready_signature():
    src = Path(__file__).parent.parent / "app" / "routers" / "tasks.py"
    src = src.read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_camera_ready_status":
            found = True
            arg_names = [a.arg for a in node.args.args]
            assert "task_id" in arg_names
            break
    assert found, "get_camera_ready_status not found"


# ==================== 3. router 端点引用了 camera_ready 服务 ====================

def test_router_camera_ready_uses_service():
    """router 必须调用 collect_artifacts + build 而非手写。"""
    src = Path(__file__).parent.parent / "app" / "routers" / "tasks.py"
    src = src.read_text(encoding="utf-8")
    # 找到 build_camera_ready 函数体
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "build_camera_ready":
            # 找函数体中的 import names
            imports = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.ImportFrom):
                    for alias in sub.names:
                        imports.add(alias.name)
                elif isinstance(sub, ast.Import):
                    for alias in sub.names:
                        imports.add(alias.name)
            # 必须引用 collect_artifacts / build
            assert "collect_artifacts" in imports
            assert "build" in imports
            return
    pytest.fail("build_camera_ready function not found")
