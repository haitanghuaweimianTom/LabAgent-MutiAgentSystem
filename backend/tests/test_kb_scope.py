"""Phase 0 测试：知识库 scope + project_name + 多 KB 注入（query_context_for_task）。

每个测试用 monkeypatch 把 _KB_DIR / _KB_INDEX_FILE / _KB_FILES_DIR 切到临时目录，
避免污染真实 data/knowledge_bases/。
"""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def tmp_kb_dir(tmp_path, monkeypatch):
    """把 KnowledgeManager 用的 _KB_DIR / _KB_INDEX_FILE / _KB_FILES_DIR 切到 tmp。"""
    from app.core import knowledge_manager as km_mod

    fake_dir = tmp_path / "kb"
    fake_dir.mkdir(parents=True, exist_ok=True)
    fake_files = tmp_path / "kb_files"
    fake_files.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(km_mod, "_KB_DIR", fake_dir)
    monkeypatch.setattr(km_mod, "_KB_INDEX_FILE", fake_dir / "index.json")
    monkeypatch.setattr(km_mod, "_KB_FILES_DIR", fake_files)
    return fake_dir


@pytest.fixture
def km(tmp_kb_dir):
    """每个测试都用一个全新的 KnowledgeManager。"""
    # 预先写一个空 index 文件，避免 KnowledgeManager 启动时跑 _migrate_legacy
    # 创建出 "默认知识库" 干扰断言
    (tmp_kb_dir / "index.json").write_text(json.dumps({"bases": []}))
    from app.core.knowledge_manager import KnowledgeManager
    return KnowledgeManager()


# =====================================================
# 1. KnowledgeBaseConfig 默认值
# =====================================================


def test_config_default_scope_is_global():
    """新建的 KnowledgeBaseConfig 默认 scope='global', project_name=None。"""
    from app.core.knowledge_manager import KnowledgeBaseConfig

    cfg = KnowledgeBaseConfig(id="kb_test", name="t", description="")
    assert cfg.scope == "global"
    assert cfg.project_name is None


def test_config_explicit_scope():
    """显式传入 scope='project' + project_name 应被接受。"""
    from app.core.knowledge_manager import KnowledgeBaseConfig

    cfg = KnowledgeBaseConfig(
        id="kb_p", name="proj-kb", description="", scope="project", project_name="proj1"
    )
    assert cfg.scope == "project"
    assert cfg.project_name == "proj1"


# =====================================================
# 2. create_base 的 scope 校验
# =====================================================


def test_create_base_global_default(km):
    """create_base 默认 scope='global'。"""
    b = km.create_base(name="g1")
    assert b.scope == "global"
    assert b.project_name is None
    assert b in km._bases.values()


def test_create_base_project_requires_project_name(km):
    """scope='project' 但没传 project_name 应抛 ValueError。"""
    with pytest.raises(ValueError, match="project_name"):
        km.create_base(name="p1", scope="project")


def test_create_base_project_success(km):
    """scope='project' + project_name 应正常创建。"""
    b = km.create_base(name="p1", scope="project", project_name="proj1")
    assert b.scope == "project"
    assert b.project_name == "proj1"


def test_create_base_invalid_scope(km):
    """scope 非法值应抛 ValueError。"""
    with pytest.raises(ValueError, match="invalid scope"):
        km.create_base(name="x", scope="team")  # type: ignore[arg-type]


# =====================================================
# 3. list_bases 过滤
# =====================================================


def test_list_bases_no_filter_returns_all(km):
    """scope=None 应返回所有 KB（含 global 和 project）。"""
    km.create_base(name="g1")  # global
    km.create_base(name="g2")  # global
    km.create_base(name="p1", scope="project", project_name="proj1")

    all_bases = km.list_bases()
    names = {b["name"] for b in all_bases}
    assert names == {"g1", "g2", "p1"}


def test_list_bases_filter_global(km):
    """scope='global' 只返回 global KB。"""
    km.create_base(name="g1")
    km.create_base(name="g2")
    km.create_base(name="p1", scope="project", project_name="proj1")

    global_only = km.list_bases(scope="global")
    names = {b["name"] for b in global_only}
    assert names == {"g1", "g2"}


def test_list_bases_filter_project(km):
    """scope='project' 只返回 project KB。"""
    km.create_base(name="g1")
    km.create_base(name="p1", scope="project", project_name="proj1")
    km.create_base(name="p2", scope="project", project_name="proj2")

    proj_only = km.list_bases(scope="project")
    names = {b["name"] for b in proj_only}
    assert names == {"p1", "p2"}


def test_list_bases_filter_project_with_name(km):
    """scope='project' + project_name 应只返回该项目 KB。"""
    km.create_base(name="p1", scope="project", project_name="proj1")
    km.create_base(name="p2", scope="project", project_name="proj2")

    proj1_only = km.list_bases(scope="project", project_name="proj1")
    names = {b["name"] for b in proj1_only}
    assert names == {"p1"}


def test_list_bases_returns_scope_fields(km):
    """list_bases 返回项应包含 scope + project_name 字段。"""
    b = km.create_base(name="p1", scope="project", project_name="proj1")
    items = km.list_bases()
    found = next(i for i in items if i["id"] == b.id)
    assert found["scope"] == "project"
    assert found["project_name"] == "proj1"


def test_list_bases_legacy_default_global(km):
    """没有 scope 字段的旧 KB（直接构造）应默认为 global。"""
    from app.core.knowledge_manager import KnowledgeBaseConfig

    legacy = KnowledgeBaseConfig(id="legacy", name="legacy")
    km._bases[legacy.id] = legacy
    items = km.list_bases()
    found = next(i for i in items if i["id"] == "legacy")
    assert found["scope"] == "global"
    assert found["project_name"] is None


