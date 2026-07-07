"""PDF 解析路由"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from ..core.security import MAX_UPLOAD_SIZE, sanitize_filename
from ..schemas.pdf import (
    PdfDownloadRequest,
    PdfParseRequest,
    PdfParseResult,
    PdfUploadResponse,
)
from ..services.pdf_processing import get_pdf_service, pdf_parser_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pdf", tags=["PDF 解析"])


from ..core.paths import _PROJECT_ROOT


@router.post("/upload", response_model=PdfUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    project_name: str = Query(None),
):
    """上传 PDF 文件"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)}MB",
        )

    safe_name = sanitize_filename(file.filename)
    try:
        info = await get_pdf_service().upload_pdf(file_bytes, safe_name, project_name)
        file_path = get_pdf_service().get_file_path(info.file_id, project_name)
        if file_path:
            try:
                rel_path = str(file_path.relative_to(_PROJECT_ROOT))
            except ValueError:
                rel_path = str(file_path)
        else:
            rel_path = ""
        return PdfUploadResponse(
            success=True,
            file_id=info.file_id,
            filename=info.filename,
            size=info.size,
            path=rel_path,
        )
    except Exception as e:
        logger.error(f"PDF 上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {e}")


@router.post("/download", response_model=Dict[str, Any])
async def download_pdf(body: PdfDownloadRequest):
    """从 URL 下载 PDF（支持 arXiv 摘要页自动转 PDF）"""
    try:
        info = await get_pdf_service().download_pdf(
            url=body.url,
            filename=body.filename,
            project_name=body.project_name,
        )
        return {
            "success": True,
            "file_id": info.file_id,
            "filename": info.filename,
            "size": info.size,
            "pages": info.pages,
            "source": info.source.value,
            "url": body.url,
        }
    except Exception as e:
        logger.error(f"PDF 下载失败: {e}")
        raise HTTPException(status_code=500, detail=f"下载失败: {e}")


@router.get("/files")
async def list_pdf_files(project_name: str = Query(None)):
    """列出已上传/下载的 PDF 文件"""
    files = get_pdf_service().list_files(project_name)
    return {
        "files": [f.model_dump() for f in files],
        "total": len(files),
    }


@router.post("/parse", response_model=PdfParseResult)
async def parse_pdf(body: PdfParseRequest, project_name: str = Query(None)):
    """解析 PDF"""
    options: Dict[str, Any] = {}
    if body.use_vision:
        options["use_vision"] = True
        options["vision_provider"] = body.vision_provider
        options["vision_max_pages"] = body.vision_max_pages

    try:
        result = await get_pdf_service().parse(
            file_id=body.file_id,
            strategy=body.strategy.value,
            pages=body.pages,
            project_name=project_name,
            options=options,
        )
        return result
    except Exception as e:
        logger.error(f"PDF 解析失败: {e}")
        raise HTTPException(status_code=500, detail=f"解析失败: {e}")


@router.get("/strategies")
async def list_strategies():
    """列出可用解析策略"""
    return {
        "strategies": pdf_parser_registry.list(),
    }


@router.delete("/files/{file_id}")
async def delete_pdf(file_id: str, project_name: str = Query(None)):
    """删除 PDF 文件"""
    success = get_pdf_service().delete_file(file_id, project_name)
    if not success:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"success": True, "deleted": file_id}


@router.get("/files/{file_id}/download")
async def get_pdf_download_url(file_id: str, project_name: str = Query(None)):
    """获取 PDF 本地路径（调试用）"""
    path = get_pdf_service().get_file_path(file_id, project_name)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        rel_path = str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        rel_path = str(path)
    return {"file_id": file_id, "path": rel_path, "size": path.stat().st_size}
