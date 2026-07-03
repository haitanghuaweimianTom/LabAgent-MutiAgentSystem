"""环境管理路由 —— 创建/删除/激活 conda 或 venv 环境，安装依赖。"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from ..core.environment_manager import (
    EnvironmentManager,
    get_environment_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/environments", tags=["环境管理"])

# 可选 API Key 认证（读取 MATHMODEL_API_KEY 环境变量）
_REQUIRED_API_KEY = os.environ.get("MATHMODEL_API_KEY", "")


async def _require_api_key(x_api_key: str = Header(default="", alias="X-API-Key")):
    if _REQUIRED_API_KEY and x_api_key != _REQUIRED_API_KEY:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="未授权：X-API-Key 无效或缺失")

# 允许执行的命令白名单（仅限环境管理相关操作）
_ALLOWED_COMMAND_BASENAMES = {
    "python", "python3", "pip", "pip3",
    "conda", "mamba",
    "node", "npm", "npx",
    "latexmk", "pdflatex", "xelatex", "bibtex",
}


def _validate_command(command: List[str]) -> None:
    """校验命令是否在白名单内。"""
    if not command:
        raise HTTPException(status_code=400, detail="命令不能为空")
    cmd_base = Path(command[0]).name
    if cmd_base not in _ALLOWED_COMMAND_BASENAMES:
        raise HTTPException(
            status_code=403,
            detail=f"不允许执行命令: {cmd_base}。允许的命令: {', '.join(sorted(_ALLOWED_COMMAND_BASENAMES))}",
        )
    # 阻止 shell 元字符
    for arg in command:
        if any(c in arg for c in (";", "|", "&", "$", "`", "(", ")", "{", "}", "\n")):
            raise HTTPException(status_code=400, detail=f"命令参数包含非法字符: {arg}")


def _validate_cwd(cwd: Optional[str], project_root: Optional[Path] = None) -> Optional[Path]:
    """校验工作目录在允许范围内。"""
    if not cwd:
        return None
    path = Path(cwd).resolve()
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"工作目录不存在: {cwd}")
    # 限制在项目目录或 /tmp 下
    allowed_roots = [Path("/tmp").resolve(), Path("/home").resolve()]
    if project_root:
        allowed_roots.append(project_root.resolve())
    if not any(str(path).startswith(str(r)) for r in allowed_roots):
        raise HTTPException(status_code=403, detail=f"工作目录不在允许范围内: {cwd}")
    return path


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
        path = Path(req.requirements_path).resolve()
        # 校验 requirements 文件路径在允许范围内
        allowed_prefixes = [Path("/tmp").resolve(), Path("/home").resolve()]
        if not any(str(path).startswith(str(p)) for p in allowed_prefixes):
            raise HTTPException(status_code=403, detail="requirements 文件路径不在允许范围内")
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"requirements 文件不存在: {req.requirements_path}")
        success = manager.install_requirements(req.backend, req.name, path)
    else:
        success = manager.install_project_requirements(req.backend, req.name)

    if not success:
        raise HTTPException(status_code=500, detail="依赖安装失败")

    return {"name": req.name, "backend": req.backend, "status": "installed"}


@router.post("/run", dependencies=[Depends(_require_api_key)])
async def run_command(req: RunCommandRequest) -> Dict[str, Any]:
    """在环境中运行命令（仅限白名单命令）。"""
    manager = _get_manager()
    if req.backend not in manager.available_backends():
        raise HTTPException(status_code=400, detail=f"后端不可用: {req.backend}")

    _validate_command(req.command)
    cwd = _validate_cwd(req.cwd)

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
