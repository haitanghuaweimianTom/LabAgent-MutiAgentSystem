"""
项目持久化模块
将项目数据保存到磁盘，与 outputs/ 目录下的文件夹同步
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from .paths import get_project_base_dir

logger = logging.getLogger(__name__)

# 项目索引文件（保存在 backend/data/projects.json）
_PROJECT_INDEX_FILE: Optional[Path] = None


def _get_project_index_file() -> Path:
    global _PROJECT_INDEX_FILE
    if _PROJECT_INDEX_FILE is None:
        from .paths import _BACKEND_ROOT
        _PROJECT_INDEX_FILE = _BACKEND_ROOT / "data" / "projects.json"
        _PROJECT_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    return _PROJECT_INDEX_FILE


def _load_index() -> Dict[str, Any]:
    """加载项目索引"""
    file = _get_project_index_file()
    if file.exists():
        try:
            return json.loads(file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load project index: {e}")
    return {"projects": [], "version": 1}


def _save_index(index: Dict[str, Any]) -> None:
    """保存项目索引"""
    file = _get_project_index_file()
    file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _scan_outputs_dirs() -> List[Dict[str, Any]]:
    """扫描 outputs/ 目录下的所有文件夹作为项目"""
    from .paths import _PROJECT_ROOT
    outputs_dir = _PROJECT_ROOT / "outputs"
    projects = []
    if outputs_dir.exists():
        for d in outputs_dir.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                # 获取目录的创建时间
                stat = d.stat()
                created_at = stat.st_mtime
                projects.append({
                    "id": d.name,
                    "name": d.name,
                    "path": str(d),
                    "created_at": created_at,
                    "updated_at": stat.st_mtime,
                    "task_ids": [],
                    "auto_detected": True,
                })
    return projects


def sync_projects_with_outputs() -> List[Dict[str, Any]]:
    """
    将 outputs/ 目录下的文件夹同步到项目索引中。
    保留已有项目的元数据，添加新检测到的目录。
    """
    index = _load_index()
    existing = {p["id"]: p for p in index.get("projects", [])}
    scanned = _scan_outputs_dirs()

    scanned_ids = {sp["id"] for sp in scanned}
    merged = {}

    # 只保留仍然存在于 outputs/ 目录下的项目
    for pid, p in existing.items():
        if pid in scanned_ids:
            merged[pid] = p
        else:
            logger.info(f"Project {pid} no longer exists in outputs/, removing from index")

    # 添加/更新扫描到的项目
    for sp in scanned:
        pid = sp["id"]
        if pid in merged:
            # 更新路径和时间戳，保留其他元数据
            merged[pid]["path"] = sp["path"]
            merged[pid]["updated_at"] = sp["updated_at"]
            merged[pid]["auto_detected"] = True
        else:
            merged[pid] = sp

    project_list = list(merged.values())
    # 按 updated_at 倒序排列
    project_list.sort(key=lambda x: x.get("updated_at", 0), reverse=True)

    index["projects"] = project_list
    _save_index(index)
    logger.info(f"Project sync complete: {len(project_list)} projects")
    return project_list


def list_projects() -> List[Dict[str, Any]]:
    """列出所有项目（优先从索引，同时同步 outputs 目录）"""
    return sync_projects_with_outputs()


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """获取单个项目信息"""
    projects = list_projects()
    for p in projects:
        if p["id"] == project_id:
            return p
    return None


def create_project(name: str, description: str = "") -> Dict[str, Any]:
    """创建新项目，同时在 outputs/ 下创建目录"""
    import re
    # 生成安全的目录名
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', name).strip()
    if not safe_name:
        safe_name = "untitled_project"

    # 确保唯一性
    base_name = safe_name
    counter = 1
    while get_project(safe_name):
        safe_name = f"{base_name}_{counter}"
        counter += 1

    # 创建目录
    project_dir = get_project_base_dir(safe_name)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "data").mkdir(exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)

    now = datetime.now().timestamp()
    project = {
        "id": safe_name,
        "name": name,
        "description": description,
        "path": str(project_dir),
        "created_at": now,
        "updated_at": now,
        "task_ids": [],
        "auto_detected": False,
    }

    index = _load_index()
    index["projects"] = [p for p in index.get("projects", []) if p["id"] != safe_name]
    index["projects"].insert(0, project)
    _save_index(index)
    logger.info(f"Project created: {safe_name}")
    return project


def update_project(project_id: str, **fields) -> Optional[Dict[str, Any]]:
    """更新项目信息"""
    index = _load_index()
    for p in index.get("projects", []):
        if p["id"] == project_id:
            for k, v in fields.items():
                if v is not None:
                    p[k] = v
            p["updated_at"] = datetime.now().timestamp()
            _save_index(index)
            return p
    return None


def delete_project(project_id: str) -> bool:
    """删除项目（只删除索引记录，不删除 outputs/ 目录，防止误删数据）"""
    index = _load_index()
    original_len = len(index.get("projects", []))
    index["projects"] = [p for p in index.get("projects", []) if p["id"] != project_id]
    if len(index["projects"]) < original_len:
        _save_index(index)
        logger.info(f"Project removed from index: {project_id}")
        return True
    return False


def add_task_to_project(project_id: str, task_id: str) -> bool:
    """将任务关联到项目"""
    index = _load_index()
    for p in index.get("projects", []):
        if p["id"] == project_id:
            if task_id not in p.get("task_ids", []):
                p.setdefault("task_ids", []).append(task_id)
                p["updated_at"] = datetime.now().timestamp()
                _save_index(index)
            return True
    return False


def remove_task_from_project(project_id: str, task_id: str) -> bool:
    """从项目中移除任务关联"""
    index = _load_index()
    for p in index.get("projects", []):
        if p["id"] == project_id:
            if task_id in p.get("task_ids", []):
                p["task_ids"] = [t for t in p["task_ids"] if t != task_id]
                p["updated_at"] = datetime.now().timestamp()
                _save_index(index)
            return True
    return False


def rename_project(project_id: str, new_name: str) -> Optional[Dict[str, Any]]:
    """重命名项目（只改 name 字段，不改目录名/ID，避免路径断裂）"""
    return update_project(project_id, name=new_name)
