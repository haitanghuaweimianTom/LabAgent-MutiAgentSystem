"""自定义 Provider 配置管理 — CC Switch 风格统一 Schema"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .provider_models import (
    type_to_api_format, type_to_category, type_to_icon, type_to_icon_color,
    import_preset, get_preset_by_id, PROVIDER_PRESETS,
)

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent.parent.parent / "custom_providers.json"
CONFIG_VERSION = 2  # 当前 schema 版本号

PROVIDER_TYPES = ["openai", "anthropic", "gemini", "ollama", "minimax", "claude_cli"]


def _read_config() -> Dict:
    """读取配置"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text("utf-8"))
        except json.JSONDecodeError:
            return {"providers": [], "default_provider": None, "_version": 1}
    return {"providers": [], "default_provider": None, "_version": 1}


def _write_config(config: Dict) -> None:
    """写入配置（原子写入）"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_FILE)


def migrate_legacy_to_new() -> bool:
    """将旧格式 provider 迁移到新 Schema，返回是否发生了迁移"""
    config = _read_config()
    if config.get("_version", 1) >= CONFIG_VERSION:
        return False

    migrated = False
    new_providers = []
    for p in config.get("providers", []):
        if "_version" in p and p["_version"] >= CONFIG_VERSION:
            new_providers.append(p)
            continue

        mp = dict(p)  # 复制旧数据

        # 迁移 models 为数组格式
        old_models = p.get("models", [])
        if old_models and not isinstance(old_models[0], dict):
            mp["models"] = [{"name": str(m), "enabled": True} for m in old_models]
        elif old_models:
            mp["models"] = []
            for m in old_models:
                if isinstance(m, dict):
                    mp["models"].append({
                        "name": m.get("name", ""),
                        "display_name": m.get("display_name"),
                        "enabled": m.get("enabled", True),
                    })
                else:
                    mp["models"].append({"name": str(m), "enabled": True})

        # 补全 category / meta / icon
        p_type = mp.get("type", "openai")
        api_host = mp.get("api_host", "")
        mp.setdefault("category", type_to_category(p_type, api_host))
        mp.setdefault("icon", type_to_icon(p_type))
        mp.setdefault("icon_color", type_to_icon_color(p_type))
        mp.setdefault("enabled", True)

        # 补全 meta
        if not mp.get("meta"):
            mp["meta"] = {"api_format": type_to_api_format(p_type)}
        else:
            mp["meta"].setdefault("api_format", type_to_api_format(p_type))

        mp["_version"] = CONFIG_VERSION
        mp.setdefault("created_at", int(time.time()))
        mp.setdefault("updated_at", int(time.time()))

        new_providers.append(mp)
        migrated = True

    config["providers"] = new_providers
    config["_version"] = CONFIG_VERSION
    _write_config(config)

    if migrated:
        logger.info(f"Provider 配置已迁移到 schema v{CONFIG_VERSION}")
    return migrated


# ===== CRUD API（保留原有签名，内部使用新 Schema） =====

def list_custom_providers() -> List[Dict[str, Any]]:
    """列出所有自定义 Provider（合并预设信息）"""
    config = _read_config()
    return config.get("providers", [])


def get_custom_provider(provider_id: str) -> Optional[Dict[str, Any]]:
    """获取指定自定义 Provider"""
    for p in list_custom_providers():
        if p.get("id") == provider_id:
            return p
    return None


def add_custom_provider(data: Dict[str, Any]) -> Dict[str, Any]:
    """添加自定义 Provider"""
    config = _read_config()
    providers = config.get("providers", [])

    provider_id = data.get("id", "").strip().lower().replace(" ", "-") or f"custom_{int(time.time())}"
    data["id"] = provider_id

    for p in providers:
        if p.get("id") == provider_id:
            raise ValueError(f"Provider ID '{provider_id}' 已存在")

    if not data.get("name"):
        raise ValueError("Provider 名称不能为空")

    p_type = data.get("type", "openai")
    if p_type not in PROVIDER_TYPES:
        raise ValueError(f"Provider 类型必须是: {PROVIDER_TYPES}")

    api_host = data.get("api_host", "")
    now = int(time.time())

    provider = {
        "id": provider_id,
        "name": data["name"],
        "type": p_type,
        "category": data.get("category", type_to_category(p_type, api_host)),
        "meta": data.get("meta", {"api_format": type_to_api_format(p_type)}),
        "api_key": data.get("api_key", ""),
        "api_host": api_host,
        "models": data.get("models", []),
        "enabled": data.get("enabled", True),
        "icon": data.get("icon", type_to_icon(p_type)),
        "icon_color": data.get("icon_color", type_to_icon_color(p_type)),
        "notes": data.get("notes", ""),
        "created_at": now,
        "updated_at": now,
        "_version": CONFIG_VERSION,
    }

    providers.append(provider)
    config["providers"] = providers
    _write_config(config)
    return provider


def update_custom_provider(provider_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """更新自定义 Provider"""
    config = _read_config()
    for i, p in enumerate(config.get("providers", [])):
        if p.get("id") == provider_id:
            # 不允许修改 ID
            data.pop("id", None)
            data["updated_at"] = int(time.time())

            # 如果更新了 type/api_host，自动更新 meta.api_format
            if "type" in data or "api_host" in data:
                p_type = data.get("type", p.get("type", "openai"))
                api_host = data.get("api_host", p.get("api_host", ""))
                meta = p.get("meta", {})
                if "meta" in data:
                    meta = {**meta, **data["meta"]}
                meta.setdefault("api_format", type_to_api_format(p_type))
                data["meta"] = meta
                data.setdefault("category", type_to_category(p_type, api_host))
                data.setdefault("icon", type_to_icon(p_type))
                data.setdefault("icon_color", type_to_icon_color(p_type))

            config["providers"][i] = {**p, **data}
            _write_config(config)
            return config["providers"][i]
    raise ValueError(f"Provider '{provider_id}' 不存在")


def delete_custom_provider(provider_id: str) -> bool:
    """删除自定义 Provider"""
    config = _read_config()
    original_len = len(config.get("providers", []))
    config["providers"] = [p for p in config["providers"] if p.get("id") != provider_id]
    if config.get("default_provider") == provider_id:
        config["default_provider"] = None
    _write_config(config)
    return len(config["providers"]) < original_len


def set_default_provider(provider_id: str) -> bool:
    """设置默认 Provider"""
    config = _read_config()
    ids = [p.get("id") for p in config.get("providers", [])]
    if provider_id not in ids:
        raise ValueError(f"Provider '{provider_id}' 不存在")
    config["default_provider"] = provider_id
    _write_config(config)
    return True


def get_default_provider_id() -> Optional[str]:
    """获取默认 Provider ID"""
    return _read_config().get("default_provider")


def get_default_provider() -> Optional[Dict[str, Any]]:
    """获取默认 Provider 完整信息"""
    default_id = get_default_provider_id()
    if default_id:
        return get_custom_provider(default_id)
    return None


def get_provider_models(provider_id: str) -> List[Dict[str, Any]]:
    """获取指定 Provider 的模型列表"""
    p = get_custom_provider(provider_id)
    if p:
        return p.get("models", [])
    return []


def add_model_to_provider(provider_id: str, model: Dict[str, Any]) -> Dict[str, Any]:
    """为指定 Provider 添加模型"""
    config = _read_config()
    for i, p in enumerate(config.get("providers", [])):
        if p.get("id") == provider_id:
            models = p.get("models", [])
            model_name = model.get("name", "").strip()
            if not model_name:
                raise ValueError("模型名称不能为空")
            for m in models:
                if m.get("name") == model_name:
                    raise ValueError(f"模型 '{model_name}' 已存在")
            models.append(model)
            config["providers"][i]["models"] = models
            config["providers"][i]["updated_at"] = int(time.time())
            _write_config(config)
            return model
    raise ValueError(f"Provider '{provider_id}' 不存在")


def remove_model_from_provider(provider_id: str, model_name: str) -> bool:
    """从指定 Provider 移除模型"""
    config = _read_config()
    for i, p in enumerate(config.get("providers", [])):
        if p.get("id") == provider_id:
            models = p.get("models", [])
            p["models"] = [m for m in models if m.get("name") != model_name]
            p["updated_at"] = int(time.time())
            config["providers"][i] = p
            _write_config(config)
            return True
    raise ValueError(f"Provider '{provider_id}' 不存在")


# ===== 预设管理 =====

def get_presets() -> List[Dict[str, Any]]:
    """获取所有内置预设"""
    return list(PROVIDER_PRESETS)


def get_presets_by_category() -> Dict[str, List[Dict[str, Any]]]:
    """按分类获取预设"""
    from .provider_models import PRESETS_BY_CATEGORY
    return {cat.value: presets for cat, presets in PRESETS_BY_CATEGORY.items()}


def import_preset_as_provider(preset_id: str) -> Optional[Dict[str, Any]]:
    """导入预设为自定义 provider"""
    template = import_preset(preset_id)
    if not template:
        return None
    return add_custom_provider(template)


# ===== Provider 测试辅助 =====

def build_test_config(provider: Dict[str, Any]) -> Dict[str, Any]:
    """构建 provider 测试配置"""
    meta = provider.get("meta", {})
    return {
        "type": provider.get("type", "openai"),
        "api_key": provider.get("api_key", ""),
        "api_host": provider.get("api_host", ""),
        "model": next((m.get("name") for m in provider.get("models", []) if m.get("enabled")), ""),
        "api_format": meta.get("api_format", type_to_api_format(provider.get("type", "openai"))),
        "auth_field": meta.get("auth_field", ""),
        "is_full_url": meta.get("is_full_url", False),
    }


def parse_cc_switch_json(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """解析 CC Switch 风格 Provider JSON 并创建 Provider

    支持的 CC Switch JSON 格式:
    {
      "env": {
        "ANTHROPIC_BASE_URL": "...",
        "ANTHROPIC_AUTH_TOKEN": "...",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "...",
        ...
      },
      "model": "...",
      "effortLevel": "max",
      ...
    }
    """
    env = config.get("env", {})
    if not env:
        return None

    # 提取 API 地址
    api_host = (
        env.get("ANTHROPIC_BASE_URL")
        or env.get("OPENAI_BASE_URL")
        or env.get("OPENAI_API_BASE")
        or env.get("BASE_URL")
        or env.get("API_BASE")
        or ""
    )

    # 提取 API Key / Token
    api_key = (
        env.get("ANTHROPIC_AUTH_TOKEN")
        or env.get("ANTHROPIC_API_KEY")
        or env.get("OPENAI_API_KEY")
        or env.get("API_KEY")
        or ""
    )

    # 提取模型名称
    model_name = (
        config.get("model")
        or env.get("ANTHROPIC_MODEL")
        or env.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
        or env.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
        or env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
        or env.get("DEFAULT_MODEL")
        or ""
    )

    # 自动推断 API 格式
    api_format = "openai_chat"  # 默认
    if "anthropic" in api_host.lower() or "kimi" in api_host.lower() or "coding" in api_host.lower():
        # 如果 key 字段名包含 ANTHROPIC 前缀，推断为 Anthropic 格式
        if any(k.startswith("ANTHROPIC_") for k in env.keys()):
            api_format = "anthropic"
        else:
            api_format = "openai_chat"
    elif "openai" in api_host.lower():
        api_format = "openai_chat"
    elif "gemini" in api_host.lower() or "google" in api_host.lower():
        api_format = "gemini_native"
    elif "localhost:11434" in api_host or "ollama" in api_host.lower():
        api_format = "ollama_chat"

    # 推断 provider 类型
    p_type = "openai"
    if api_format == "anthropic":
        p_type = "anthropic"
    elif api_format == "ollama_chat":
        p_type = "ollama"
    elif api_format == "gemini_native":
        p_type = "gemini"

    # 从 URL 推断 provider 名称
    name_from_url = api_host.split("://")[1].split("/")[0] if "://" in api_host else api_host
    name = config.get("name", "") or env.get("PROVIDER_NAME", "") or name_from_url

    models = []
    if model_name:
        models.append({"name": model_name, "enabled": True})

    return {
        "name": name or "CC Switch Provider",
        "type": p_type,
        "api_key": api_key,
        "api_host": api_host,
        "models": models,
        "meta": {"api_format": api_format},
        "notes": "从 CC Switch JSON 导入",
    }


# ===== CC Switch SQLite 自动检测 =====
# 优先从环境变量获取，避免绑定特定用户主目录；未设置时回退到默认路径
_CCSWITCH_DB_PATH = os.environ.get("CCSWITCH_DB_PATH", "")
if _CCSWITCH_DB_PATH:
    CCSWITCH_DB = Path(_CCSWITCH_DB_PATH)
else:
    CCSWITCH_DB = Path.home() / ".cc-switch" / "cc-switch.db"


def detect_ccswitch_providers() -> List[Dict[str, Any]]:
    """从 ccswitch SQLite 数据库读取所有 claude 类型的 Provider 配置。

    返回已解析的 provider 列表（可直接用于 add_custom_provider 或同步）。
    如果 ccswitch 未安装或数据库不存在，返回空列表。
    """
    if not CCSWITCH_DB.exists():
        return []

    try:
        import sqlite3
        conn = sqlite3.connect(str(CCSWITCH_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, settings_config, is_current FROM providers WHERE app_type='claude'"
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.warning(f"读取 ccswitch 数据库失败: {e}")
        return []

    providers = []
    for row in rows:
        try:
            config = json.loads(row["settings_config"])
        except (json.JSONDecodeError, TypeError):
            continue

        parsed = parse_cc_switch_json(config)
        if not parsed or not parsed.get("api_key") or not parsed.get("api_host"):
            continue

        # 保留原始 ID 和名称
        parsed["id"] = row["id"]
        parsed["name"] = row["name"] or parsed["name"]
        parsed["_ccswitch_current"] = bool(row["is_current"])
        providers.append(parsed)

    return providers


def sync_ccswitch_to_local() -> Dict[str, Any]:
    """将 ccswitch 中的 Provider 同步到本地 custom_providers.json。

    策略：
    - 本地已存在的 provider（按 id 匹配）→ 更新 api_key / api_host / models
    - 本地不存在的 → 新增
    - ccswitch 标记为 current 的 → 设为 default_provider

    返回 {"synced": int, "added": int, "updated": int, "default": str}
    """
    ccswitch_providers = detect_ccswitch_providers()
    if not ccswitch_providers:
        return {"synced": 0, "added": 0, "updated": 0, "default": ""}

    config = _read_config()
    local_providers = config.get("providers", [])
    local_by_id = {p["id"]: p for p in local_providers}

    added = 0
    updated = 0
    current_id = ""

    for cs_p in ccswitch_providers:
        pid = cs_p["id"]
        if cs_p.get("_ccswitch_current"):
            current_id = pid

        if pid in local_by_id:
            # 更新已有 provider 的关键字段
            local = local_by_id[pid]
            local["api_key"] = cs_p["api_key"]
            local["api_host"] = cs_p["api_host"]
            if cs_p.get("models"):
                local["models"] = cs_p["models"]
            local["meta"] = cs_p.get("meta", local.get("meta", {}))
            local["updated_at"] = int(time.time())
            updated += 1
        else:
            # 新增
            new_p = {
                "id": pid,
                "name": cs_p["name"],
                "type": cs_p.get("type", "anthropic"),
                "category": "custom",
                "meta": cs_p.get("meta", {"api_format": "anthropic"}),
                "api_key": cs_p["api_key"],
                "api_host": cs_p["api_host"],
                "models": cs_p.get("models", []),
                "enabled": True,
                "icon": "Claude",
                "icon_color": "#d97706",
                "notes": "从 ccswitch 自动同步",
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
                "_version": 2,
            }
            local_providers.append(new_p)
            added += 1

    config["providers"] = local_providers
    if current_id:
        config["default_provider"] = current_id

    _write_config(config)

    return {
        "synced": added + updated,
        "added": added,
        "updated": updated,
        "default": current_id,
    }
