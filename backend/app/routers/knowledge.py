"""知识库 RESTful API

提供知识库 CRUD、查询和统计端点。
使用 src/knowledge.KnowledgeBase 作为后端。
"""
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["知识库"])

# 延迟导入 KnowledgeBase，避免启动时加载嵌入模型
_kb_instance: Optional[Any] = None


def _get_kb() -> Any:
    """懒加载 KnowledgeBase 单例"""
    global _kb_instance
    if _kb_instance is None:
        project_root = Path(__file__).parent.parent.parent.parent
        src_path = str(project_root)
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        from src.knowledge import KnowledgeBase, TfidfEmbedding
        # 使用 TF-IDF 避免模型下载慢/挂起问题
        _kb_instance = KnowledgeBase(name="math_modeling", embedding_model=TfidfEmbedding(max_features=2000))
        # 尝试加载已保存的知识库
        kb_file = project_root / "data" / "knowledge_base.json"
        if kb_file.exists():
            try:
                _kb_instance.load(str(kb_file))
            except Exception as e:
                logger.warning(f"加载知识库文件失败: {e}")
    return _kb_instance


class DocumentCreate(BaseModel):
    title: str
    content: str
    source: Optional[str] = None
    metadata: Dict[str, Any] = {}


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    min_score: float = 0.0
    max_chars: int = 2000


class SaveRequest(BaseModel):
    filepath: Optional[str] = None


@router.get("/")
async def list_knowledge():
    """列出所有文档"""
    kb = _get_kb()
    return {
        "name": kb.name,
        "documents": kb.list_documents(),
        "total": len(kb),
    }


@router.post("/documents")
async def add_document(doc: DocumentCreate):
    """添加文档到知识库"""
    kb = _get_kb()
    try:
        doc_id = kb.add_document(
            title=doc.title,
            content=doc.content,
            source=doc.source,
            metadata=doc.metadata,
        )
        return {
            "success": True,
            "doc_id": doc_id,
            "message": f"Document '{doc.title}' added",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """获取文档详情"""
    kb = _get_kb()
    kb_docs = getattr(kb, "_documents", {})
    if doc_id not in kb_docs:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    doc = kb_docs[doc_id]
    return {
        "id": doc.id,
        "title": doc.title,
        "content": doc.content,
        "source": doc.source,
        "metadata": doc.metadata,
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """删除文档"""
    kb = _get_kb()
    if not kb.remove_document(doc_id):
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return {"success": True, "message": f"Document '{doc_id}' removed"}


@router.post("/query")
async def query_knowledge(req: QueryRequest):
    """搜索知识库"""
    kb = _get_kb()
    results = kb.query(req.query, top_k=req.top_k, min_score=req.min_score)
    return {
        "query": req.query,
        "results": [
            {
                "id": doc.id,
                "title": doc.title,
                "content": doc.content,
                "source": doc.source,
                "score": round(score, 4),
            }
            for doc, score in results
        ],
        "total": len(results),
    }


@router.post("/query/context")
async def query_with_context(req: QueryRequest):
    """查询并返回格式化上下文文本（用于注入 Agent 提示词）"""
    kb = _get_kb()
    context = kb.query_with_context(
        req.query,
        top_k=req.top_k,
        min_score=req.min_score,
        max_chars=req.max_chars,
    )
    return {
        "query": req.query,
        "context": context,
        "has_context": bool(context),
    }


@router.get("/stats")
async def knowledge_stats():
    """知识库统计信息"""
    kb = _get_kb()
    kb_docs = getattr(kb, "_documents", {})
    total_chunks = len(kb.vector_store) if hasattr(kb, "vector_store") else 0
    sources = set()
    for doc in kb_docs.values():
        if doc.source:
            sources.add(doc.source)
    return {
        "name": kb.name,
        "total_documents": len(kb),
        "total_chunks": total_chunks,
        "sources": sorted(sources),
    }


@router.post("/save")
async def save_knowledge(req: SaveRequest = SaveRequest()):
    """保存知识库到磁盘"""
    kb = _get_kb()
    filepath = req.filepath or str(
        Path(__file__).parent.parent.parent.parent / "data" / "knowledge_base.json"
    )
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    kb.save(filepath)
    return {"success": True, "filepath": filepath}


@router.post("/load")
async def load_knowledge(req: SaveRequest = SaveRequest()):
    """从磁盘加载知识库"""
    global _kb_instance
    filepath = req.filepath or str(
        Path(__file__).parent.parent.parent.parent / "data" / "knowledge_base.json"
    )
    if not Path(filepath).exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filepath}")
    kb = _get_kb()
    kb.load(filepath)
    return {"success": True, "filepath": filepath, "documents": len(kb)}


@router.post("/clear")
async def clear_knowledge():
    """清空知识库"""
    kb = _get_kb()
    kb.clear()
    return {"success": True, "message": "Knowledge base cleared"}
