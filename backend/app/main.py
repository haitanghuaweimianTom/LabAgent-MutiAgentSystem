"""数学建模多Agent系统 - FastAPI入口"""
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from .config import get_settings
from .routers import tasks_router, agents_router, data_router, workflows_router
from .routers.mcp import router as mcp_router
from .core.runtime_config import (
    get_runtime_api_key, update_runtime_api_key, is_api_key_set,
    get_runtime_kimi_key, get_runtime_kimi_url,
    update_runtime_kimi_key, update_runtime_kimi_url, is_kimi_key_set,
)
from .routers.tasks import reset_orchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SettingsUpdate(BaseModel):
    minimax_api_key: str | None = None
    kimi_api_key: str | None = None
    kimi_base_url: str | None = None
    default_model: str | None = None
    # Multi-provider settings
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None
    anthropic_model: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    default_llm_provider: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("数学建模多Agent系统 启动中...")
    # 确保所有必要目录存在
    from .core.paths import ensure_dirs
    ensure_dirs()
    try:
        from .core.task_persistence import list_all_tasks
        tasks = list_all_tasks()
        logger.info(f"从磁盘恢复 {len(tasks)} 个历史任务")
    except Exception as e:
        logger.warning(f"恢复历史任务失败: {e}")
    yield
    logger.info("系统关闭...")


app = FastAPI(title="数学建模多Agent系统", version="3.0.0", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(data_router, prefix="/api/v1")
app.include_router(workflows_router, prefix="/api/v1")
app.include_router(mcp_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"name": "数学建模多Agent系统", "version": "3.0.0", "status": "running", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/v1/info")
async def info():
    from .core.chat_room import list_chat_rooms
    s = get_settings()
    # 检测 Claude Code CLI 是否可用
    from .agents.base import _find_claude_code
    claude_code_path = _find_claude_code()
    return {
        "app_name": s.app_name,
        "version": s.app_version,
        "default_model": s.default_model,
        "api_base_url": s.api_base_url,
        "team_size": 7,
        "active_chat_rooms": list_chat_rooms(),
        # Claude Code 集成状态
        "claude_code_available": claude_code_path is not None,
        "claude_code_path": claude_code_path or "",
        "claude_model": s.claude_model,
        "claude_mcp_tools": s.claude_mcp_tools,
        "claude_mcp_config_path": s.claude_mcp_config_path,
        "default_llm_backend": s.default_llm_backend,
    }


@app.get("/api/v1/settings")
async def get_runtime_settings():
    s = get_settings()
    return {
        "minimax_api_key_set": is_api_key_set(),
        "kimi_api_key_set": is_kimi_key_set(),
        "kimi_base_url": get_runtime_kimi_url(),
        "default_model": s.default_model,
        "api_base_url": s.api_base_url,
        # Multi-provider
        "providers": {
            "anthropic": {
                "api_key_set": bool(s.anthropic_api_key),
                "base_url": s.anthropic_base_url or "https://api.anthropic.com",
                "model": s.anthropic_model,
            },
            "openai": {
                "api_key_set": bool(s.openai_api_key),
                "base_url": s.openai_base_url,
                "model": s.openai_model,
            },
            "gemini": {
                "api_key_set": bool(s.gemini_api_key),
                "model": s.gemini_model,
            },
            "ollama": {
                "base_url": s.ollama_base_url,
                "model": s.ollama_model,
            },
            "claude_cli": {
                "available": _find_claude_code() is not None,
                "model": s.claude_model,
            },
        },
        "default_llm_provider": s.default_llm_provider,
    }

from .agents.base import _find_claude_code

@app.post("/api/v1/settings")
async def update_runtime_settings(body: SettingsUpdate):
    changed = False
    if body.minimax_api_key is not None:
        update_runtime_api_key(body.minimax_api_key.strip())
        logger.info("MiniMax API密钥已更新")
        changed = True
    if body.kimi_api_key is not None:
        update_runtime_kimi_key(body.kimi_api_key.strip())
        logger.info("Kimi API密钥已更新")
        changed = True
    if body.kimi_base_url is not None:
        update_runtime_kimi_url(body.kimi_base_url.strip())
        logger.info(f"Kimi Base URL已更新: {body.kimi_base_url}")
        changed = True
    # Multi-provider updates
    s = get_settings()
    if body.anthropic_api_key is not None:
        s.anthropic_api_key = body.anthropic_api_key.strip()
        changed = True
    if body.anthropic_base_url is not None:
        s.anthropic_base_url = body.anthropic_base_url.strip()
        changed = True
    if body.anthropic_model is not None:
        s.anthropic_model = body.anthropic_model.strip()
        changed = True
    if body.openai_api_key is not None:
        s.openai_api_key = body.openai_api_key.strip()
        changed = True
    if body.openai_base_url is not None:
        s.openai_base_url = body.openai_base_url.strip()
        changed = True
    if body.openai_model is not None:
        s.openai_model = body.openai_model.strip()
        changed = True
    if body.gemini_api_key is not None:
        s.gemini_api_key = body.gemini_api_key.strip()
        changed = True
    if body.gemini_model is not None:
        s.gemini_model = body.gemini_model.strip()
        changed = True
    if body.ollama_base_url is not None:
        s.ollama_base_url = body.ollama_base_url.strip()
        changed = True
    if body.ollama_model is not None:
        s.ollama_model = body.ollama_model.strip()
        changed = True
    if body.default_llm_provider is not None:
        s.default_llm_provider = body.default_llm_provider.strip()
        changed = True
    if changed:
        reset_orchestrator()
    if body.default_model is not None:
        logger.info(f"默认模型已更新为: {body.default_model}")
    return {"success": True, "message": "设置已保存" + ("，Agent已重新初始化" if changed else "")}


@app.get("/api/v1/debug/key")
async def debug_api_key():
    """调试接口：查看当前API密钥状态"""
    from .core.runtime_config import ENV_FILE
    key = get_runtime_api_key()
    return {
        "env_file_path": str(ENV_FILE),
        "env_file_exists": ENV_FILE.exists(),
        "key_length": len(key),
        "key_prefix": key[:15] + "..." if key else "EMPTY",
        "is_set": is_api_key_set(),
        "env_content_preview": ENV_FILE.read_text("utf-8")[:300] if ENV_FILE.exists() else "NOT FOUND",
    }


@app.post("/api/v1/debug/test-llm")
async def debug_test_llm():
    """调试接口：测试LLM调用"""
    import httpx
    import json

    key = get_runtime_api_key()
    s = get_settings()

    if not key:
        return {"error": "API key is empty"}

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": s.default_model,
        "messages": [{"role": "user", "content": "说'你好'，只说这两个字"}],
        "temperature": 0.7,
        "max_tokens": 50,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{s.api_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            result = json.loads(response.text)
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"success": True, "response": content}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text[:500]}
    except Exception as e:
        return {"error": str(e)}


@app.exception_handler(Exception)
async def handle_error(request, exc):
    logger.error(f"Error: {exc}")
    return JSONResponse(status_code=500, content={"error": str(exc)})
