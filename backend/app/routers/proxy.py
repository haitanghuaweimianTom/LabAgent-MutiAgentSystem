"""网络代理管理路由。

供前端「数据源 / 代理」面板调用：
- GET  /proxy/status   查看自动检测到的代理 + 各开关
- POST /proxy          设置手动代理 / 全局开关
- DELETE /proxy        清除手动代理
- POST /proxy/test     测试代理连通性

代理检测逻辑见 core.proxy（跨平台：env/gsettings/scutil/registry + 手动覆盖）。
注意：只对"取数据"路径注入代理，绝不影响 LLM（国产 provider）调用。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..core.proxy import (
    clear_manual_proxy,
    get_proxy_status,
    set_proxy_settings,
    test_proxy,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proxy", tags=["proxy"])


class ProxySettingsUpdate(BaseModel):
    manual_proxy: Optional[str] = None
    manual_enabled: Optional[bool] = None
    use_proxy: Optional[bool] = None


@router.get("/status")
async def status() -> Dict[str, Any]:
    return get_proxy_status()


@router.post("")
async def update_settings(req: ProxySettingsUpdate) -> Dict[str, Any]:
    return set_proxy_settings(
        manual_proxy=req.manual_proxy,
        manual_enabled=req.manual_enabled,
        use_proxy=req.use_proxy,
    )


@router.delete("")
async def clear_manual() -> Dict[str, Any]:
    return clear_manual_proxy()


@router.post("/test")
async def test() -> Dict[str, Any]:
    return await test_proxy()
