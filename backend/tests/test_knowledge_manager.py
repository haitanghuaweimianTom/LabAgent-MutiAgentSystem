"""KnowledgeManager 与知识库路由测试"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.knowledge_manager import (
    KnowledgeItem,
    FileMetadata,
    get_knowledge_manager,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def km(tmp_path, monkeypatch):
    """使用临时目录隔离的 KnowledgeManager"""
    import app.core.knowledge_manager as km_module
    monkeypatch.setattr(km_module, "_KB_DIR", tmp_path / "knowledge_bases")
    monkeypatch.setattr(km_module, "_KB_INDEX_FILE", tmp_path / "knowledge_bases" / "index.json")
    monkeypatch.setattr(km_module, "_KB_FILES_DIR", tmp_path / "knowledge_files")
    # 重置单例，确保使用新路径
    monkeypatch.setattr(km_module, "_knowledge_manager", None)
    manager = get_knowledge_manager()
    return manager


# ==================== update_item ====================

def test_update_note_content(km):
    base = km.create_base("test-base")
    item_id = km.add_item(base.id, KnowledgeItem(
        id="",
        type="note",
        content="原始笔记内容",
        source="manual",
        metadata={"author": "tester"},
        processingStatus="completed",
    ))

    ok = km.update_item(base.id, item_id, content="更新后的笔记内容")
    assert ok is True

    updated = next(i for i in km.get_items(base.id) if i.id == item_id)
    assert updated.content == "更新后的笔记内容"
    assert updated.source == "manual"
    assert updated.metadata["author"] == "tester"
    assert updated.updated_at > updated.created_at


def test_update_item_source_and_metadata(km):
    base = km.create_base("test-base")
    item_id = km.add_item(base.id, KnowledgeItem(
        id="",
        type="note",
        content="note",
        source="old-source",
        metadata={"keep": "value"},
        processingStatus="completed",
    ))

    ok = km.update_item(
        base.id,
        item_id,
        source="new-source",
        metadata={"new_key": "new_value"},
    )
    assert ok is True

    updated = next(i for i in km.get_items(base.id) if i.id == item_id)
    assert updated.source == "new-source"
    assert updated.metadata["keep"] == "value"
    assert updated.metadata["new_key"] == "new_value"
    # content 未提供，保持不变
    assert updated.content == "note"


def test_update_file_replacement(km):
    base = km.create_base("test-base")
    # 保存旧文件
    old_path = km.save_file("old.txt", b"old content")
    old_meta = FileMetadata(
        name=old_path.name,
        size=old_path.stat().st_size,
        ext=".txt",
        path=str(old_path),
    )
    item_id = km.add_item(base.id, KnowledgeItem(
        id="",
        type="file",
        content=old_meta,
        source=f"file:{old_path.name}",
        metadata={"extracted_text": "old content", "chunks": 1},
        processingStatus="completed",
    ))

    # 保存新文件
    new_path = km.save_file("new.txt", b"new content")
    new_meta = FileMetadata(
        name=new_path.name,
        size=new_path.stat().st_size,
        ext=".txt",
        path=str(new_path),
    )

    ok = km.update_item(
        base.id,
        item_id,
        content=new_meta,
        source=f"file:{new_path.name}",
        metadata={"extracted_text": "new content", "chunks": 1},
    )
    assert ok is True

    updated = next(i for i in km.get_items(base.id) if i.id == item_id)
    assert isinstance(updated.content, FileMetadata)
    assert updated.content.name == new_path.name
    assert updated.content.size == len(b"new content")

    # 旧文件应被删除
    assert not old_path.exists()
    # 新文件应存在
    assert new_path.exists()


def test_update_file_old_file_kept_when_same_name(km):
    base = km.create_base("test-base")
    path = km.save_file("same.txt", b"content v1")
    meta = FileMetadata(
        name=path.name,
        size=path.stat().st_size,
        ext=".txt",
        path=str(path),
    )
    item_id = km.add_item(base.id, KnowledgeItem(
        id="",
        type="file",
        content=meta,
        source=f"file:{path.name}",
        metadata={},
        processingStatus="completed",
    ))

    # 用同名（实际不可能由 save_file 产生，但测试防御逻辑）
    ok = km.update_item(base.id, item_id, content=meta)
    assert ok is True
    assert path.exists()


def test_update_item_not_found(km):
    base = km.create_base("test-base")
    assert km.update_item(base.id, "nonexistent", content="x") is False
    assert km.update_item("nonexistent-base", "nonexistent", content="x") is False


def test_update_item_type_mismatch(km):
    base = km.create_base("test-base")
    item_id = km.add_item(base.id, KnowledgeItem(
        id="",
        type="note",
        content="note",
        processingStatus="completed",
    ))
    with pytest.raises(ValueError, match="必须使用字符串更新"):
        km.update_item(base.id, item_id, content=FileMetadata(name="x.txt", size=0, ext=".txt", path=""))

    file_id = km.add_item(base.id, KnowledgeItem(
        id="",
        type="file",
        content=FileMetadata(name="x.txt", size=0, ext=".txt", path=""),
        processingStatus="completed",
    ))
    with pytest.raises(ValueError, match="必须使用 FileMetadata 更新"):
        km.update_item(base.id, file_id, content="string")


# ==================== 路由 PUT 端点 ====================

def test_put_update_note_endpoint(client, km):
    """client fixture 来自 conftest 或需自行创建"""
    base = km.create_base("test-base")
    item_id = km.add_item(base.id, KnowledgeItem(
        id="",
        type="note",
        content="original",
        processingStatus="completed",
    ))

    response = client.put(
        f"/api/v1/knowledge/bases/{base.id}/items/{item_id}",
        json={"content": "updated"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["item_id"] == item_id


def test_put_replace_file_endpoint(client, km):
    base = km.create_base("test-base")
    old_path = km.save_file("old.txt", b"old content")
    old_meta = FileMetadata(
        name=old_path.name,
        size=old_path.stat().st_size,
        ext=".txt",
        path=str(old_path),
    )
    item_id = km.add_item(base.id, KnowledgeItem(
        id="",
        type="file",
        content=old_meta,
        source=f"file:{old_path.name}",
        metadata={"extracted_text": "old content"},
        processingStatus="completed",
    ))

    response = client.put(
        f"/api/v1/knowledge/bases/{base.id}/items/{item_id}/file",
        files={"file": ("new.txt", b"new content", "text/plain")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["filename"] == "new.txt"
    assert data["total_chars"] == len("new content")

    updated = next(i for i in km.get_items(base.id) if i.id == item_id)
    assert updated.content.name == "new.txt"
    assert not old_path.exists()


def test_put_file_item_json_rejected(client, km):
    base = km.create_base("test-base")
    item_id = km.add_item(base.id, KnowledgeItem(
        id="",
        type="file",
        content=FileMetadata(name="x.txt", size=0, ext=".txt", path=""),
        processingStatus="completed",
    ))

    response = client.put(
        f"/api/v1/knowledge/bases/{base.id}/items/{item_id}",
        json={"content": "new"},
    )
    assert response.status_code == 400


def test_put_item_not_found(client, km):
    base = km.create_base("test-base")
    response = client.put(
        f"/api/v1/knowledge/bases/{base.id}/items/nonexistent",
        json={"content": "x"},
    )
    assert response.status_code == 404


def test_put_base_not_found(client, km):
    response = client.put(
        "/api/v1/knowledge/bases/nonexistent/items/nonexistent",
        json={"content": "x"},
    )
    assert response.status_code == 404
