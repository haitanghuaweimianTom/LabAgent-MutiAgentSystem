"""Provider 管理路由 — CC Switch 风格"""
import httpx
import ipaddress
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.provider_config import (
    list_custom_providers, get_custom_provider, add_custom_provider,
    update_custom_provider, delete_custom_provider, set_default_provider,
    get_default_provider_id, get_provider_models, add_model_to_provider,
    remove_model_from_provider, get_presets, get_presets_by_category,
    import_preset_as_provider, build_test_config, parse_cc_switch_json,
    get_ccswitch_status, sync_ccswitch_to_local, _ccswitch_auto_sync,
    auto_detect_models,
)

from ..routers.tasks import reset_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/providers", tags=["Provider管理"])


@router.get("/")
async def list_providers():
    """列出所有 Provider（预设 + 自定义）"""
    custom = list_custom_providers()
    default_id = get_default_provider_id()
    return {
        "presets": get_presets(),
        "presets_by_category": get_presets_by_category(),
        "custom_providers": custom,
        "default_provider_id": default_id,
    }


@router.get("/presets")
async def list_presets():
    """获取所有内置预设"""
    return {"presets": get_presets(), "presets_by_category": get_presets_by_category()}


@router.post("/import-preset")
async def import_preset(body: Dict[str, Any]):
    """导入预设为自定义 Provider"""
    preset_id = body.get("preset_id", "")
    try:
        result = import_preset_as_provider(preset_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"预设 '{preset_id}' 不存在")
        return {"success": True, "provider": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import-json")
async def import_cc_switch_json(body: Dict[str, Any]):
    """导入 CC Switch 风格 Provider JSON

    支持格式:
    {
      "env": {
        "ANTHROPIC_BASE_URL": "...",
        "ANTHROPIC_AUTH_TOKEN": "...",
        "ANTHROPIC_MODEL": "..."
      },
      "model": "...",
      ...
    }
    """
    parsed = parse_cc_switch_json(body)
    if not parsed:
        raise HTTPException(status_code=400, detail="无法解析 CC Switch JSON：缺少 env 字段")

    if not parsed.get("api_host"):
        raise HTTPException(status_code=400, detail="JSON 中未找到 API 地址（需包含 ANTHROPIC_BASE_URL 或 OPENAI_BASE_URL）")

    try:
        result = add_custom_provider(parsed)
        return {"success": True, "provider": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/")
async def create_provider(body: Dict[str, Any]):
    """创建自定义 Provider"""
    try:
        result = add_custom_provider(body)
        return {"success": True, "provider": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/models")
async def list_all_models():
    """获取所有可用模型（跨 provider）"""
    all_models = []
    default_id = get_default_provider_id()
    for p in list_custom_providers():
        for m in p.get("models", []):
            if isinstance(m, dict):
                all_models.append({
                    "id": f"{p['id']}/{m['name']}",
                    "name": m["name"],
                    "display_name": m.get("display_name", m["name"]),
                    "provider_id": p["id"],
                    "provider_name": p.get("name", ""),
                    "enabled": m.get("enabled", True),
                    "is_default": p.get("id") == default_id,
                })
            else:
                all_models.append({
                    "id": f"{p['id']}/{m}",
                    "name": str(m),
                    "provider_id": p["id"],
                    "provider_name": p.get("name", ""),
                    "enabled": True,
                    "is_default": p.get("id") == default_id,
                })
    return {"models": all_models}


from ..core.provider_models import ApiFormat, AuthField


@router.get("/api-formats")
async def list_api_formats():
    """获取所有支持的 API 格式"""
    return {
        "formats": [
            {"id": fmt.value, "label": fmt.name.replace("_", " ").title(), "desc": _api_format_desc(fmt.value)}
            for fmt in ApiFormat
        ]
    }


@router.get("/auth-fields")
async def list_auth_fields():
    """获取所有支持的认证字段"""
    return {
        "fields": [
            {"id": field.value, "label": field.name.replace("_", " ").title(), "desc": _auth_field_desc(field.value)}
            for field in AuthField
        ]
    }


def _api_format_desc(api_format: str) -> str:
    """API 格式描述"""
    descs = {
        "openai_chat": "/chat/completions",
        "openai_responses": "/responses",
        "anthropic": "/v1/messages",
        "gemini_native": "google.ai",
        "ollama_chat": "/api/chat",
    }
    return descs.get(api_format, "")


def _auth_field_desc(auth_field: str) -> str:
    """认证字段描述"""
    descs = {
        "bearer_token": "Authorization: Bearer <key>",
        "x_api_key": "x-api-key: <key>",
        "anthropic_auth_token": "ANTHROPIC_AUTH_TOKEN (阿里云TokenPlan/Kimi Coding)",
    }
    return descs.get(auth_field, "")


# ===== CC Switch 集成（必须放在 /{provider_id} 之前，避免路径参数冲突） =====

@router.get("/ccswitch-status")
async def ccswitch_status():
    """获取 CC Switch 同步状态"""
    return get_ccswitch_status()


@router.post("/ccswitch-sync")
async def ccswitch_sync():
    """强制同步 CC Switch 配置到本地，并重置编排器"""
    result = sync_ccswitch_to_local(force=True)
    reset_orchestrator()
    return {"success": True, "message": "CC Switch 同步完成，编排器已重置", **result}


class AutoSyncToggle(BaseModel):
    enabled: bool


@router.post("/ccswitch-toggle-auto")
async def ccswitch_toggle_auto(body: AutoSyncToggle):
    """开启/关闭 CC Switch 自动同步"""
    global _ccswitch_auto_sync
    _ccswitch_auto_sync = body.enabled
    return {"success": True, "auto_sync_enabled": _ccswitch_auto_sync}


@router.get("/{provider_id}")
async def get_provider(provider_id: str):
    """获取单个 Provider"""
    p = get_custom_provider(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' 不存在")
    return p


@router.put("/{provider_id}")
async def update_provider(provider_id: str, body: Dict[str, Any]):
    """更新自定义 Provider"""
    try:
        result = update_custom_provider(provider_id, body)
        return {"success": True, "provider": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{provider_id}")
async def delete_provider(provider_id: str):
    """删除自定义 Provider"""
    if delete_custom_provider(provider_id):
        return {"success": True, "deleted": provider_id}
    raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' 不存在")


@router.post("/{provider_id}/default")
async def set_default(provider_id: str):
    """设置默认 Provider"""
    try:
        set_default_provider(provider_id)
        return {"success": True, "default": provider_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{provider_id}/models")
async def add_model(provider_id: str, body: Dict[str, Any]):
    """为 Provider 添加模型"""
    try:
        result = add_model_to_provider(provider_id, body)
        return {"success": True, "model": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{provider_id}/models/{model_name}")
async def remove_model(provider_id: str, model_name: str):
    """从 Provider 移除模型"""
    try:
        remove_model_from_provider(provider_id, model_name)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _validate_api_host(url: str) -> str:
    """验证 api_host 防止 SSRF：仅允许 http/https，阻止内网 IP。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="api_host 仅支持 http/https 协议")
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="api_host 缺少有效主机名")
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            raise HTTPException(status_code=400, detail="api_host 不允许访问内网/本地地址")
    except ValueError:
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            raise HTTPException(status_code=400, detail="api_host 不允许访问本地地址")
    return url


@router.post("/{provider_id}/test")
async def test_provider(provider_id: str, body: Optional[Dict[str, Any]] = None):
    """测试 Provider 连接"""
    provider = get_custom_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' 不存在")

    test_cfg = build_test_config(provider)
    if body:
        test_cfg.update(body)

    api_key = test_cfg.get("api_key", "")
    api_host = test_cfg.get("api_host", "")
    model = test_cfg.get("model", "") or "gpt-3.5-turbo"
    api_format = test_cfg.get("api_format", "openai_chat")
    auth_field = test_cfg.get("auth_field", "")

    if not api_host:
        raise HTTPException(status_code=400, detail="api_host 不能为空")
    _validate_api_host(api_host)

    try:
        if api_format == "anthropic":
            # 根据认证字段决定 header
            if auth_field == "anthropic_auth_token":
                # 阿里云 TokenPlan / Kimi Coding: 使用 ANTHROPIC_AUTH_TOKEN
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
            else:
                # 标准 Anthropic: 使用 x-api-key
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
            payload = {"model": model or "claude-3-haiku-20240307", "max_tokens": 10, "messages": [{"role": "user", "content": "Hi"}]}
            async with httpx.AsyncClient(timeout=30.0, proxy=None) as client:
                response = await client.post(f"{api_host}/v1/messages", headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                content = result.get("content", [{}])[0].get("text", "")
                return {"success": True, "response": content[:50], "latency_ms": int(response.elapsed.total_seconds() * 1000)}

        elif api_format == "anthropic_messages":
            # 兼容 Anthropic Messages API 但使用 OpenAI 风格 endpoint（如 Kimi Coding）
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {"model": model, "messages": [{"role": "user", "content": "Say hi"}], "max_tokens": 10}
            async with httpx.AsyncClient(timeout=30.0, proxy=None) as client:
                response = await client.post(f"{api_host}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content[:50], "latency_ms": int(response.elapsed.total_seconds() * 1000)}

        elif api_format == "ollama_chat":
            payload = {"model": model or "qwen2.5:latest", "messages": [{"role": "user", "content": "Hi"}], "stream": False}
            async with httpx.AsyncClient(timeout=30.0, proxy=None) as client:
                response = await client.post(f"{api_host}/api/chat", json=payload)
                response.raise_for_status()
                result = response.json()
                content = result.get("message", {}).get("content", "")
                return {"success": True, "response": content[:50], "latency_ms": int(response.elapsed.total_seconds() * 1000)}

        else:  # openai_chat, openai_responses, gemini_native
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"model": model, "messages": [{"role": "user", "content": "Say hi, just these two words"}], "max_tokens": 10}
            async with httpx.AsyncClient(timeout=30.0, proxy=None) as client:
                response = await client.post(f"{api_host}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content[:50], "latency_ms": int(response.elapsed.total_seconds() * 1000)}

    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP {e.response.status_code}", "detail": e.response.text[:300]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/{provider_id}/auto-detect-models")
async def detect_models(provider_id: str):
    """自动从 Provider API 获取可用模型列表"""
    provider = get_custom_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' 不存在")

    models = auto_detect_models(provider_id)
    if models:
        # 更新 provider 的模型列表
        current_models = provider.get("models", [])
        current_names = {m.get("name") for m in current_models}
        new_models = current_models + [{"name": m, "enabled": True} for m in models if m not in current_names]
        if len(new_models) > len(current_models):
            update_custom_provider(provider_id, {"models": new_models})
        return {"success": True, "models": models, "message": f"检测到 {len(models)} 个模型"}
    return {"success": False, "models": [], "message": "未能自动获取模型列表，请手动添加"}
