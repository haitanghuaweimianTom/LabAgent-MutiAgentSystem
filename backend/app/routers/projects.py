"""项目路由 - 管理项目（Project）的 CRUD"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..core.project_persistence import (
    list_projects,
    get_project,
    create_project,
    delete_project,
    rename_project,
    add_task_to_project,
    remove_task_from_project,
    sync_projects_with_outputs,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["项目管理"])


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""


class RenameProjectRequest(BaseModel):
    name: str


class AddTaskRequest(BaseModel):
    task_id: str


@router.get("")
async def get_projects() -> List[Dict[str, Any]]:
    """列出所有项目（与 outputs/ 目录同步）"""
    return list_projects()


@router.post("")
async def post_project(req: CreateProjectRequest) -> Dict[str, Any]:
    """创建新项目"""
    project = create_project(name=req.name, description=req.description)
    return {"success": True, "project": project}


@router.get("/{project_id}")
async def get_project_detail(project_id: str) -> Dict[str, Any]:
    """获取项目详情"""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
    return project


@router.put("/{project_id}")
async def put_project(project_id: str, req: CreateProjectRequest) -> Dict[str, Any]:
    """更新项目信息"""
    from ..core.project_persistence import update_project
    project = update_project(project_id, name=req.name, description=req.description)
    if not project:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
    return {"success": True, "project": project}


@router.delete("/{project_id}")
async def del_project(
    project_id: str,
    force: bool = Query(False, description="是否同时删除 outputs/ 目录下的文件"),
) -> Dict[str, Any]:
    """删除项目。默认仅从索引移除；force=True 时同时删除 outputs/ 目录。"""
    import shutil
    from ..core.paths import _PROJECT_ROOT

    success = delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")

    if force:
        outputs_root = _PROJECT_ROOT / "outputs"
        target_dir = outputs_root / project_id
        if project_id == "_global":
            raise HTTPException(status_code=400, detail="Cannot delete global project")
        if target_dir.exists():
            shutil.rmtree(target_dir)
            logger.info(f"强制删除项目目录: {target_dir}")

    return {"success": True, "message": f"项目 {project_id} 已删除", "force": force}


@router.post("/{project_id}/rename")
async def post_rename_project(project_id: str, req: RenameProjectRequest) -> Dict[str, Any]:
    """重命名项目"""
    project = rename_project(project_id, req.name)
    if not project:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
    return {"success": True, "project": project}


@router.post("/{project_id}/tasks")
async def post_add_task(project_id: str, req: AddTaskRequest) -> Dict[str, Any]:
    """将任务关联到项目"""
    success = add_task_to_project(project_id, req.task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
    return {"success": True}


@router.delete("/{project_id}/tasks/{task_id}")
async def del_remove_task(project_id: str, task_id: str) -> Dict[str, Any]:
    """从项目中移除任务关联"""
    success = remove_task_from_project(project_id, task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
    return {"success": True}


@router.post("/sync")
async def post_sync_projects() -> Dict[str, Any]:
    """手动同步 outputs/ 目录到项目列表"""
    projects = sync_projects_with_outputs()
    return {"success": True, "count": len(projects), "projects": projects}
