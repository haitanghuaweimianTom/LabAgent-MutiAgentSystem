"""v5.3.0 数据目录辅助函数

为 Phase 1/2 提供：
- SelfCollectedMeta：单条自收集元数据
- read_self_collected_index / append_self_collected_index：操作 _index.json
- list_project_files：跨 user_upload + self_collected 列出文件
"""
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.paths import get_project_data_subdir

logger = logging.getLogger(__name__)


@dataclass
class SelfCollectedMeta:
    """单条自收集文件的元数据"""
    url: str
    filename: Optional[str] = None
    size: int = 0
    downloaded_at: int = 0
    content_type: str = ""
    source_query: str = ""
    http_status: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# 在文件名中跳过这些元数据文件
_META_FILES = {"_index.json"}


def read_self_collected_index(project_name: Optional[str]) -> List[Dict[str, Any]]:
    """读取 self_collected/_index.json；不存在返回空列表。"""
    target = get_project_data_subdir(project_name, "self_collected")
    index_path = target / "_index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return data
    except Exception as e:
        logger.warning(f"[data_directory] 读取 _index.json 失败: {e}")
        return []


def write_self_collected_index(
    project_name: Optional[str], items: List[Dict[str, Any]]
) -> Path:
    """写 _index.json（覆盖）。"""
    target = get_project_data_subdir(project_name, "self_collected")
    index_path = target / "_index.json"
    index_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return index_path


def append_self_collected_index(
    project_name: Optional[str],
    new_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """追加新的元数据条目，返回合并后的全量列表。"""
    existing = read_self_collected_index(project_name)
    existing.extend(new_items)
    write_self_collected_index(project_name, existing)
    return existing


def list_project_files(
    project_name: Optional[str],
    source: str = "both",
) -> List[Dict[str, Any]]:
    """列出项目下的文件。

    Args:
        project_name: 项目名（None = 全局）
        source: 'user_upload' / 'self_collected' / 'both'

    Returns:
        [{"name", "size", "type", "modified", "source", "meta?"}, ...]
    """
    items: List[Dict[str, Any]] = []

    sources: List[str]
    if source == "both":
        sources = ["user_upload", "self_collected"]
    elif source in ("user_upload", "self_collected"):
        sources = [source]
    else:
        raise ValueError(f"invalid source: {source!r}")

    # 读 self_collected 元数据索引（filename -> meta）
    self_index: Dict[str, Dict[str, Any]] = {}
    if "self_collected" in sources:
        for entry in read_self_collected_index(project_name):
            fname = entry.get("filename")
            if fname:
                self_index[fname] = entry

    for src in sources:
        try:
            d = get_project_data_subdir(project_name, src)
        except Exception as e:
            logger.warning(f"[data_directory] 无法访问 {src}: {e}")
            continue
        for f in d.iterdir():
            if f.name.startswith("."):
                continue
            if f.name in _META_FILES:
                continue
            if f.is_file():
                item: Dict[str, Any] = {
                    "name": f.name,
                    "size": f.stat().st_size,
                    "type": f.suffix,
                    "modified": int(f.stat().st_mtime * 1000),
                    "source": src,
                }
                if src == "self_collected" and f.name in self_index:
                    meta = self_index[f.name]
                    item["meta"] = {
                        "url": meta.get("url"),
                        "downloaded_at": meta.get("downloaded_at"),
                        "content_type": meta.get("content_type"),
                        "source_query": meta.get("source_query"),
                        "http_status": meta.get("http_status"),
                        "error": meta.get("error"),
                    }
                items.append(item)
    # 按 source + name 排序
    items.sort(key=lambda x: (x.get("source", ""), x.get("name", "")))
    return items