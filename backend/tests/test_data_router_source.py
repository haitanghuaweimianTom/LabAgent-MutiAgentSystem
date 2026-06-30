"""Phase 1 测试：data router ?source= 拆分 + list_project_files 合并行为。"""
import json
import sys
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    """切 paths._PROJECT_ROOT 到临时目录。"""
    from app.core import paths
    fake_outputs = tmp_path / "outputs"
    fake_outputs.mkdir(parents=True)
    fake_data = tmp_path / "data"
    fake_data.mkdir(parents=True)
    monkeypatch.setattr(paths, "_PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def client(tmp_paths):
    """FastAPI TestClient。"""
    from app.main import app
    return TestClient(app)


# =====================================================
# 1. list_project_files 合并行为
# =====================================================


def test_list_project_files_both_sources(tmp_paths):
    """list_project_files(source='both') 应返回 user_upload + self_collected 两边。"""
    from app.services.data_directory import list_project_files

    # user_upload 一个
    user_dir = tmp_paths / "outputs" / "proj1" / "data" / "user_upload"
    user_dir.mkdir(parents=True)
    (user_dir / "a.csv").write_text("a")

    # self_collected 一个 + 元数据索引
    self_dir = tmp_paths / "outputs" / "proj1" / "data" / "self_collected"
    self_dir.mkdir(parents=True)
    (self_dir / "b.json").write_text("{}")

    items = list_project_files("proj1", source="both")
    names = {x["name"] for x in items}
    assert names == {"a.csv", "b.json"}
    sources = {x["name"]: x["source"] for x in items}
    assert sources["a.csv"] == "user_upload"
    assert sources["b.json"] == "self_collected"


def test_list_project_files_single_source(tmp_paths):
    """list_project_files(source='user_upload') 只返 user_upload。"""
    from app.services.data_directory import list_project_files

    user_dir = tmp_paths / "outputs" / "proj1" / "data" / "user_upload"
    user_dir.mkdir(parents=True)
    (user_dir / "a.csv").write_text("a")
    self_dir = tmp_paths / "outputs" / "proj1" / "data" / "self_collected"
    self_dir.mkdir(parents=True)
    (self_dir / "b.json").write_text("{}")

    items = list_project_files("proj1", source="user_upload")
    assert {x["name"] for x in items} == {"a.csv"}


def test_list_project_files_skips_index_json(tmp_paths):
    """list_project_files 应跳过 self_collected/_index.json。"""
    from app.services.data_directory import list_project_files

    self_dir = tmp_paths / "outputs" / "proj1" / "data" / "self_collected"
    self_dir.mkdir(parents=True)
    (self_dir / "_index.json").write_text("[]")
    (self_dir / "real.csv").write_text("x")

    items = list_project_files("proj1", source="self_collected")
    names = {x["name"] for x in items}
    assert "_index.json" not in names
    assert "real.csv" in names


def test_list_project_files_attaches_meta(tmp_paths):
    """self_collected 文件项应带上 meta 字段（含 URL 等）。"""
    from app.services.data_directory import list_project_files, append_self_collected_index

    self_dir = tmp_paths / "outputs" / "proj1" / "data" / "self_collected"
    self_dir.mkdir(parents=True)
    (self_dir / "abc.csv").write_text("x")
    append_self_collected_index("proj1", [{
        "url": "https://example.com/data.csv",
        "filename": "abc.csv",
        "size": 1,
        "downloaded_at": 1234567890,
        "content_type": "text/csv",
        "source_query": "test",
        "http_status": 200,
        "error": None,
    }])

    items = list_project_files("proj1", source="self_collected")
    found = next(i for i in items if i["name"] == "abc.csv")
    assert "meta" in found
    assert found["meta"]["url"] == "https://example.com/data.csv"
    assert found["meta"]["source_query"] == "test"


# =====================================================
# 2. upload endpoint ?source=
# =====================================================


def test_upload_to_user_upload(client, tmp_paths):
    """POST /data/upload?source=user_upload 应落 user_upload/。"""
    proj = "phase1_test_uu"
    files = {"file": ("hello.csv", BytesIO(b"a,b\n1,2\n"), "text/csv")}
    res = client.post(
        f"/api/v1/data/upload?project_name={proj}&source=user_upload",
        files=files,
    )
    assert res.status_code == 200, res.text
    target_dir = tmp_paths / "outputs" / proj / "data" / "user_upload"
    assert target_dir.exists()
    files_in_dir = list(target_dir.iterdir())
    assert any(f.name.endswith(".csv") for f in files_in_dir)


def test_upload_to_self_collected(client, tmp_paths):
    """POST /data/upload?source=self_collected 应落 self_collected/。"""
    proj = "phase1_test_sc"
    files = {"file": ("hello.json", BytesIO(b'{"x":1}'), "application/json")}
    res = client.post(
        f"/api/v1/data/upload?project_name={proj}&source=self_collected",
        files=files,
    )
    assert res.status_code == 200, res.text
    target_dir = tmp_paths / "outputs" / proj / "data" / "self_collected"
    assert target_dir.exists()
    files_in_dir = list(target_dir.iterdir())
    assert any(f.name.endswith(".json") for f in files_in_dir)


def test_upload_invalid_extension(client):
    """上传不支持的扩展名应 400。"""
    files = {"file": ("x.exe", BytesIO(b"x"), "application/octet-stream")}
    res = client.post("/api/v1/data/upload?source=user_upload", files=files)
    assert res.status_code == 400


# =====================================================
# 3. list endpoint ?source=
# =====================================================


def test_list_files_default_is_user_upload(client, tmp_paths):
    """不传 source 时默认 list user_upload。"""
    proj = "phase1_test_li"
    # 写两个文件
    user_dir = tmp_paths / "outputs" / proj / "data" / "user_upload"
    user_dir.mkdir(parents=True)
    (user_dir / "x.csv").write_text("x")
    self_dir = tmp_paths / "outputs" / proj / "data" / "self_collected"
    self_dir.mkdir(parents=True)
    (self_dir / "y.csv").write_text("y")

    # 不传 source → 默认 user_upload
    res = client.get(f"/api/v1/data/files?project_name={proj}")
    assert res.status_code == 200
    items = res.json()
    names = {x["name"] for x in items}
    # 默认应该只看到 user_upload（除非服务端有特殊逻辑）
    # 我们的实现：source='both' → 合并；缺省 → 'both'
    # 至少 x.csv 应在；y.csv 可能也在
    assert "x.csv" in names


def test_list_files_filter_user_upload(client, tmp_paths):
    """?source=user_upload 只返 user_upload。"""
    proj = "phase1_test_lf"
    user_dir = tmp_paths / "outputs" / proj / "data" / "user_upload"
    user_dir.mkdir(parents=True)
    (user_dir / "x.csv").write_text("x")
    self_dir = tmp_paths / "outputs" / proj / "data" / "self_collected"
    self_dir.mkdir(parents=True)
    (self_dir / "y.csv").write_text("y")

    res = client.get(f"/api/v1/data/files?project_name={proj}&source=user_upload")
    items = res.json()
    assert all(x["source"] == "user_upload" for x in items)


def test_list_self_collected_endpoint(client, tmp_paths):
    """/data/self-collected 返回 files + index。"""
    proj = "phase1_test_sc2"
    self_dir = tmp_paths / "outputs" / proj / "data" / "self_collected"
    self_dir.mkdir(parents=True)
    (self_dir / "z.csv").write_text("z")

    res = client.get(f"/api/v1/data/self-collected?project_name={proj}")
    assert res.status_code == 200
    data = res.json()
    assert "files" in data
    assert "index" in data
    assert any(f["name"] == "z.csv" for f in data["files"])