"""数据路由 - 文件上传和分析API"""
import base64
import io
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, File, UploadFile, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["数据管理"])

from ..core.paths import get_data_dir, get_project_data_dir, get_project_data_subdir
from ..core.security import MAX_UPLOAD_SIZE, sanitize_filename, validate_path_within
from ..services.data_directory import list_project_files

DATA_DIR: Path = get_data_dir()  # 全局默认目录

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".txt", ".tsv", ".parquet", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf"}

# v5.3.0: 数据来源
DataSource = Literal["user_upload", "self_collected"]


def get_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def allowed(filename: str) -> bool:
    return get_extension(filename) in ALLOWED_EXTENSIONS


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    task_id: str = Query(None),
    project_name: str = Query(None),
    source: DataSource = Query("user_upload", description="数据来源：user_upload（默认）或 self_collected"),
):
    """上传数据文件（支持项目隔离 + source 拆分）。

    向后兼容：source 缺省 = 'user_upload'，与旧版行为一致（直接落到 data/ 根目录）。
    旧版客户端零改动。

    v5.3.0：传入 source='self_collected' 时文件落到 outputs/<name>/data/self_collected/。
    """
    if not allowed(file.filename or ""):
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {get_extension(file.filename or '')}")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)}MB",
        )

    safe_name = sanitize_filename(file.filename or "unnamed")
    target_dir = get_project_data_subdir(project_name, source=source)
    file_id = uuid4().hex[:8]
    ext = get_extension(safe_name)
    save_name = f"{file_id}_{safe_name}{ext}"
    save_path = target_dir / save_name

    with open(save_path, "wb") as buffer:
        buffer.write(file_bytes)

    size = save_path.stat().st_size
    # 返回相对路径，避免绑定本机绝对路径
    from ..core.paths import _PROJECT_ROOT
    try:
        rel_path = str(save_path.relative_to(_PROJECT_ROOT))
    except ValueError:
        rel_path = str(save_path)
    result = {"success": True, "file_id": file_id, "name": save_name, "size": size, "path": rel_path, "source": source}

    # 如果是数据文件，做初步分析（仅 user_upload 触发）
    if source == "user_upload" and ext in {".csv", ".xlsx", ".xls", ".json"}:
        try:
            from ..agents.data_agent import DataAgent
            agent = DataAgent(data_dir=str(target_dir))
            analysis = agent.analyze_file(str(save_path))
            result.update(analysis)
        except Exception as e:
            logger.warning(f"Auto-analysis failed: {e}")

    logger.info(
        f"Uploaded{' to project ' + project_name if project_name else ''} "
        f"(source={source}): {save_name} ({size} bytes)"
    )
    return result


@router.get("/files", response_model=None)
async def list_files(
    project_name: str = Query(None),
    source: Literal["user_upload", "self_collected", "both"] = Query(
        "both", description="数据来源过滤"
    ),
) -> list:
    """列出已上传文件（支持项目隔离 + source 拆分）。

    v5.3.0：
    - source='user_upload' → 只列 user_upload/
    - source='self_collected' → 只列 self_collected/
    - source='both'（默认） → 合并返回，每项带 source 字段
    """
    if source == "both":
        return list_project_files(project_name, source="both")

    target_dir = get_project_data_subdir(project_name, source=source)
    files: list = []
    for f in target_dir.iterdir():
        if f.is_file() and not f.name.startswith("."):
            if f.name == "_index.json":
                continue
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "type": f.suffix,
                "modified": int(f.stat().st_mtime * 1000),
                "source": source,
            })
    return files


@router.get("/self-collected")
async def list_self_collected_files(project_name: str = Query(None)) -> Dict[str, Any]:
    """列出 self_collected 目录的文件 + 元数据索引。"""
    from ..services.data_directory import read_self_collected_index
    items = list_project_files(project_name, source="self_collected")
    index = read_self_collected_index(project_name)
    return {"files": items, "index": index, "total": len(items)}


@router.post("/self-collect/trigger")
async def trigger_self_collect(
    plan: Dict[str, Any],
    project_name: str = Query(None),
    concurrency: int = Query(4, ge=1, le=16),
    max_size_mb: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    """手动触发自收集：传入 {"urls": [...], "query": "..."} → 异步下载。"""
    from ..services.self_collector import collect_urls

    urls = plan.get("urls") or []
    query = plan.get("query", "") or ""
    if not isinstance(urls, list):
        raise HTTPException(status_code=400, detail="urls must be a list")
    if not urls:
        raise HTTPException(status_code=400, detail="urls is empty")
    urls = [u for u in urls if isinstance(u, str) and u]

    results = await collect_urls(
        urls,
        project_name=project_name,
        source_query=query,
        concurrency=concurrency,
        max_size_mb=max_size_mb,
    )
    succeeded = sum(1 for r in results if r.filename)
    failed = [r for r in results if r.error]
    return {
        "success": True,
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(failed),
        "results": [
            {
                "url": r.url,
                "filename": r.filename,
                "size": r.size,
                "error": r.error,
                "http_status": r.http_status,
            }
            for r in results
        ],
    }


@router.get("/analyze")
async def analyze_file(
    dataset_name: str = Query(...),
    project_name: str = Query(None),
    source: DataSource = Query("user_upload", description="数据来源"),
):
    """分析数据文件（支持项目隔离 + source）"""
    target_dir = get_project_data_subdir(project_name, source=source)
    file_path = target_dir / dataset_name
    validate_path_within(file_path, target_dir)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {dataset_name}")

    try:
        from ..agents.data_agent import DataAgent
        agent = DataAgent(data_dir=str(target_dir))
        return agent.analyze_file(str(file_path))
    except Exception as e:
        return {"error": str(e)}


@router.delete("/files/{filename}")
async def delete_file(
    filename: str,
    project_name: str = Query(None),
    source: DataSource = Query("user_upload", description="数据来源"),
):
    """删除文件（支持项目隔离 + source）"""
    target_dir = get_project_data_subdir(project_name, source=source)
    file_path = target_dir / filename
    validate_path_within(file_path, target_dir)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"success": True, "deleted": filename, "source": source}


