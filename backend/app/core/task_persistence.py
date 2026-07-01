"""
任务持久化模块
将任务数据保存到磁盘，重启后不丢失

Phase 2 扩展：增量 checkpoint 支持
- save_task_checkpoint(task_id, phase, step, payload)
- load_task_checkpoint(task_id) -> list of {phase, step, payload, saved_at}
- clear_task_checkpoints(task_id)

每个 Agent 完成后写一个 checkpoint；任务失败时，可从最近的 checkpoint
恢复，跳过已完成的步骤。
"""
import json
import shutil
import logging
import fcntl
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
    **extra: Any,
) -> None:
    """保存任务元数据（支持额外字段）"""
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
        "schema_version": extra.pop("schema_version", "2.0"),
        **extra,
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


# ====================================================================
# Phase 2：增量 checkpoint API
# ====================================================================

def _checkpoint_file(task_id: str) -> Path:
    """checkpoint 文件路径：``{task_id}_checkpoints.json``"""
    return TASK_DATA_DIR / f"{task_id}_checkpoints.json"


def save_task_checkpoint(
    task_id: str,
    phase: str,
    step: str,
    payload: Dict[str, Any],
) -> None:
    """保存一个增量 checkpoint（原子写 + 文件锁）。

    Args:
        task_id: 任务 ID。
        phase: 阶段名（``"phase1"`` / ``"phase2"`` / ``"peer_review"`` 等）。
        step: 步骤名（``"analyzer_agent"`` / ``"data_agent"`` / ``"research_agent"`` 等）。
        payload: 该步骤的完整输出 dict。

    写策略：
    - 每次写入一个 *完整* 的 checkpoint 列表（list of entries）
    - 同 (phase, step) 后写覆盖前写（避免重复）
    - 使用 :func:`_atomic_write_json` 保证原子性（先写 .tmp 再 rename）
    """
    _ensure_dir()
    file = _checkpoint_file(task_id)
    entry = {
        "phase": phase,
        "step": step,
        "payload": payload,
        "saved_at": datetime.now().isoformat(),
    }
    # 读旧列表，upsert
    existing = load_task_checkpoints(task_id)
    # 移除同 (phase, step) 的旧记录
    existing = [e for e in existing if not (e.get("phase") == phase and e.get("step") == step)]
    existing.append(entry)
    _atomic_write_json(file, {"task_id": task_id, "checkpoints": existing})
    logger.debug(f"Task {task_id} checkpoint saved: {phase}/{step}")


def load_task_checkpoints(task_id: str) -> List[Dict[str, Any]]:
    """加载任务的所有 checkpoint。**按写入顺序返回**。"""
    file = _checkpoint_file(task_id)
    if not file.exists():
        return []
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        return data.get("checkpoints", []) or []
    except Exception as e:
        logger.error(f"Failed to load checkpoints {task_id}: {e}")
        return []


def load_task_checkpoint(task_id: str, phase: str, step: str) -> Optional[Dict[str, Any]]:
    """加载某个特定 (phase, step) 的 checkpoint。"""
    for entry in load_task_checkpoints(task_id):
        if entry.get("phase") == phase and entry.get("step") == step:
            return entry
    return None


