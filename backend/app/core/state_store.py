"""LangGraph State 大对象外部存储。

目标：把 results 中的 Agent 输出从 ``TaskState`` 中剥离，state 里只保留引用标记，
避免 LangGraph 在节点间传递时反复浅/深拷贝大 dict。

每个任务对应一个 ``results`` dict，key 为 agent_name，value 为实际输出。
state 中保留 ``results`` 字段，但只存放 ``{"agent_name": "__ref__agent_name"}`` 形式的占位，
节点通过 ``TaskResultStore`` 读写真实数据。
"""
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent.parent.parent / "data" / "langgraph_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

REF_PREFIX = "__ref__"


def _ref_key(agent_name: str) -> str:
    return f"{REF_PREFIX}{agent_name}"


def _is_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(REF_PREFIX)


class TaskResultStore:
    """按 task_id 存储 Agent 输出；线程安全；使用原子写。"""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base_dir = base_dir or RESULTS_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, task_id: str) -> Path:
        # task_id 可能带 task_ 前缀，直接作为文件名的一部分
        safe_id = task_id.replace("/", "_").replace("\\", "_")
        return self._base_dir / f"{safe_id}.json"

    def _load(self, task_id: str) -> Dict[str, Any]:
        path = self._path(task_id)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception as e:
            logger.warning(f"加载 task results 失败 {task_id}: {e}")
            return {}

    def _save(self, task_id: str, results: Dict[str, Any]) -> None:
        path = self._path(task_id)
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), "utf-8")
            tmp.replace(path)
        except Exception as e:
            logger.warning(f"保存 task results 失败 {task_id}: {e}")

    def set(self, task_id: str, agent_name: str, output: Any) -> None:
        """写入/更新某个 Agent 的输出。"""
        with self._lock:
            results = self._load(task_id)
            results[agent_name] = output
            self._save(task_id, results)

    def get(self, task_id: str, agent_name: str, default: Any = None) -> Any:
        """读取某个 Agent 的输出。"""
        return self._load(task_id).get(agent_name, default)

    def get_all(self, task_id: str) -> Dict[str, Any]:
        """读取任务全部 Agent 输出。"""
        return self._load(task_id)

    def set_many(self, task_id: str, outputs: Dict[str, Any]) -> None:
        """批量写入。"""
        with self._lock:
            results = self._load(task_id)
            results.update(outputs)
            self._save(task_id, results)

    def delete(self, task_id: str) -> None:
        """删除任务结果文件。"""
        path = self._path(task_id)
        try:
            if path.exists():
                path.unlink()
        except Exception as e:
            logger.warning(f"删除 task results 失败 {task_id}: {e}")


# 全局单例
_task_result_store: Optional[TaskResultStore] = None
_store_lock = threading.Lock()


def get_task_result_store() -> TaskResultStore:
    global _task_result_store
    if _task_result_store is None:
        with _store_lock:
            if _task_result_store is None:
                _task_result_store = TaskResultStore()
    return _task_result_store
