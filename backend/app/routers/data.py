"""数据路由 - 文件上传和分析API"""
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, File, UploadFile, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["数据管理"])

from ..core.paths import get_data_dir

DATA_DIR: Path = get_data_dir()  # 使用统一的路径管理

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".txt", ".tsv", ".parquet", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf"}


def get_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def allowed(filename: str) -> bool:
    return get_extension(filename) in ALLOWED_EXTENSIONS


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), task_id: str = Query(None)):
    """上传数据文件"""
    if not allowed(file.filename or ""):
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {get_extension(file.filename or '')}")

    file_id = uuid4().hex[:8]
    ext = get_extension(file.filename or "")
    save_name = f"{file_id}_{file.filename or 'file'}{ext}"
    save_path = DATA_DIR / save_name

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    size = save_path.stat().st_size
    result = {"success": True, "file_id": file_id, "name": save_name, "size": size, "path": str(save_path)}

    # 如果是数据文件，做初步分析
    if ext in {".csv", ".xlsx", ".xls", ".json"}:
        try:
            from ..agents.data_agent import DataAgent
            agent = DataAgent(data_dir=str(DATA_DIR))
            analysis = agent.analyze_file(str(save_path))
            result.update(analysis)
        except Exception as e:
            logger.warning(f"Auto-analysis failed: {e}")

    logger.info(f"Uploaded: {save_name} ({size} bytes)")
    return result


@router.get("/files", response_model=None)
async def list_files() -> list:
    """列出所有已上传文件"""
    files: list = []
    for f in DATA_DIR.iterdir():
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "type": f.suffix,
                "modified": f.stat().st_mtime,
            })
    return files


@router.get("/analyze")
async def analyze_file(dataset_name: str = Query(...)):
    """分析数据文件"""
    file_path = DATA_DIR / dataset_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {dataset_name}")

    try:
        from ..agents.data_agent import DataAgent
        agent = DataAgent(data_dir=str(DATA_DIR))
        return agent.analyze_file(str(file_path))
    except Exception as e:
        return {"error": str(e)}


@router.delete("/files/{filename}")
async def delete_file(filename: str):
    """删除文件"""
    file_path = DATA_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"success": True, "deleted": filename}