def clear_task_checkpoints(task_id: str) -> bool:
    """清空某任务的所有 checkpoint（任务完成时调用）。"""
    file = _checkpoint_file(task_id)
    if file.exists():
        try:
            file.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to clear checkpoints {task_id}: {e}")
            return False
    return True


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """原子写 JSON：先写 ``.tmp`` 再 rename，避免半写状态。"""
    _ensure_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        # 用文件锁防止并发写（仅 POSIX）
        with open(tmp, "w", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except (AttributeError, OSError):
                pass  # Windows / 非 POSIX 跳过
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.replace(path)
    except Exception:
        # 失败清理
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass
        raise


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
        # 排除非任务文件：消息、结果、检查点
        if any(suffix in f.name for suffix in ("_messages", "_result", "_checkpoints")):
            continue
        try:
            tasks.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    # 按创建时间倒序
    tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return tasks


def mark_interrupted_tasks() -> int:
    """启动时将之前标记为 running 的任务改为 interrupted（防止僵尸任务）"""
    count = 0
    for task in list_all_tasks():
        if task.get("status") == "running":
            tid = task.get("task_id")
            if tid:
                task["status"] = "interrupted"
                task["current_step"] = "系统重启，任务中断"
                task["completed_at"] = datetime.now().isoformat()
                try:
                    _task_file(tid).write_text(
                        json.dumps(task, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    count += 1
                    logger.info(f"Task {tid} marked as interrupted (system restart)")
                except Exception as e:
                    logger.error(f"Failed to mark {tid} as interrupted: {e}")
    return count


def delete_task(task_id: str) -> bool:
    """删除任务所有数据（包含 checkpoint、任务级知识库、reading artifacts、输出产物）。"""
    deleted = False

    # 先读取元数据以获取项目名
    meta_file = TASK_DATA_DIR / f"{task_id}.json"
    project_name = None
    try:
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            project_name = meta.get("project_name") or task_id
    except Exception as e:
        logger.debug(f"读取任务元数据失败: {e}")

    for suffix in ["", "_messages", "_result", "_checkpoints"]:
        file = TASK_DATA_DIR / f"{task_id}{suffix}.json"
        if file.exists():
            try:
                file.unlink()
                deleted = True
            except Exception as e:
                logger.error(f"Failed to delete {file}: {e}")

    # 清理任务级论文知识库（如果还存在）
    try:
        from .knowledge_manager import get_knowledge_manager
        km = get_knowledge_manager()
        for kb in km.list_custom_providers():  # 兼容：只清理名字匹配的
            pass
        # 直接通过存储查找
        for base_id in list(km._bases.keys()):
            base = km._bases[base_id]
            if base.name == f"task_kb_{task_id}":
                km.delete_base(base_id)
                logger.info(f"删除任务级知识库: {base_id}")
                deleted = True
    except Exception as e:
        logger.debug(f"清理任务级知识库失败（可能不存在）: {e}")

    # 清理项目目录下的 references/ 和 reading/ 子目录
    try:
        from .paths import _PROJECT_ROOT
        for project_dir in _PROJECT_ROOT.glob("outputs/*"):
            for sub in ("references", "reading"):
                target = project_dir / sub
                if target.exists():
                    import shutil
                    for f in target.glob(f"{task_id}_*"):
                        try:
                            f.unlink()
                            deleted = True
                        except Exception:
                            pass
    except Exception as e:
        logger.debug(f"清理项目 artifacts 失败: {e}")

    # 清理任务输出产物目录（PDF、LaTeX、代码、图表等）
    try:
        from .paths import _PROJECT_ROOT
        import shutil
        output_project = project_name or task_id
        outputs_root = _PROJECT_ROOT / "outputs"

        # 1) 删除 task_ 前缀的专属输出目录
        if output_project.startswith("task_"):
            target_dir = outputs_root / output_project
            if target_dir.exists():
                shutil.rmtree(target_dir)
                logger.info(f"删除任务输出目录: {target_dir}")
                deleted = True

        # 2) 清理项目目录下的 task 专属子文件夹（output/<task_id>/ 等）
        for proj_dir in outputs_root.iterdir():
            if not proj_dir.is_dir() or proj_dir.name.startswith(".") or proj_dir.name == "_global":
                continue
            for sub in ("output", "data"):
                task_sub = proj_dir / sub / task_id
                if task_sub.exists():
                    shutil.rmtree(task_sub)
                    logger.info(f"清理项目 {proj_dir.name} 下的任务子目录: {task_sub}")
                    deleted = True
    except Exception as e:
        logger.debug(f"清理任务输出目录失败: {e}")

    return deleted
