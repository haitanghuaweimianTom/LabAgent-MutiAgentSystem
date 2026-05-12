"""Provider 数据模型 — 采用 CC Switch 风格统一结构"""
import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional


class ProviderCategory(str, Enum):
    OFFICIAL = "official"
    CN_OFFICIAL = "cn_official"
    CLOUD_PROVIDER = "cloud_provider"
    AGGREGATOR = "aggregator"
    THIRD_PARTY = "third_party"
    CUSTOM = "custom"


class ApiFormat(str, Enum):
    OPENAI_CHAT = "openai_chat"
    OPENAI_RESPONSES = "openai_responses"
    ANTHROPIC_MESSAGES = "anthropic"
    GEMINI_NATIVE = "gemini_native"
    OLLAMA_CHAT = "ollama_chat"


class AuthField(str, Enum):
    """认证字段类型 — 用户可选择 Provider 使用的认证方式"""
    BEARER_TOKEN = "bearer_token"     # Authorization: Bearer <key>  (OpenAI/SiliconFlow 等兼容格式)
    X_API_KEY = "x_api_key"          # x-api-key: <key>             (Anthropic 原生格式)
    ANTHROPIC_AUTH_TOKEN = "anthropic_auth_token"  # 使用 ANTHROPIC_AUTH_TOKEN (阿里云TokenPlan 等)


def type_to_api_format(p_type: str) -> str:
    """Provider type -> API format mapping"""
    mapping = {
        "openai": "openai_chat",
        "anthropic": "anthropic",
        "gemini": "gemini_native",
        "ollama": "ollama_chat",
        "minimax": "openai_chat",
        "claude_cli": "anthropic",
    }
    return mapping.get(p_type, "openai_chat")


def type_to_category(p_type: str, api_host: str = "") -> str:
    """Provider type + host -> category mapping"""
    official_hosts = {"api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com"}
    cn_official_hosts = {"dashscope.aliyuncs.com", "api.siliconflow.cn", "open.bigmodel.cn", "api.moonshot.cn"}
    if p_type in ("openai", "anthropic", "gemini") and api_host in official_hosts:
        return ProviderCategory.OFFICIAL
    if api_host and any(h in api_host for h in cn_official_hosts):
        return ProviderCategory.CN_OFFICIAL
    if p_type == "minimax":
        return ProviderCategory.THIRD_PARTY
    if p_type == "ollama":
        return ProviderCategory.CLOUD_PROVIDER
    return ProviderCategory.CUSTOM


def type_to_icon(p_type: str) -> str:
    type_icons = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "gemini": "Gemini",
        "ollama": "Ollama",
        "minimax": "MiniMax",
        "claude_cli": "CLI",
    }
    return type_icons.get(p_type, "Custom")


def type_to_icon_color(p_type: str) -> str:
    colors = {
        "openai": "#10a37f",
        "anthropic": "#d9733e",
        "gemini": "#4285f4",
        "ollama": "#000000",
        "minimax": "#6366f1",
        "claude_cli": "#8b5cf6",
    }
    return colors.get(p_type, "#666666")


