"""Phase 0 测试：路径迁移 + KB scope 字段。

- test_paths_migration.py：get_project_data_subdir + migrate_legacy_data_dir
- test_kb_scope.py：KnowledgeBaseConfig 加 scope 后 list_bases 过滤 + query_context_for_task

每个测试用 monkeypatch 隔离 TASK_DATA_DIR / OUTPUT_DIR，避免污染真实目录。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# =====================================================
# 1. 路径迁移
# =====================================================


@pytest.fixture
def tmp_outputs_dir(tmp_path, monkeypatch):
    """把 OUTPUT_DIR 切到临时目录，迁移不影响真实 outputs/。"""
    from app.core import paths
    fake_outputs = tmp_path / "outputs"
    fake_outputs.mkdir(parents=True)
    # 改 PROJECT_ROOT 让 get_project_base_dir 用 tmp
    monkeypatch.setattr(paths, "_PROJECT_ROOT", tmp_path)
    # OUTPUT_DIR 也指向 fake
    monkeypatch.setattr(paths, "OUTPUT_DIR", fake_outputs / "_global")
    return fake_outputs


def test_get_project_data_subdir_creates_dirs(tmp_outputs_dir):
    """get_project_data_subdir 应自动创建 user_upload / self_collected 子目录。"""
    from app.core.paths import get_project_data_subdir

    p1 = get_project_data_subdir("proj1", "user_upload")
    p2 = get_project_data_subdir("proj1", "self_collected")

    assert p1.exists()
    assert p2.exists()
    assert p1.name == "user_upload"
    assert p2.name == "self_collected"
    assert p1.parent == p2.parent


def test_get_project_data_subdir_invalid_source(tmp_outputs_dir):
    """非法 source 应抛 ValueError。"""
    from app.core.paths import get_project_data_subdir

    with pytest.raises(ValueError, match="invalid source"):
        get_project_data_subdir("proj1", "hack")


def test_get_project_data_subdir_no_project(tmp_outputs_dir):
    """无项目时回退到全局 uploads。"""
    from app.core.paths import get_project_data_subdir

    p = get_project_data_subdir(None, "user_upload")
    assert p.exists()
    assert p.name == "user_upload"
    # 父目录应是 DATA_DIR（全局）
    from app.core.paths import DATA_DIR
    assert p.parent == DATA_DIR


def test_migrate_legacy_moves_files(tmp_outputs_dir):
    """migrate_legacy_data_dir 应把 outputs/<name>/data/ 根下文件移到 user_uploads/。"""
    from app.core.paths import migrate_legacy_data_dir

    proj = tmp_outputs_dir / "proj1"
    data_dir = proj / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "input.csv").write_text("a,b\n1,2\n")
    (data_dir / "notes.txt").write_text("hello")

    stats = migrate_legacy_data_dir()

    assert stats["projects_scanned"] == 1
    assert stats["files_moved"] == 2
    # 旧位置文件应已不存在
    assert not (data_dir / "input.csv").exists()
    assert not (data_dir / "notes.txt").exists()
    # 新位置
    assert (data_dir / "user_uploads" / "input.csv").exists()
    assert (data_dir / "user_uploads" / "notes.txt").read_text() == "hello"
    # 标记文件
    assert (data_dir / ".migrated_v530").exists()


def test_migrate_legacy_idempotent(tmp_outputs_dir):
    """重复调用 migrate 不应重复移动文件。"""
    from app.core.paths import migrate_legacy_data_dir

    proj = tmp_outputs_dir / "proj1"
    data_dir = proj / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "input.csv").write_text("a,b\n1,2\n")

    s1 = migrate_legacy_data_dir()
    s2 = migrate_legacy_data_dir()

    assert s1["files_moved"] == 1
    assert s2["files_moved"] == 0  # 第二次什么也不做
    assert s2["skipped"] == 1
    # 文件仍在 user_uploads/
    assert (data_dir / "user_uploads" / "input.csv").exists()


def test_migrate_legacy_skips_already_migrated_dirs(tmp_outputs_dir):
    """已有 user_uploads/ 子目录的项目（标记文件存在）应被跳过。"""
    from app.core.paths import migrate_legacy_data_dir

    proj = tmp_outputs_dir / "proj1"
    data_dir = proj / "data"
    data_dir.mkdir(parents=True)
    (data_dir / ".migrated_v530").touch()  # 手动写标记
    (data_dir / "old.csv").write_text("old")  # 仍在根下（不应该移动）

    stats = migrate_legacy_data_dir()

    assert stats["projects_scanned"] == 1
    assert stats["files_moved"] == 0
    assert stats["skipped"] == 1
    # 旧文件仍在根下
    assert (data_dir / "old.csv").exists()


def test_migrate_legacy_preserves_subdirs(tmp_outputs_dir):
    """如果 data/ 已有 user_uploads/ 和 self_collected/ 子目录，不动它们。"""
    from app.core.paths import migrate_legacy_data_dir

    proj = tmp_outputs_dir / "proj1"
    data_dir = proj / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "user_uploads").mkdir()
    (data_dir / "self_collected").mkdir()
    (data_dir / "self_collected" / "url1.txt").write_text("u1")
    (data_dir / "user_uploads" / "user.csv").write_text("u")

    stats = migrate_legacy_data_dir()

    assert stats["projects_scanned"] == 1
    assert stats["files_moved"] == 0  # 已有结构 → 不动
    # 标记文件应被创建
    assert (data_dir / ".migrated_v530").exists()


def test_migrate_legacy_handles_missing_outputs(tmp_path, monkeypatch):
    """outputs/ 不存在时安全跳过。"""
    from app.core import paths

    # PROJECT_ROOT 指向没 outputs/ 的位置
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(paths, "_PROJECT_ROOT", empty)

    from app.core.paths import migrate_legacy_data_dir
    stats = migrate_legacy_data_dir()

    assert stats["projects_scanned"] == 0
    assert stats["files_moved"] == 0


def test_migrate_legacy_skips_global_project(tmp_outputs_dir):
    """_global 项目目录不应被扫描。"""
    from app.core.paths import migrate_legacy_data_dir

    # 创建 _global 目录（模拟真实 outputs/_global）
    global_dir = tmp_outputs_dir / "_global"
    (global_dir / "data").mkdir(parents=True)
    (global_dir / "data" / "system.csv").write_text("g")

    stats = migrate_legacy_data_dir()

    assert stats["projects_scanned"] == 0
    # _global/data 文件不应被移动
    assert (global_dir / "data" / "system.csv").exists()