# =====================================================
# 4. _resolve_task_bases：自动选择 + 排序
# =====================================================


def test_resolve_task_bases_explicit_ids(km):
    """显式 base_ids 优先，忽略 scope。"""
    g = km.create_base(name="g1")
    p = km.create_base(name="p1", scope="project", project_name="proj1")

    # 即便 p 不属于 proj2，显式传也应返回
    bases = km._resolve_task_bases(task_project_name="proj2", base_ids=[g.id, p.id])
    ids = {b.id for b in bases}
    assert ids == {g.id, p.id}


def test_resolve_task_bases_auto_includes_global(km):
    """自动模式下，无项目时 = 全部 global。"""
    g = km.create_base(name="g1")
    p = km.create_base(name="p1", scope="project", project_name="proj1")

    bases = km._resolve_task_bases(task_project_name=None, base_ids=None)
    ids = {b.id for b in bases}
    assert g.id in ids
    assert p.id not in ids  # 项目私有 → 不包含


def test_resolve_task_bases_auto_includes_project_match(km):
    """自动模式下，task_project_name 匹配 → 包含对应 project KB。"""
    g = km.create_base(name="g1")
    p1 = km.create_base(name="p1", scope="project", project_name="proj1")
    p2 = km.create_base(name="p2", scope="project", project_name="proj2")

    bases = km._resolve_task_bases(task_project_name="proj1", base_ids=None)
    ids = {b.id for b in bases}
    assert g.id in ids
    assert p1.id in ids
    assert p2.id not in ids


def test_resolve_task_bases_project_first(km):
    """项目私有 KB 应排在 global 前面。"""
    g = km.create_base(name="g1")
    p = km.create_base(name="p1", scope="project", project_name="proj1")

    bases = km._resolve_task_bases(task_project_name="proj1", base_ids=None)
    # p (project) 应在 g (global) 之前
    assert bases[0].id == p.id
    assert bases[1].id == g.id


def test_resolve_task_bases_explicit_unknown_id_skipped(km):
    """显式 base_ids 含未知 ID 时应静默跳过。"""
    g = km.create_base(name="g1")

    bases = km._resolve_task_bases(
        task_project_name=None, base_ids=[g.id, "kb_doesnotexist"]
    )
    ids = {b.id for b in bases}
    assert ids == {g.id}


# =====================================================
# 5. query_context_for_task：合并 + token 均分
# =====================================================


def test_query_context_for_task_no_bases_returns_empty(km):
    """没有任何 KB 时返回空字符串。"""
    ctx = km.query_context_for_task(
        task_project_name="proj1", base_ids=None, query="test"
    )
    assert ctx == ""


def test_query_context_for_task_explicit_ids(km):
    """显式 base_ids 调用 query_context_for_task 不会抛异常（即使 KB 无 items）。"""
    km.create_base(name="g1")
    km.create_base(name="g2")

    # 没有 items 的 KB → query_context 返回空 → 合并结果为空
    ctx = km.query_context_for_task(
        task_project_name=None, base_ids=None, query="test"
    )
    # 没 items → 应该是空（不抛错）
    assert ctx == ""


def test_query_context_for_task_handles_query_failure(monkeypatch, km):
    """query_context 抛异常时，该 KB 被跳过，不影响其他 KB。"""
    g = km.create_base(name="g1")
    g2 = km.create_base(name="g2")

    def fake_query_context(base_id, query, top_k=3, max_chars=1500):
        if base_id == g.id:
            raise RuntimeError("simulated KB failure")
        return f"ctx-from-{base_id}"

    monkeypatch.setattr(km, "query_context", fake_query_context)

    ctx = km.query_context_for_task(
        task_project_name=None, base_ids=None, query="q"
    )
    # g 失败被跳过，g2 应正常返回
    assert "ctx-from-" + g.id not in ctx  # 失败被跳过
    assert g2.id in ctx  # g2 成功返回


def test_query_context_for_task_token_split(km, monkeypatch):
    """max_chars 应在 KB 数之间均分。"""
    km.create_base(name="g1")
    km.create_base(name="g2")

    seen_max_chars = []

    def fake_query_context(base_id, query, top_k=3, max_chars=1500):
        seen_max_chars.append(max_chars)
        return f"ctx:{base_id}"

    monkeypatch.setattr(km, "query_context", fake_query_context)

    km.query_context_for_task(
        task_project_name=None, base_ids=None, query="q", max_chars=4000
    )
    # 2 个 KB → 每个分到 2000
    assert seen_max_chars == [2000, 2000]


def test_query_context_for_task_header_includes_scope(km, monkeypatch):
    """合并后的 KB header 应标明 scope 类型。"""
    g = km.create_base(name="global_kb")
    p = km.create_base(name="proj_kb", scope="project", project_name="proj1")

    def fake_query_context(base_id, query, top_k=3, max_chars=1500):
        return f"content-{base_id}"

    monkeypatch.setattr(km, "query_context", fake_query_context)

    ctx = km.query_context_for_task(
        task_project_name="proj1", base_ids=None, query="q"
    )
    # 项目私有 KB 应标记 (项目私有)
    assert "项目私有" in ctx
    # 找到全局 KB 的 header 行
    lines = ctx.split("\n")
    # header 行包含 "【知识库:"  →  找到包含 global_kb 名称的那行
    global_header = next(
        ln for ln in lines if ln.startswith("【") and g.name in ln
    )
    assert "项目私有" not in global_header