"""环境管理路由 —— 创建/删除/激活 conda 或 venv 环境，安装依赖。"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.environment_manager import (
    EnvironmentManager,
    get_environment_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/environments", tags=["环境管理"])


class CreateEnvRequest(BaseModel):
    backend: str
    name: str
    python_version: str = "3.11"


class InstallRequest(BaseModel):
    backend: str
    name: str
    requirements_path: Optional[str] = None


class RunCommandRequest(BaseModel):
    backend: str
    name: str
    command: List[str]
    cwd: Optional[str] = None


class ActivateRequest(BaseModel):
    backend: str
    name: str


def _get_manager() -> EnvironmentManager:
    return get_environment_manager()


@router.get("/backends")
async def list_backends() -> List[str]:
    """列出当前系统可用的环境后端。"""
    return _get_manager().available_backends()


@router.get("")
async def list_environments() -> List[Dict[str, Any]]:
    """列出所有可管理的环境。"""
    return [e.to_dict() for e in _get_manager().list_environments()]


@router.get("/active")
async def get_active_environment() -> Dict[str, Any]:
    """获取当前激活的环境。"""
    return _get_manager().get_active() or {"name": None, "backend": None}


@router.post("")
async def create_environment(req: CreateEnvRequest) -> Dict[str, Any]:
    """创建新环境。"""
    manager = _get_manager()
    if req.backend not in manager.available_backends():
        raise HTTPException(status_code=400, detail=f"后端不可用: {req.backend}")

    success = manager.create(req.backend, req.name, req.python_version)
    if not success:
        raise HTTPException(status_code=500, detail="环境创建失败")

    return {
        "name": req.name,
        "backend": req.backend,
        "python_version": req.python_version,
        "status": "created",
    }


@router.delete("/{backend}/{name}")
async def delete_environment(backend: str, name: str) -> Dict[str, Any]:
    """删除环境。"""
    manager = _get_manager()
    if backend not in manager.available_backends():
        raise HTTPException(status_code=400, detail=f"后端不可用: {backend}")

    success = manager.delete(backend, name)
    if not success:
        raise HTTPException(status_code=500, detail="环境删除失败")

    return {"name": name, "backend": backend, "status": "deleted"}


@router.post("/install")
async def install_requirements(req: InstallRequest) -> Dict[str, Any]:
    """在环境中安装依赖。"""
    manager = _get_manager()
    if req.backend not in manager.available_backends():
        raise HTTPException(status_code=400, detail=f"后端不可用: {req.backend}")

    if req.requirements_path:
        path = Path(req.requirements_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"requirements 文件不存在: {req.requirements_path}")
        success = manager.install_requirements(req.backend, req.name, path)
    else:
        success = manager.install_project_requirements(req.backend, req.name)

    if not success:
        raise HTTPException(status_code=500, detail="依赖安装失败")

    return {"name": req.name, "backend": req.backend, "status": "installed"}


@router.post("/run")
async def run_command(req: RunCommandRequest) -> Dict[str, Any]:
    """在环境中运行命令。"""
    manager = _get_manager()
    if req.backend not in manager.available_backends():
        raise HTTPException(status_code=400, detail=f"后端不可用: {req.backend}")

    cwd = Path(req.cwd) if req.cwd else None
    success, stdout, stderr = manager.run_command(req.backend, req.name, req.command, cwd=cwd)
    return {
        "name": req.name,
        "backend": req.backend,
        "success": success,
        "stdout": stdout,
        "stderr": stderr,
    }


@router.post("/activate")
async def activate_environment(req: ActivateRequest) -> Dict[str, Any]:
    """设置当前激活环境。"""
    manager = _get_manager()
    if req.backend not in manager.available_backends():
        raise HTTPException(status_code=400, detail=f"后端不可用: {req.backend}")

    success = manager.set_active(req.backend, req.name)
    if not success:
        raise HTTPException(status_code=400, detail="激活失败，环境不存在")

    return {"name": req.name, "backend": req.backend, "status": "activated"}
