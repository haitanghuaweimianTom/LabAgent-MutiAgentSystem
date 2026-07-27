"""数据源 API Key 管理（GitHub / Kaggle / HuggingFace 等）。

独立于 LLM provider 体系（custom_providers.json）——这里专管"获取数据"用的凭证。
key 明文存 backend/data/datasource_keys.json，与现有 provider 体系风格一致。

采集器（self_collector）通过 get_datasource_key() 读取 key 调外部 API；
前端通过 routers/datasources.py 的 CRUD 接口管理 key。

详见 [[data-gate-akshare-fix]]、[[no-local-binding-policy]]。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# key 存储路径（明文，仿 custom_providers.json）
_KEYS_FILE = Path(__file__).parent.parent.parent.parent / "backend" / "data" / "datasource_keys.json"

# 支持的数据源 + 各自字段定义（前端据此渲染表单）
DATASOURCE_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "github": {
        "label": "GitHub",
        "icon": "Github",
        "fields": [
            {"name": "token", "label": "Personal Access Token", "type": "password",
             "placeholder": "ghp_xxxxxxxxxxxxxxxxxxxx",
             "hint": "匿名限 60 次/小时；带 token 提至 5000 次/小时。仅需 public_repo 读权限即可搜公开数据集。"},
        ],
    },
    "kaggle": {
        "label": "Kaggle",
        "icon": "Kaggle",
        "fields": [
            {"name": "username", "label": "用户名", "type": "text", "placeholder": "your_kaggle_username"},
            {"name": "key", "label": "API Key", "type": "password", "placeholder": "xxxxxxxxxxxxxxxxxxxxxxxx",
             "hint": "kaggle.com → Account → Create New API Token 下载 kaggle.json，取 username + key。"},
        ],
    },
    "huggingface": {
        "label": "HuggingFace",
        "icon": "HuggingFace",
        "fields": [
            {"name": "token", "label": "Access Token", "type": "password", "placeholder": "hf_xxxxxxxxxxxx",
             "hint": "huggingface.co → Settings → Access Tokens。注意：本机网络需能访问 huggingface.co。"},
        ],
    },
}


def _load() -> Dict[str, Any]:
    """读取全部 key 配置。文件不存在或损坏 → 返回空 dict。"""
    if not _KEYS_FILE.exists():
        return {}
    try:
        data = json.loads(_KEYS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"读取 datasource_keys.json 失败: {e}")
        return {}


def _save(data: Dict[str, Any]) -> None:
    """写入全部 key 配置（自动建目录）。"""
    _KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEYS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(_KEYS_FILE, 0o600)  # 仅属主可读写
    except Exception:
        pass


def list_datasource_keys() -> Dict[str, Any]:
    """列出所有数据源 key（token 脱敏，仅供前端展示）。

    返回 {source: {enabled, configured, masked_fields...}}。
    """
    data = _load()
    result: Dict[str, Any] = {}
    for source in DATASOURCE_SCHEMAS:
        entry = data.get(source, {})
        is_configured = bool(entry.get("enabled")) and any(
            str(entry.get(f["name"] or "")).strip()
            for f in DATASOURCE_SCHEMAS[source]["fields"]
        )
        masked = {}
        for f in DATASOURCE_SCHEMAS[source]["fields"]:
            fname = f["name"]
            val = str(entry.get(fname, "") or "")
            # 脱敏：仅显示前2后2
            if val:
                masked[fname] = val[:2] + "*" * (len(val) - 4) + val[-2:] if len(val) > 4 else "****"
            else:
                masked[fname] = ""
        result[source] = {
            "label": DATASOURCE_SCHEMAS[source]["label"],
            "icon": DATASOURCE_SCHEMAS[source]["icon"],
            "enabled": bool(entry.get("enabled", False)),
            "configured": is_configured,
            "fields": masked,
            "updated_at": entry.get("updated_at"),
        }
    return result


def save_datasource_key(source: str, fields: Dict[str, str], enabled: bool = True) -> Dict[str, Any]:
    """保存某数据源的 key 字段。"""
    if source not in DATASOURCE_SCHEMAS:
        raise ValueError(f"不支持的数据源: {source}")
    data = _load()
    entry = data.get(source, {})
    for f in DATASOURCE_SCHEMAS[source]["fields"]:
        fname = f["name"]
        if fname in fields:
            val = (fields.get(fname) or "").strip()
            if val:
                entry[fname] = val
            elif fname in entry and not val:
                # 空值 → 清除该字段
                entry.pop(fname, None)
    entry["enabled"] = enabled
    entry["updated_at"] = datetime.now().isoformat()
    data[source] = entry
    _save(data)
    logger.info(f"数据源 key 已保存: {source} (enabled={enabled})")
    return {"source": source, "saved": True, "enabled": enabled}


def delete_datasource_key(source: str) -> Dict[str, Any]:
    """删除某数据源的 key 配置。"""
    if source not in DATASOURCE_SCHEMAS:
        raise ValueError(f"不支持的数据源: {source}")
    data = _load()
    if source in data:
        data.pop(source)
        _save(data)
        logger.info(f"数据源 key 已删除: {source}")
    return {"source": source, "deleted": True}


def get_datasource_key(source: str) -> Optional[Dict[str, str]]:
    """供采集器调用：读取某数据源的明文 key（未配置或 disabled → None）。

    返回 {字段名: 明文值}；key 都在主进程内使用，不落日志。
    """
    if source not in DATASOURCE_SCHEMAS:
        return None
    entry = _load().get(source, {})
    if not entry.get("enabled", False):
        return None
    result: Dict[str, str] = {}
    for f in DATASOURCE_SCHEMAS[source]["fields"]:
        fname = f["name"]
        val = entry.get(fname)
        if val:
            result[fname] = val
    # 至少一个字段有值才算有效
    return result if result else None


def get_schemas() -> Dict[str, Any]:
    """返回数据源字段定义（前端表单渲染用）。"""
    return DATASOURCE_SCHEMAS
