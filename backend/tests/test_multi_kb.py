"""Phase 4 测试：多 KB 注入 + 向后兼容 + TaskCreateRequest.get_effective_kb_ids。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# =====================================================
# 1. TaskCreateRequest.get_effective_kb_ids
# =====================================================


def test_get_effective_kb_ids_priority_list():
    """knowledge_base_ids 优先于 knowledge_base_id。"""
    from app.schemas.schemas import TaskCreateRequest

    req = TaskCreateRequest(
        problem_text="x",
        knowledge_base_id="old_id",
        knowledge_base_ids=["new1", "new2"],
    )
    assert req.get_effective_kb_ids() == ["new1", "new2"]


def test_get_effective_kb_ids_fallback_to_single():
    """没有 ids 时退回 knowledge_base_id。"""
    from app.schemas.schemas import TaskCreateRequest

    req = TaskCreateRequest(problem_text="x", knowledge_base_id="old_id")
    assert req.get_effective_kb_ids() == ["old_id"]


def test_get_effective_kb_ids_empty():
    """都没有时返回空列表。"""
    from app.schemas.schemas import TaskCreateRequest

    req = TaskCreateRequest(problem_text="x")
    assert req.get_effective_kb_ids() == []


# =====================================================
# 2. BaseAgent._inject_knowledge_context 多 KB 优先级
# =====================================================


@pytest.fixture
def tmp_kb_dir(tmp_path, monkeypatch):
    import json
    from app.core import knowledge_manager as km_mod
    fake_dir = tmp_path / "kb"
    fake_dir.mkdir(parents=True, exist_ok=True)
    fake_files = tmp_path / "kb_files"
    fake_files.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(km_mod, "_KB_DIR", fake_dir)
    monkeypatch.setattr(km_mod, "_KB_INDEX_FILE", fake_dir / "index.json")
    monkeypatch.setattr(km_mod, "_KB_FILES_DIR", fake_files)
    (fake_dir / "index.json").write_text(json.dumps({"bases": []}))
    return fake_dir


@pytest.fixture
def km(tmp_kb_dir):
    from app.core.knowledge_manager import KnowledgeManager
    return KnowledgeManager()


class _StubAgent:
    """最小可实例化的 BaseAgent 子类（避免 abstract 错误）。"""

    def __init__(self, name="stub"):
        # v5.3.0: 模拟 BaseAgent 内部属性
        self.name = name
        self._knowledge_base_id = None
        self._knowledge_base_ids = None
        self._task_project_name = None

    def _inject_knowledge_context(
        self, query_text, top_k=3, base_id=None,
        base_ids=None, project_name=None,
    ):
        # 复用 BaseAgent 真实实现
        from app.agents.base import BaseAgent
        return BaseAgent._inject_knowledge_context(
            self, query_text, top_k=top_k, base_id=base_id,
            base_ids=base_ids, project_name=project_name,
        )


def _patch_km(monkeypatch, km):
    """把 get_knowledge_manager() 切到测试用的 km（patch knowledge_manager 模块）。"""
    from app.core import knowledge_manager as km_mod
    monkeypatch.setattr(km_mod, "get_knowledge_manager", lambda: km)


def test_inject_knowledge_context_uses_base_ids(monkeypatch, km):
    """base_ids 显式传入 → 应走 query_context_for_task。"""
    _patch_km(monkeypatch, km)
    captured = {}

    def fake_query_context_for_task(task_project_name, base_ids, query, top_k=3, max_chars=4000):
        captured["task_project_name"] = task_project_name
        captured["base_ids"] = list(base_ids)
        captured["query"] = query
        captured["max_chars"] = max_chars
        return "merged-context"

    monkeypatch.setattr(km, "query_context_for_task", fake_query_context_for_task)

    agent = _StubAgent(name="test_agent")
    result = agent._inject_knowledge_context(
        query_text="hello",
        base_ids=["kb_a", "kb_b"],
        project_name="proj1",
    )

    assert "merged-context" in result
    assert captured["base_ids"] == ["kb_a", "kb_b"]
    assert captured["task_project_name"] == "proj1"
    assert captured["max_chars"] == 4000


def test_inject_knowledge_context_uses_instance_attrs(monkeypatch, km):
    """agent._knowledge_base_ids 设置后 → 应被使用。"""
    _patch_km(monkeypatch, km)
    captured = {}

    def fake_query_context_for_task(task_project_name, base_ids, query, top_k=3, max_chars=4000):
        captured["base_ids"] = list(base_ids)
        captured["project_name"] = task_project_name
        return "ctx"

    monkeypatch.setattr(km, "query_context_for_task", fake_query_context_for_task)

    agent = _StubAgent(name="test_agent2")
    agent._knowledge_base_ids = ["kb_x"]
    agent._task_project_name = "proj_x"

    agent._inject_knowledge_context(query_text="q")
    assert captured["base_ids"] == ["kb_x"]
    assert captured["project_name"] == "proj_x"


def test_inject_knowledge_context_fallback_to_base_id(monkeypatch, km):
    """没 base_ids 时退回 base_id → query_context。"""
    _patch_km(monkeypatch, km)
    captured = {}

    def fake_query_context(base_id, query, top_k=3, max_chars=1500):
        captured["base_id"] = base_id
        captured["max_chars"] = max_chars
        return "single-ctx"

    monkeypatch.setattr(km, "query_context", fake_query_context)

    agent = _StubAgent(name="test_agent3")
    agent._knowledge_base_id = "kb_legacy"

    result = agent._inject_knowledge_context(query_text="q")
    assert "single-ctx" in result
    assert captured["base_id"] == "kb_legacy"


def test_inject_knowledge_context_auto_select_by_project(monkeypatch, km):
    """没 base_ids + 有 project → 自动选 (query_context_for_task)。"""
    _patch_km(monkeypatch, km)
    captured = {}

    def fake_query_context_for_task(task_project_name, base_ids, query, top_k=3, max_chars=4000):
        captured["project"] = task_project_name
        captured["base_ids"] = base_ids
        return "auto-ctx"

    monkeypatch.setattr(km, "query_context_for_task", fake_query_context_for_task)

    agent = _StubAgent(name="test_agent4")
    agent._task_project_name = "auto_proj"

    result = agent._inject_knowledge_context(query_text="q")
    assert "auto-ctx" in result
    assert captured["project"] == "auto_proj"
    assert captured["base_ids"] is None


def test_inject_knowledge_context_fallback_to_all(monkeypatch, km):
    """什么都没设 → query_all_context。"""
    _patch_km(monkeypatch, km)
    captured = {}

    def fake_query_all_context(query, top_k=3, max_chars=1500):
        captured["query"] = query
        return "all-ctx"

    monkeypatch.setattr(km, "query_all_context", fake_query_all_context)

    agent = _StubAgent(name="test_agent5")
    result = agent._inject_knowledge_context(query_text="q")
    assert "all-ctx" in result
    assert captured["query"] == "q"


def test_inject_knowledge_context_silent_on_error(monkeypatch, km):
    """KB 查询异常时静默失败 → 返回 ""。"""
    _patch_km(monkeypatch, km)

    def fake_query_context_for_task(*args, **kwargs):
        raise RuntimeError("simulated")

    monkeypatch.setattr(km, "query_context_for_task", fake_query_context_for_task)

    agent = _StubAgent(name="test_agent6")
    agent._knowledge_base_ids = ["kb_x"]

    result = agent._inject_knowledge_context(query_text="q")
    assert result == ""  # 异常被吞掉


# =====================================================
# 3. KB scope 通过 router (API) 的端到端
# =====================================================


def test_create_base_with_scope_project_via_manager(km):
    """create_base + scope='project' + project_name 应落 dict。"""
    base = km.create_base(name="proj_kb", scope="project", project_name="myproj")
    assert base.scope == "project"
    assert base.project_name == "myproj"
    # list_bases 应能查到
    items = km.list_bases(scope="project", project_name="myproj")
    assert any(i["id"] == base.id for i in items)


def test_query_context_for_task_uses_auto_when_no_ids(km):
    """base_ids=None, task_project_name=... → 自动选。"""
    # 创建 1 个 global + 1 个 project 匹配
    g = km.create_base(name="g1")
    p = km.create_base(name="p1", scope="project", project_name="auto_proj")

    bases = km._resolve_task_bases(task_project_name="auto_proj", base_ids=None)
    ids = {b.id for b in bases}
    assert g.id in ids
    assert p.id in ids