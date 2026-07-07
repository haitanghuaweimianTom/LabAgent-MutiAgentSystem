"""数学建模多Agent系统 - FastAPI入口"""
import os
# 清除 SOCKS 代理环境变量（httpx 不支持 socks:// 协议）
for _var in ("ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
    _val = os.environ.get(_var, "")
    if _val and "socks" in _val.lower():
        del os.environ[_var]

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from .config import get_settings
from .routers import tasks_router, agents_router, data_router, workflows_router
from .routers.mcp import router as mcp_router
from .routers.environments import router as environments_router
from .core.runtime_config import (
    get_runtime_api_key, update_runtime_api_key, is_api_key_set,
    get_runtime_kimi_key, get_runtime_kimi_url,
    update_runtime_kimi_key, update_runtime_kimi_url, is_kimi_key_set,
    persist_provider_setting, persist_claude_setting,
)
from .routers.tasks import reset_orchestrator
from .routers.providers import router as providers_router
from .routers.knowledge import router as knowledge_router
from .routers.projects import router as projects_router
from .routers.memory import router as memory_router
from .routers.pdf import router as pdf_router
from .routers.discussion import router as discussion_router
from .core.provider_config import migrate_legacy_to_new, get_default_provider, list_custom_providers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 应用启动时间戳（用于计算运行时长）
_app_start_time: float = 0.0


# ---------------------------------------------------------------------------
# 可选 API Key 认证依赖
# ---------------------------------------------------------------------------
# 设置环境变量 MATHMODEL_API_KEY 即可启用认证；留空则所有端点免认证（本地开发模式）。
import os as _os

_REQUIRED_API_KEY = _os.environ.get("MATHMODEL_API_KEY", "")


async def require_api_key(x_api_key: str = Header(default="", alias="X-API-Key")):
    """FastAPI 依赖：校验 X-API-Key 请求头。

    - 若系统未配置 MATHMODEL_API_KEY（空字符串），则跳过校验（本地开发模式）。
    - 若已配置，则请求必须携带匹配的 X-API-Key 头。
    """
    if not _REQUIRED_API_KEY:
        return  # 未启用认证
    if x_api_key != _REQUIRED_API_KEY:
        raise HTTPException(status_code=401, detail="未授权：X-API-Key 无效或缺失")


class SettingsUpdate(BaseModel):
    api_key: str | None = None  # 通用 API 密钥（新增）
    minimax_api_key: str | None = None  # 兼容旧字段
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
    # Claude Code CLI settings
    claude_model: str | None = None
    claude_mcp_tools: str | None = None
    claude_mcp_config_path: str | None = None
    claude_temperature: float | None = None
    claude_max_tokens: int | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _app_start_time
    _app_start_time = time.time()
    logger.info("数学建模多Agent系统 启动中...")
    # 确保所有必要目录存在
    from .core.paths import ensure_dirs
    ensure_dirs()
    # v5.3.0: 迁移旧格式数据目录（outputs/<name>/data/*.csv → user_uploads/）
    try:
        from .core.paths import migrate_legacy_data_dir
        m_stats = migrate_legacy_data_dir(verbose=False)
        if m_stats["files_moved"] > 0:
            logger.info(
                f"v5.3.0 数据目录迁移: 扫描 {m_stats['projects_scanned']} 个项目, "
                f"移动 {m_stats['files_moved']} 个文件到 user_uploads/"
            )
    except Exception as mig_exc:
        logger.warning(f"v5.3.0 数据迁移失败（不影响启动）: {mig_exc}")
    # 迁移旧格式 provider 配置
    migrate_legacy_to_new()
    # 自动检测并同步 ccswitch Provider 配置
    try:
        from .core.provider_config import sync_ccswitch_to_local
        result = sync_ccswitch_to_local()
        if result["synced"] > 0:
            logger.info(f"ccswitch 同步完成: {result['added']} 新增, {result['updated']} 更新, 默认={result['default']}")
        else:
            logger.info("ccswitch: 未检测到可同步的 Provider")
    except Exception as e:
        logger.debug(f"ccswitch 同步跳过: {e}")
    try:
        from .core.provider_config import start_ccswitch_watcher
        start_ccswitch_watcher()
    except Exception as e:
        logger.debug(f"ccswitch watcher 启动跳过: {e}")
    try:
        from .core.task_persistence import list_all_tasks, mark_interrupted_tasks
        tasks = list_all_tasks()
        interrupted = mark_interrupted_tasks()
        logger.info(f"从磁盘恢复 {len(tasks)} 个历史任务（{interrupted} 个中断）")
    except Exception as e:
        logger.warning(f"恢复历史任务失败: {e}")
    yield
    try:
        from .core.provider_config import stop_ccswitch_watcher
        stop_ccswitch_watcher()
    except Exception as e:
        logger.debug(f"ccswitch watcher 停止跳过: {e}")
    logger.info("系统关闭...")


app = FastAPI(title="数学建模多Agent系统", version="3.0.0", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(data_router, prefix="/api/v1")
app.include_router(workflows_router, prefix="/api/v1")
app.include_router(mcp_router, prefix="/api/v1")
app.include_router(environments_router, prefix="/api/v1")
app.include_router(providers_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(pdf_router, prefix="/api/v1")
app.include_router(discussion_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"name": "数学建模多Agent系统", "version": "7.3.0", "status": "running", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/v1/info")
async def info():
    from . import agents  # noqa: F401 确保所有 agent 模块被加载并注册到 AgentFactory
    from .agents.base import _find_claude_code, AgentFactory
    from .core.task_persistence import list_all_tasks
    from .core.knowledge_manager import get_knowledge_manager
    s = get_settings()
    claude_code_path = _find_claude_code()
    default_p = get_default_provider()

    # 任务统计
    all_tasks = list_all_tasks()
    active_tasks = [t for t in all_tasks if t.get("status") in ("running", "in_progress")]

    # Provider 列表（脱敏）
    providers = []
    for p in list_custom_providers():
        has_key = bool(p.get("api_key"))
        has_host = bool(p.get("api_host"))
        providers.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "type": p.get("type"),
            "available": has_key and has_host,
            "model": next((m.get("name") for m in p.get("models", []) if m.get("enabled")), None),
        })

    # 知识库数量
    try:
        kb_count = len(get_knowledge_manager().list_bases())
    except Exception:
        kb_count = 0

    # ccswitch 状态
    try:
        from .core.provider_config import get_ccswitch_status
        ccswitch_status = get_ccswitch_status()
    except Exception:
        ccswitch_status = {"available": False, "error": "not_loaded"}

    # 记忆系统统计
    memory_stats = {}
    try:
        from .core.memory import get_memory_manager
        mm = get_memory_manager()
        lessons = mm.get_lessons()
        memory_stats = {
            "total_lessons": len(lessons.lessons),
            "by_category": {},
        }
        for l in lessons.lessons:
            cat = l.get("category", "unknown")
            memory_stats["by_category"][cat] = memory_stats["by_category"].get(cat, 0) + 1
    except Exception:
        pass

    # Agent 列表（含 Orchestrator）
    agent_list = []
    for name in AgentFactory.list_agents():
        cls = AgentFactory._registry[name]
        agent_list.append({
            "id": name,
            "label": getattr(cls, "label", name),
            "description": getattr(cls, "description", ""),
        })
    agent_list.append({
        "id": "orchestrator",
        "label": "编排器",
        "description": "管理两阶段多Agent工作流",
    })

    return {
        "app_name": s.app_name,
        "version": s.app_version,
        "started_at": _app_start_time,
        "default_model": s.default_model,
        "default_llm_backend": s.default_llm_backend,
        "default_provider": {
            "id": default_p.get("id") if default_p else None,
            "name": default_p.get("name") if default_p else None,
            "type": default_p.get("type") if default_p else None,
            "model": next((m.get("name") for m in default_p.get("models", []) if m.get("enabled")), None) if default_p else None,
        } if default_p else None,
        "agent_count": len(agent_list),
        "agents": agent_list,
        "knowledge_base_count": kb_count,
        "memory_stats": memory_stats,
        "total_tasks": len(all_tasks),
        "active_tasks": len(active_tasks),
        "providers": providers,
        "claude_code_available": claude_code_path is not None,
        "claude_code_path": claude_code_path or "",
        "ccswitch_status": get_ccswitch_status(),
    }


@app.get("/api/v1/settings")
async def get_runtime_settings():
    s = get_settings()
    return {
        "api_key_set": is_api_key_set(),
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

@app.post("/api/v1/settings", dependencies=[Depends(require_api_key)])
async def update_runtime_settings(body: SettingsUpdate):
    changed = False
    if body.minimax_api_key is not None:
        update_runtime_api_key(body.minimax_api_key.strip())
        logger.info("API密钥已更新（兼容旧字段 minimax_api_key）")
        changed = True
    if body.api_key is not None:
        update_runtime_api_key(body.api_key.strip())
        logger.info("API密钥已更新")
        changed = True
    if body.kimi_api_key is not None:
        update_runtime_kimi_key(body.kimi_api_key.strip())
        logger.info("Kimi API密钥已更新")
        changed = True
    if body.kimi_base_url is not None:
        update_runtime_kimi_url(body.kimi_base_url.strip())
        logger.info(f"Kimi Base URL已更新: {body.kimi_base_url}")
        changed = True
    # Multi-provider updates (also persist to .env)
    s = get_settings()
    if body.anthropic_api_key is not None:
        s.anthropic_api_key = body.anthropic_api_key.strip()
        persist_provider_setting("ANTHROPIC_API_KEY", body.anthropic_api_key.strip())
        changed = True
    if body.anthropic_base_url is not None:
        s.anthropic_base_url = body.anthropic_base_url.strip()
        persist_provider_setting("ANTHROPIC_BASE_URL", body.anthropic_base_url.strip())
        changed = True
    if body.anthropic_model is not None:
        s.anthropic_model = body.anthropic_model.strip()
        persist_provider_setting("ANTHROPIC_MODEL", body.anthropic_model.strip())
        changed = True
    if body.openai_api_key is not None:
        s.openai_api_key = body.openai_api_key.strip()
        persist_provider_setting("OPENAI_API_KEY", body.openai_api_key.strip())
        changed = True
    if body.openai_base_url is not None:
        s.openai_base_url = body.openai_base_url.strip()
        persist_provider_setting("OPENAI_BASE_URL", body.openai_base_url.strip())
        changed = True
    if body.openai_model is not None:
        s.openai_model = body.openai_model.strip()
        persist_provider_setting("OPENAI_MODEL", body.openai_model.strip())
        changed = True
    if body.gemini_api_key is not None:
        s.gemini_api_key = body.gemini_api_key.strip()
        persist_provider_setting("GEMINI_API_KEY", body.gemini_api_key.strip())
        changed = True
    if body.gemini_model is not None:
        s.gemini_model = body.gemini_model.strip()
        persist_provider_setting("GEMINI_MODEL", body.gemini_model.strip())
        changed = True
    if body.ollama_base_url is not None:
        s.ollama_base_url = body.ollama_base_url.strip()
        persist_provider_setting("OLLAMA_BASE_URL", body.ollama_base_url.strip())
        changed = True
    if body.ollama_model is not None:
        s.ollama_model = body.ollama_model.strip()
        persist_provider_setting("OLLAMA_MODEL", body.ollama_model.strip())
        changed = True
    if body.default_llm_provider is not None:
        s.default_llm_provider = body.default_llm_provider.strip()
        persist_provider_setting("DEFAULT_LLM_PROVIDER", body.default_llm_provider.strip())
        changed = True
    # Claude Code CLI settings updates (also persist to .env)
    if body.claude_model is not None:
        s.claude_model = body.claude_model.strip()
        persist_claude_setting("CLAUDE_MODEL", body.claude_model.strip())
        changed = True
    if body.claude_mcp_tools is not None:
        s.claude_mcp_tools = body.claude_mcp_tools.strip()
        persist_claude_setting("CLAUDE_MCP_TOOLS", body.claude_mcp_tools.strip())
        changed = True
    if body.claude_mcp_config_path is not None:
        s.claude_mcp_config_path = body.claude_mcp_config_path.strip()
        persist_claude_setting("CLAUDE_MCP_CONFIG_PATH", body.claude_mcp_config_path.strip())
        changed = True
    if body.claude_temperature is not None:
        s.claude_temperature = body.claude_temperature
        persist_claude_setting("CLAUDE_TEMPERATURE", str(body.claude_temperature))
        changed = True
    if body.claude_max_tokens is not None:
        s.claude_max_tokens = body.claude_max_tokens
        persist_claude_setting("CLAUDE_MAX_TOKENS", str(body.claude_max_tokens))
        changed = True
    if changed:
        reset_orchestrator()
    if body.default_model is not None:
        logger.info(f"默认模型已更新为: {body.default_model}")
    return {"success": True, "message": "设置已保存" + ("，Agent已重新初始化" if changed else "")}


# Provider 管理已移至 backend/app/routers/providers.py
# 以下为调试和测试端点


@app.get("/api/v1/debug/key", dependencies=[Depends(require_api_key)])
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


@app.post("/api/v1/debug/test-llm", dependencies=[Depends(require_api_key)])
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
    logger.error(f"Error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "服务器内部错误，请查看日志了解详情"})
