"""数据路由 - 文件上传和分析API"""
import base64
import io
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, File, UploadFile, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["数据管理"])

from ..core.paths import get_data_dir, get_project_data_dir

DATA_DIR: Path = get_data_dir()  # 全局默认目录

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".txt", ".tsv", ".parquet", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf"}


def get_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def allowed(filename: str) -> bool:
    return get_extension(filename) in ALLOWED_EXTENSIONS


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    task_id: str = Query(None),
    project_name: str = Query(None),
):
    """上传数据文件（支持项目隔离）"""
    if not allowed(file.filename or ""):
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {get_extension(file.filename or '')}")

    target_dir = get_project_data_dir(project_name)
    file_id = uuid4().hex[:8]
    ext = get_extension(file.filename or "")
    save_name = f"{file_id}_{file.filename or 'file'}{ext}"
    save_path = target_dir / save_name

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    size = save_path.stat().st_size
    # 返回相对路径，避免绑定本机绝对路径
    from ..core.paths import _PROJECT_ROOT
    try:
        rel_path = str(save_path.relative_to(_PROJECT_ROOT))
    except ValueError:
        rel_path = str(save_path)
    result = {"success": True, "file_id": file_id, "name": save_name, "size": size, "path": rel_path}

    # 如果是数据文件，做初步分析
    if ext in {".csv", ".xlsx", ".xls", ".json"}:
        try:
            from ..agents.data_agent import DataAgent
            agent = DataAgent(data_dir=str(target_dir))
            analysis = agent.analyze_file(str(save_path))
            result.update(analysis)
        except Exception as e:
            logger.warning(f"Auto-analysis failed: {e}")

    logger.info(f"Uploaded{' to project ' + project_name if project_name else ''}: {save_name} ({size} bytes)")
    return result


@router.get("/files", response_model=None)
async def list_files(project_name: str = Query(None)) -> list:
    """列出已上传文件（支持项目隔离）"""
    target_dir = get_project_data_dir(project_name)
    files: list = []
    for f in target_dir.iterdir():
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "type": f.suffix,
                "modified": f.stat().st_mtime,
            })
    return files


@router.get("/analyze")
async def analyze_file(
    dataset_name: str = Query(...),
    project_name: str = Query(None),
):
    """分析数据文件（支持项目隔离）"""
    target_dir = get_project_data_dir(project_name)
    file_path = target_dir / dataset_name
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
):
    """删除文件（支持项目隔离）"""
    target_dir = get_project_data_dir(project_name)
    file_path = target_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"success": True, "deleted": filename}


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


def _build_vision_messages(base64_image: str, prompt: str, api_format: str) -> List[Dict[str, Any]]:
    """根据 API 格式构建多模态消息"""
    if api_format == "anthropic":
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64_image,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]
    else:
        # OpenAI / Gemini / Ollama 兼容格式
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

    # 确定 API 格式以选择正确的 vision message 格式
    api_format = agent._get_api_format()

    # 严格控制幻觉：只输出图片中实际可见的内容，不补充。
    prompt = (
        "请提取这张图片中的所有文本内容，"
        "只输出图片中实际出现的文字、公式、表格与图表说明，"
        "不要补充任何图片里没有的信息。"
        "如果属于数学建模/科研/工程类题目，完整保留题目描述、公式、表格和附件说明。"
        "保持原有排版格式，不要遗漏任何信息。"
    )
    messages = _build_vision_messages(base64_image, prompt, api_format)

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