# ===== 内置 Provider 预设 =====
PROVIDER_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "openai-official", "name": "OpenAI", "type": "openai",
        "category": ProviderCategory.OFFICIAL,
        "icon": "OpenAI", "icon_color": "#10a37f",
        "api_host": "https://api.openai.com",
        "meta": {"api_format": "openai_chat"},
        "models": [{"name": "gpt-4o", "enabled": True}, {"name": "gpt-4o-mini", "enabled": True}, {"name": "o3", "enabled": True}],
    },
    {
        "id": "anthropic-official", "name": "Anthropic", "type": "anthropic",
        "category": ProviderCategory.OFFICIAL,
        "icon": "Anthropic", "icon_color": "#d9733e",
        "api_host": "https://api.anthropic.com",
        "meta": {"api_format": "anthropic"},
        "models": [{"name": "claude-sonnet-4-6-20250514", "enabled": True}, {"name": "claude-opus-4-7-20250522", "enabled": True}],
    },
    {
        "id": "gemini-official", "name": "Google Gemini", "type": "gemini",
        "category": ProviderCategory.OFFICIAL,
        "icon": "Gemini", "icon_color": "#4285f4",
        "api_host": "https://generativelanguage.googleapis.com",
        "meta": {"api_format": "gemini_native"},
        "models": [{"name": "gemini-2.5-pro", "enabled": True}, {"name": "gemini-2.5-flash", "enabled": True}],
    },
    {
        "id": "bailian", "name": "阿里云百炼", "type": "openai",
        "category": ProviderCategory.CN_OFFICIAL,
        "icon": "Aliyun", "icon_color": "#ff6a00",
        "api_host": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "meta": {"api_format": "openai_chat", "auth_field": "bearer_token"},
        "models": [{"name": "qwen-plus", "enabled": True}, {"name": "qwen-max", "enabled": True}, {"name": "qwen-turbo", "enabled": True}, {"name": "qwen-long", "enabled": True}],
    },
    {
        "id": "aliyun-tokenplan", "name": "阿里云 TokenPlan (Anthropic兼容)", "type": "anthropic",
        "category": ProviderCategory.CN_OFFICIAL,
        "icon": "Aliyun", "icon_color": "#ff6a00",
        "api_host": "https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic",
        "meta": {"api_format": "anthropic", "auth_field": "anthropic_auth_token"},
        "models": [{"name": "glm-5.1", "enabled": True}, {"name": "qwen3.6-plus", "enabled": True}, {"name": "qwen3.6-flash", "enabled": True}, {"name": "qwen-image-2.0", "enabled": True}],
    },
    {
        "id": "siliconflow", "name": "SiliconFlow 硅基流动", "type": "openai",
        "category": ProviderCategory.CN_OFFICIAL,
        "icon": "SiliconFlow", "icon_color": "#6366f1",
        "api_host": "https://api.siliconflow.cn/v1",
        "meta": {"api_format": "openai_chat"},
        "models": [{"name": "Qwen/Qwen2.5-72B-Instruct", "enabled": True}, {"name": "deepseek-ai/DeepSeek-V3", "enabled": True}, {"name": "THUDM/glm-4-9b-chat", "enabled": True}],
    },
    {
        "id": "zhipu", "name": "智谱 AI", "type": "openai",
        "category": ProviderCategory.CN_OFFICIAL,
        "icon": "Zhipu", "icon_color": "#1677ff",
        "api_host": "https://open.bigmodel.cn/api/paas/v4",
        "meta": {"api_format": "openai_chat"},
        "models": [{"name": "glm-4-plus", "enabled": True}, {"name": "glm-4-flash", "enabled": True}, {"name": "glm-4v-plus", "enabled": True}],
    },
    {
        "id": "moonshot", "name": "月之暗面 Kimi", "type": "openai",
        "category": ProviderCategory.CN_OFFICIAL,
        "icon": "Kimi", "icon_color": "#6c5ce7",
        "api_host": "https://api.moonshot.cn/v1",
        "meta": {"api_format": "openai_chat", "auth_field": "bearer_token"},
        "models": [{"name": "moonshot-v1-8k", "enabled": True}, {"name": "moonshot-v1-32k", "enabled": True}, {"name": "moonshot-v1-128k", "enabled": True}],
    },
    {
        "id": "kimi-coding", "name": "Kimi Coding (Anthropic兼容)", "type": "anthropic",
        "category": ProviderCategory.CN_OFFICIAL,
        "icon": "Kimi", "icon_color": "#6c5ce7",
        "api_host": "https://api.kimi.com/coding",
        "meta": {"api_format": "anthropic", "auth_field": "anthropic_auth_token"},
        "models": [{"name": "kimi-k2.6", "enabled": True}],
    },
    {
        "id": "deepseek", "name": "DeepSeek", "type": "openai",
        "category": ProviderCategory.CN_OFFICIAL,
        "icon": "DeepSeek", "icon_color": "#1e90ff",
        "api_host": "https://api.deepseek.com",
        "meta": {"api_format": "openai_chat"},
        "models": [{"name": "deepseek-chat", "enabled": True}, {"name": "deepseek-reasoner", "enabled": True}],
    },
    {
        "id": "minimax", "name": "MiniMax", "type": "minimax",
        "category": ProviderCategory.THIRD_PARTY,
        "icon": "MiniMax", "icon_color": "#6366f1",
        "api_host": "https://api.minimax.chat/v1",
        "meta": {"api_format": "openai_chat"},
        "models": [{"name": "minimax-m2.7", "enabled": True}],
    },
    {
        "id": "ollama-local", "name": "Ollama (本地)", "type": "ollama",
        "category": ProviderCategory.CLOUD_PROVIDER,
        "icon": "Ollama", "icon_color": "#000000",
        "api_host": "http://localhost:11434",
        "meta": {"api_format": "ollama_chat"},
        "models": [{"name": "qwen2.5:latest", "enabled": True}, {"name": "llama3.2:latest", "enabled": True}],
    },
    {
        "id": "openrouter", "name": "OpenRouter", "type": "openai",
        "category": ProviderCategory.AGGREGATOR,
        "icon": "OpenRouter", "icon_color": "#7c3aed",
        "api_host": "https://openrouter.ai/api/v1",
        "meta": {"api_format": "openai_chat"},
        "models": [{"name": "anthropic/claude-sonnet-4.6", "enabled": True}, {"name": "openai/gpt-4o", "enabled": True}],
    },
]

PRESETS_BY_CATEGORY: Dict[str, List[Dict[str, Any]]] = {}
for p in PROVIDER_PRESETS:
    cat = p.get("category", ProviderCategory.CUSTOM)
    PRESETS_BY_CATEGORY.setdefault(cat, []).append(p)


def get_preset_by_id(preset_id: str) -> Optional[Dict[str, Any]]:
    """通过 ID 获取预设"""
    for p in PROVIDER_PRESETS:
        if p["id"] == preset_id:
            return p
    return None


def import_preset(preset_id: str) -> Optional[Dict[str, Any]]:
    """导入预设为自定义 provider（返回模板，不含 key）"""
    preset = get_preset_by_id(preset_id)
    if not preset:
        return None
    return {
        "id": f"{preset_id}-{int(time.time())}",
        "name": preset["name"],
        "type": preset["type"],
        "category": preset["category"],
        "icon": preset.get("icon"),
        "icon_color": preset.get("icon_color"),
        "api_host": preset["api_host"],
        "meta": preset.get("meta", {}),
        "models": preset.get("models", []),
    }