@router.delete("/output/{filename}")
async def delete_output_artifact(
    filename: str,
    project_name: str = Query(None, description="项目名，为空时用全局 output"),
):
    """删除 output 目录下的产出物（PDF、LaTeX、代码、图表等）"""
    from ..core.paths import get_project_output_dir, OUTPUT_DIR
    target_dir = get_project_output_dir(project_name) if project_name else OUTPUT_DIR
    file_path = target_dir / filename
    validate_path_within(file_path, target_dir)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Output artifact not found")
    file_path.unlink()
    logger.info(f"删除输出产物: {file_path}")
    return {"success": True, "deleted": filename, "project": project_name}


@router.delete("/output/{project_name}/directory")
async def delete_output_directory(project_name: str):
    """删除整个项目的 output 子目录（谨慎操作）"""
    import shutil
    from ..core.paths import _PROJECT_ROOT
    outputs_root = _PROJECT_ROOT / "outputs"
    target_dir = outputs_root / project_name / "output"
    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="Output directory not found")
    # 安全检查：不允许删除 _global
    if project_name == "_global":
        raise HTTPException(status_code=400, detail="Cannot delete global output directory")
    validate_path_within(target_dir, outputs_root)
    shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)  # 重建空目录
    logger.info(f"清空项目输出目录: {target_dir}")
    # 同步项目索引
    from ..core.project_persistence import sync_projects_with_outputs
    sync_projects_with_outputs()
    return {"success": True, "deleted": project_name}


# ===== OCR 接口（调用 LLM Vision 能力）=====

def _image_to_base64_png(image_bytes: bytes) -> str:
    """将图片字节转换为 base64 PNG 字符串"""
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _pdf_page_to_base64_png(pdf_bytes: bytes, page_number: int = 0) -> str:
    """将 PDF 指定页渲染为 base64 PNG 字符串"""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if page_number >= len(doc):
        page_number = 0
    page = doc.load_page(page_number)
    pix = page.get_pixmap(dpi=200)
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode("utf-8")


def _build_vision_messages(base64_image: str, prompt: str) -> List[Dict[str, Any]]:
    """统一使用 OpenAI 风格的多模态消息；由 provider adapter 内部再转换为原生格式。"""
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]


@router.post("/ocr")
async def ocr_upload(file: UploadFile = File(...), domain: str = "general"):
    """上传图片/PDF，调用 LLM Vision 提取文本。

    Phase 1E 整改：接受 ``domain`` 查询参数（math_modeling / research_paper / general），
    默认 ``general``。严格控制幻觉：只输出图片中实际出现的文字，不补充。
    旧调用方不传 domain 时行为与重构前完全等价。
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf"}:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)}MB",
        )

    # 转换为 base64 图片
    try:
        if ext == ".pdf":
            base64_image = _pdf_page_to_base64_png(file_bytes, page_number=0)
        else:
            base64_image = _image_to_base64_png(file_bytes)
    except Exception as e:
        logger.error(f"OCR 图片转换失败: {e}")
        raise HTTPException(status_code=400, detail=f"图片转换失败: {e}")

    # 创建临时 Agent 实例用于调用 LLM
    from ..agents.data_agent import DataAgent
    agent = DataAgent()

    # 严格控制幻觉：只输出图片中实际可见的内容，不补充。
    prompt = (
        "请提取这张图片中的所有文本内容，"
        "只输出图片中实际出现的文字、公式、表格与图表说明，"
        "不要补充任何图片里没有的信息。"
        "如果属于数学建模/科研/工程类题目，完整保留题目描述、公式、表格和附件说明。"
        "保持原有排版格式，不要遗漏任何信息。"
    )
    messages = _build_vision_messages(base64_image, prompt)

    try:
        response = await agent.call_llm(messages=messages, temperature=0.1)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content.strip():
            content = "未能识别到文本内容"
        return {
            "success": True,
            "filename": file.filename,
            "text": content,
            "model": agent.model,
            "provider": agent.provider_id,
        }
    except Exception as e:
        logger.error(f"OCR LLM 调用失败: {e}")
        raise HTTPException(status_code=500, detail=f"OCR 识别失败: {e}")
