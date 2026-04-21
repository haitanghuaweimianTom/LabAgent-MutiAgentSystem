"""
任务持久化模块
将任务数据保存到磁盘，重启后不丢失
"""
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from .paths import get_task_data_dir

logger = logging.getLogger(__name__)

# 任务存储目录（使用统一路径管理）
TASK_DATA_DIR: Path = get_task_data_dir()


def _ensure_dir():
    TASK_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _task_file(task_id: str) -> Path:
    return TASK_DATA_DIR / f"{task_id}.json"


def save_task_metadata(
    task_id: str,
    problem_text: str,
    status: str,
    created_at: str,
    completed_at: Optional[str] = None,
    error: Optional[str] = None,
    total_steps: int = 0,
    progress: int = 0,
    current_step: str = "",
) -> None:
    """保存任务元数据"""
    _ensure_dir()
    file = _task_file(task_id)

    # 如果文件已存在，合并数据
    existing = {}
    if file.exists():
        try:
            existing = json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            pass

    data = {
        **existing,
        "task_id": task_id,
        "problem_text": problem_text,
        "problem_preview": problem_text[:200].replace("\n", " ").strip() if problem_text else "",
        "status": status,
        "created_at": created_at,
        "completed_at": completed_at,
        "error": error,
        "total_steps": total_steps,
        "progress": progress,
        "current_step": current_step,
        "updated_at": datetime.now().isoformat(),
    }

    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Task metadata saved: {task_id}")


def save_task_messages(task_id: str, messages: List[Dict[str, Any]]) -> None:
    """保存任务聊天消息"""
    _ensure_dir()
    file = TASK_DATA_DIR / f"{task_id}_messages.json"
    file.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    logger.info(f"Task messages saved: {task_id} ({len(messages)} msgs)")


def save_task_result(task_id: str, result: Dict[str, Any]) -> None:
    """保存任务最终结果"""
    _ensure_dir()
    file = TASK_DATA_DIR / f"{task_id}_result.json"
    file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    logger.info(f"Task result saved: {task_id}")


def load_task_metadata(task_id: str) -> Optional[Dict[str, Any]]:
    """加载任务元数据"""
    file = _task_file(task_id)
    if not file.exists():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load task metadata {task_id}: {e}")
        return None


def load_task_messages(task_id: str) -> List[Dict[str, Any]]:
    """加载任务聊天消息"""
    file = TASK_DATA_DIR / f"{task_id}_messages.json"
    if not file.exists():
        return []
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load task messages {task_id}: {e}")
        return []


def load_task_result(task_id: str) -> Optional[Dict[str, Any]]:
    """加载任务结果"""
    file = TASK_DATA_DIR / f"{task_id}_result.json"
    if not file.exists():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load task result {task_id}: {e}")
        return None


def list_all_tasks() -> List[Dict[str, Any]]:
    """列出所有任务（按时间倒序）"""
    _ensure_dir()
    tasks = []
    for f in TASK_DATA_DIR.glob("task_*.json"):
        if "_messages" not in f.name and "_result" not in f.name:
            try:
                tasks.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
    # 按创建时间倒序
    tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return tasks


def delete_task(task_id: str) -> bool:
    """删除任务所有数据"""
    deleted = False
    for suffix in ["", "_messages", "_result"]:
        file = TASK_DATA_DIR / f"{task_id}{suffix}.json"
        if file.exists():
            try:
                file.unlink()
                deleted = True
            except Exception as e:
                logger.error(f"Failed to delete {file}: {e}")
    return deleted
