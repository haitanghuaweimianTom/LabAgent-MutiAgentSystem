"""知识库 RESTful API (v2 多库版)

参照 cherry-studio KnowledgeService 设计，支持多知识库管理。
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, File, UploadFile, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..core.knowledge_manager import (
    get_knowledge_manager,
    KnowledgeItem,
    FileMetadata,
    KnowledgeBaseConfig,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["知识库"])


# ===== Pydantic 请求模型 =====

class CreateBaseRequest(BaseModel):
    name: str
    description: str = ""
    # v5.3.0: 两级 KB scope
    scope: Literal["global", "project"] = "global"
    project_name: Optional[str] = None


class UpdateBaseRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scope: Optional[Literal["global", "project"]] = None
    project_name: Optional[str] = None


class UpdateBaseModelRequest(BaseModel):
    embedding_model: Optional[Dict[str, Any]] = None
    reranker_model: Optional[Dict[str, Any]] = None


class CreateItemRequest(BaseModel):
    type: Literal["file", "note", "url", "sitemap", "directory"]
    content: Any
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateItemRequest(BaseModel):
    content: Optional[Any] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    min_score: float = 0.0


class QueryContextRequest(BaseModel):
    query: str
    top_k: int = 3
    max_chars: int = 1500


class QueryContextForTaskRequest(BaseModel):
    """v5.3.0: 多 KB 任务级注入"""
    query: str
    base_ids: Optional[List[str]] = None
    project_name: Optional[str] = None
    top_k: int = 3
    max_chars: int = 4000


# ===== 知识库管理端点 =====

@router.get("/bases")
async def list_bases(
    include_task: bool = False,
    scope: Optional[Literal["global", "project"]] = Query(
        None, description="v5.3.0: 按 scope 过滤（None = 全部）"
    ),
    project_name: Optional[str] = Query(
        None, description="v5.3.0: scope='project' 时按项目过滤"
    ),
):
    """列出所有知识库（v5.3.0: 支持 scope 过滤）。"""
    km = get_knowledge_manager()
    bases = km.list_bases(scope=scope, project_name=project_name)
    if not include_task:
        bases = [b for b in bases if not b.get("name", "").startswith("task_kb_")]
    return {"bases": bases}


@router.post("/bases")
async def create_base(req: CreateBaseRequest):
    """创建新知识库（v5.3.0: 支持 scope / project_name）"""
    km = get_knowledge_manager()
    try:
        base = km.create_base(
            name=req.name,
            description=req.description,
            scope=req.scope,
            project_name=req.project_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "base": base.model_dump()}


@router.get("/bases/{base_id}")
async def get_base(base_id: str):
    """获取知识库详情"""
    km = get_knowledge_manager()
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")
    return base.model_dump()


@router.put("/bases/{base_id}")
async def update_base(base_id: str, req: UpdateBaseRequest):
    """更新知识库"""
    km = get_knowledge_manager()
    if req.name is not None:
        km.rename_base(base_id, req.name)
    if req.description is not None:
        km.update_base(base_id, description=req.description)
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")
    return {"success": True, "base": base.model_dump()}


@router.delete("/bases/{base_id}")
async def delete_base(base_id: str):
    """删除知识库"""
    km = get_knowledge_manager()
    if not km.delete_base(base_id):
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")
    return {"success": True, "message": f"知识库 {base_id} 已删除"}


@router.put("/bases/{base_id}/models")
async def update_base_models(base_id: str, req: UpdateBaseModelRequest):
    """更新知识库的嵌入模型和重排模型配置"""
    km = get_knowledge_manager()
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")

    if req.embedding_model is not None:
        base.embedding_model = req.embedding_model
    if req.reranker_model is not None:
        base.reranker_model = req.reranker_model
    base.updated_at = int(__import__("time").time() * 1000)

    # 清除缓存的 KnowledgeBase 实例，下次查询时重新初始化
    if base_id in km._kb_instances:
        del km._kb_instances[base_id]

    km._persist_base(base)
    km._persist_index()
    return {"success": True, "base": base.model_dump()}


# ===== 条目管理端点 =====

@router.get("/bases/{base_id}/items")
async def list_items(base_id: str, type: Optional[str] = Query(None)):
    """列出知识库条目"""
    km = get_knowledge_manager()
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")
    items = km.get_items(base_id, item_type=type)
    return {"items": [item.model_dump() for item in items], "total": len(items)}


@router.post("/bases/{base_id}/items")
async def add_item(base_id: str, req: CreateItemRequest):
    """添加条目到知识库"""
    km = get_knowledge_manager()
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")

    # 处理 content
    content = req.content
    if req.type == "file" and isinstance(content, dict):
        content = FileMetadata(**content)

    item = KnowledgeItem(
        id="",
        type=req.type,
        content=content,
        source=req.source,
        metadata=req.metadata,
        processingStatus="completed",
    )
    item_id = km.add_item(base_id, item)
    return {"success": True, "item_id": item_id}


@router.delete("/bases/{base_id}/items/{item_id}")
async def remove_item(base_id: str, item_id: str):
    """删除知识库条目"""
    km = get_knowledge_manager()
    if not km.remove_item(base_id, item_id):
        raise HTTPException(status_code=404, detail="条目不存在")
    return {"success": True, "message": "条目已删除"}


@router.put("/bases/{base_id}/items/{item_id}")
async def update_item(
    base_id: str,
    item_id: str,
    req: UpdateItemRequest,
):
    """更新知识库条目（note/url/sitemap/directory）。

    file 类型请使用 `/bases/{base_id}/items/{item_id}/file` 端点替换文件。
    """
    km = get_knowledge_manager()
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")

    item = next((i for i in base.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="条目不存在")

    if item.type == "file":
        raise HTTPException(status_code=400, detail="file 类型条目请通过 /items/{item_id}/file 上传文件替换")

    ok = km.update_item(
        base_id,
        item_id,
        content=req.content,
        source=req.source,
        metadata=req.metadata,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="更新条目失败")

    return {"success": True, "item_id": item_id}


@router.put("/bases/{base_id}/items/{item_id}/file")
async def replace_file(
    base_id: str,
    item_id: str,
    file: UploadFile = File(...),
    chunk_size: int = Query(500, description="分块大小(字符数)"),
    overlap: int = Query(50, description="重叠字符数"),
):
    """替换知识库中的文件条目"""
    km = get_knowledge_manager()
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")

    item = next((i for i in base.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="条目不存在")
    if item.type != "file":
        raise HTTPException(status_code=400, detail="只能向 file 类型条目上传新文件")

    filename = file.filename or "uploaded_file"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持 {ext} 格式，仅支持: {', '.join(ALLOWED_UPLOAD_EXTENSIONS)}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")

    save_path = km.save_file(filename, content)

    text = ""
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        text = ""
    chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    fmeta = FileMetadata(
        name=save_path.name,
        size=save_path.stat().st_size,
        ext=ext,
        path=str(save_path),
    )

    metadata = {
        "original_filename": filename,
        "total_chars": len(text),
        "chunks": len(chunks),
        "chunk_size": chunk_size,
        "extracted_text": text[:50000],
    }

    ok = km.update_item(
        base_id,
        item_id,
        content=fmeta,
        source=f"file:{save_path.name}",
        metadata=metadata,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="更新条目失败")

    return {
        "success": True,
        "item_id": item_id,
        "filename": save_path.name,
        "total_chars": len(text),
        "chunks": len(chunks),
    }


@router.get("/bases/{base_id}/items/{item_id}/download")
async def download_item(base_id: str, item_id: str):
    """下载知识库中的文件条目"""
    km = get_knowledge_manager()
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")

    item = next((i for i in base.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="条目不存在")
    if item.type != "file" or not isinstance(item.content, FileMetadata):
        raise HTTPException(status_code=400, detail="只有文件条目支持下载")

    file_path = Path(item.content.path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        path=file_path,
        filename=item.content.name,
        media_type="application/octet-stream",
    )


# ===== 搜索与查询端点 =====

@router.post("/bases/{base_id}/search")
async def search_base(base_id: str, req: SearchRequest):
    """在知识库中搜索"""
    km = get_knowledge_manager()
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")
    results = km.search(base_id, req.query, top_k=req.top_k, min_score=req.min_score)
    return {"query": req.query, "results": results, "total": len(results)}


@router.post("/bases/{base_id}/query-context")
async def query_context(base_id: str, req: QueryContextRequest):
    """查询知识库并返回格式化上下文"""
    km = get_knowledge_manager()
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")
    context = km.query_context(
        base_id, req.query, top_k=req.top_k, max_chars=req.max_chars
    )
    return {"query": req.query, "context": context, "has_context": bool(context)}


@router.post("/query-context-for-task")
async def query_context_for_task(req: QueryContextForTaskRequest):
    """v5.3.0: 多 KB 任务级注入。

    base_ids 给定时只查这些；否则自动选当前任务 project 私有 + 全部全局。
    """
    km = get_knowledge_manager()
    context = km.query_context_for_task(
        task_project_name=req.project_name,
        base_ids=req.base_ids,
        query=req.query,
        top_k=req.top_k,
        max_chars=req.max_chars,
    )
    bases = km._resolve_task_bases(req.project_name, req.base_ids)
    return {
        "query": req.query,
        "context": context,
        "has_context": bool(context),
        "used_bases": [
            {
                "id": b.id,
                "name": b.name,
                "scope": getattr(b, "scope", "global"),
                "project_name": getattr(b, "project_name", None),
            }
            for b in bases
        ],
    }


# ===== 文件上传端点 =====

ALLOWED_UPLOAD_EXTENSIONS = {
    ".md",
    ".txt",
    ".markdown",
    ".rst",
    ".tex",
    ".json",
    ".csv",
    ".pdf",
    ".docx",
    ".doc",
}


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """将长文本切分为重叠的块"""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = max(
                text.rfind("\n", start, end),
                text.rfind(". ", start, end),
                text.rfind("。", start, end),
            )
            if boundary > start + chunk_size // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end < len(text) else end
    return chunks


@router.post("/upload")
async def upload_knowledge_file(
    file: UploadFile = File(...),
    base_id: str = Query(..., description="目标知识库ID"),
    chunk_size: int = Query(500, description="分块大小(字符数)"),
    overlap: int = Query(50, description="重叠字符数"),
):
    """上传文件到指定知识库"""
    km = get_knowledge_manager()
    base = km.get_base(base_id)
    if not base:
        raise HTTPException(status_code=404, detail=f"知识库不存在: {base_id}")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持 {ext} 格式，仅支持: {', '.join(ALLOWED_UPLOAD_EXTENSIONS)}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")

    # 保存文件
    save_path = km.save_file(file.filename or "uploaded_file", content)

    # 提取文本
    text = ""
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        text = ""

    # 分块
    chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    # 创建 KnowledgeItem
    fmeta = FileMetadata(
        name=save_path.name,
        size=save_path.stat().st_size,
        ext=ext,
        path=str(save_path),
    )

    item = KnowledgeItem(
        id="",
        type="file",
        content=fmeta,
        source=f"file:{save_path.name}",
        metadata={
            "original_filename": file.filename,
            "total_chars": len(text),
            "chunks": len(chunks),
            "chunk_size": chunk_size,
            "extracted_text": text[:50000],  # 限制存储大小
        },
        processingStatus="completed",
    )

    item_id = km.add_item(base_id, item)

    logger.info(f"[Knowledge] 上传文件到 {base.name}: {save_path.name} ({len(chunks)} chunks)")
    return {
        "success": True,
        "item_id": item_id,
        "filename": save_path.name,
        "total_chars": len(text),
        "chunks": len(chunks),
    }
