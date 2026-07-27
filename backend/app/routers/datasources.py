"""数据源 API Key 管理路由（GitHub / Kaggle / HuggingFace）。

供前端「数据源 Key」面板调用：列出 / 保存 / 删除 key + 测试连通性。
采集器（self_collector）通过 core.datasource_config.get_datasource_key 读 key 调外部 API。

与 providers 路由（管 LLM）分开，职责清晰。
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.datasource_config import (
    DATASOURCE_SCHEMAS,
    delete_datasource_key,
    get_datasource_key,
    get_schemas,
    list_datasource_keys,
    save_datasource_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasources", tags=["datasources"])


class SaveKeyRequest(BaseModel):
    """保存数据源 key 的请求体。"""
    fields: Dict[str, str]  # {字段名: 值}
    enabled: bool = True


@router.get("/schemas")
async def get_datasource_schemas() -> Dict[str, Any]:
    """返回各数据源字段定义（前端表单渲染用）。"""
    return {"schemas": get_schemas()}


@router.get("/keys")
async def list_keys() -> Dict[str, Any]:
    """列出所有数据源 key（脱敏）。"""
    return {"keys": list_datasource_keys()}


@router.post("/keys/{source}")
async def save_key(source: str, req: SaveKeyRequest) -> Dict[str, Any]:
    """保存某数据源的 key。"""
    try:
        return save_datasource_key(source, req.fields, req.enabled)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/keys/{source}")
async def delete_key(source: str) -> Dict[str, Any]:
    """删除某数据源的 key。"""
    try:
        return delete_datasource_key(source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/keys/{source}/test")
async def test_key(source: str) -> Dict[str, Any]:
    """测试数据源 key 连通性（返回 ok + 限额信息）。"""
    if source not in DATASOURCE_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"不支持的数据源: {source}")
    keys = get_datasource_key(source)
    # GitHub/HuggingFace 镜像支持匿名测试，其余源无 key 直接返回
    if not keys and source not in ("github", "huggingface"):
        return {"source": source, "ok": False, "message": "未配置 key 或已禁用"}

    try:
        if source == "github":
            return await _test_github(keys)
        elif source == "kaggle":
            return await _test_kaggle(keys)
        elif source == "huggingface":
            return await _test_huggingface(keys)
        return {"source": source, "ok": False, "message": "未知数据源"}
    except Exception as e:
        logger.warning(f"测试 {source} 连通性失败: {e}")
        return {"source": source, "ok": False, "message": f"连通失败: {e}"}


async def _test_github(keys: Dict[str, str]) -> Dict[str, Any]:
    """GitHub：调 rate_limit 验证 token 有效 + 返回限额（无 token 走匿名）。"""
    from ..core.proxy import smart_get
    headers = {"Accept": "application/vnd.github+json"}
    token = (keys or {}).get("token", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = await smart_get("https://api.github.com/rate_limit", headers=headers, timeout=15.0)
    except Exception as e:
        return {"source": "github", "ok": False, "message": f"连接失败: {type(e).__name__}: {e}"}
    if resp.status_code != 200:
        return {"source": "github", "ok": False, "message": f"HTTP {resp.status_code}"}
    core = resp.json().get("resources", {}).get("core", {})
    limit = core.get("limit")
    # 有 token 时 limit=5000，匿名 60
    return {
        "source": "github",
        "ok": True,
        "message": f"Token {'有效' if token else '匿名'}，限额 {core.get('remaining')}/{limit} 次/小时",
        "authenticated": bool(token),
        "rate_limit": limit,
    }


async def _test_kaggle(keys: Dict[str, str]) -> Dict[str, Any]:
    """Kaggle：用 username+key 调 dataset list 验证。"""
    import os
    import tempfile
    username = keys.get("username", "")
    key = keys.get("key", "")
    if not username or not key:
        return {"source": "kaggle", "ok": False, "message": "username 或 key 缺失"}
    # kaggle SDK 从 ~/.kaggle/kaggle.json 读凭证，临时写入测试
    kaggle_dir = os.path.expanduser("~/.kaggle")
    os.makedirs(kaggle_dir, exist_ok=True)
    cred_path = os.path.join(kaggle_dir, "kaggle.json")
    try:
        with open(cred_path, "w") as f:
            import json
            json.dump({"username": username, "key": key}, f)
        os.chmod(cred_path, 0o600)
        try:
            import kaggle  # noqa: F401
            from kaggle.api.kaggle_api_extended import KaggleApi
            api = KaggleApi()
            api.authenticate()
            # 简单调一个轻量接口验证
            comps = api.competitions_list(page=1)
            return {"source": "kaggle", "ok": True, "message": f"认证成功，竞赛列表可访问（{len(comps)} 个）"}
        except ImportError:
            return {"source": "kaggle", "ok": False, "message": "kaggle SDK 未安装"}
        except Exception as e:
            return {"source": "kaggle", "ok": False, "message": f"认证失败: {e}"}
    finally:
        try:
            os.remove(cred_path)
        except Exception:
            pass


async def _test_huggingface(keys: Dict[str, str]) -> Dict[str, Any]:
    """HuggingFace 连通测试。无 token 测镜像 datasets API 可达；有 token 测 whoami。"""
    from ..core.proxy import smart_get
    token = (keys or {}).get("token", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    base = "https://hf-mirror.com"
    if token:
        # 有 token：调 whoami 验证
        try:
            resp = await smart_get(f"{base}/api/whoami-v2", headers=headers, timeout=15.0)
            if resp.status_code == 200:
                name = resp.json().get("name", "?")
                return {"source": "huggingface", "ok": True,
                        "message": f"Token 有效（镜像），用户: {name}"}
            if resp.status_code == 401:
                return {"source": "huggingface", "ok": False, "message": "Token 无效（HTTP 401）"}
            return {"source": "huggingface", "ok": False, "message": f"镜像 HTTP {resp.status_code}"}
        except Exception as e:
            return {"source": "huggingface", "ok": False, "message": f"镜像不可达: {e}"}
    # 无 token：测 datasets 搜索 API 可达性
    try:
        resp = await smart_get(f"{base}/api/datasets",
                                params={"search": "iris", "limit": 1}, timeout=15.0)
        if resp.status_code == 200:
            cnt = len(resp.json()) if isinstance(resp.json(), list) else 0
            return {"source": "huggingface", "ok": True,
                    "message": f"镜像连通（匿名，datasets API 可用，返回 {cnt} 个）"}
        return {"source": "huggingface", "ok": False, "message": f"镜像 HTTP {resp.status_code}"}
    except Exception as e:
        return {"source": "huggingface", "ok": False, "message": f"镜像不可达: {e}"}
