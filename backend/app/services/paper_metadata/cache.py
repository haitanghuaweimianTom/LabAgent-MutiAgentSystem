"""论文元数据缓存（Phase 5）。

动机：``PaperMetadataProvider`` 每次 enrich 都会调外部 API（Semantic Scholar / Crossref），
重复 enrich 同一 arxiv_id 集合时会浪费 API 配额 + 增加延迟。

本模块提供 :class:`MetadataCache`：
- 进程内 LRU（防止单次大 enrich 撑爆内存）
- 磁盘 JSON 持久化（默认 ``backend/data/paper_metadata_cache.json``）
- TTL 默认 7 天，过期重新查
- 失败写入 *不* 持久化（避免把网络错误状态缓存下来）
- ``warmup(top_n)`` 预热：启动时把最近访问的 N 条加载到内存

严格控制幻觉：缓存只存 *实际收到* 的元数据字段，不补默认值。
"""
from __future__ import annotations
import json
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

from .base import PaperMetadataProvider

logger = logging.getLogger(__name__)


class MetadataCache:
    """论文元数据缓存：内存 LRU + 磁盘 JSON + TTL。"""

    DEFAULT_TTL_SECONDS = 7 * 24 * 3600  # 7 days
    DEFAULT_MAX_ENTRIES = 1000

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ):
        self._cache_path = cache_path
        self._ttl = ttl_seconds
        self._max = max_entries
        self._entries: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        if cache_path is not None:
            self._load_from_disk()

    # ----------------- 基本 CRUD -----------------

    def get(self, arxiv_id: str, source: str = "default") -> Optional[Dict[str, Any]]:
        """获取缓存项；过期或缺失返回 None。"""
        key = self._key(arxiv_id, source)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            if self._is_expired(entry):
                # 过期删除
                del self._entries[key]
                self._misses += 1
                return None
            # 命中 + LRU 提升
            self._entries.move_to_end(key)
            self._hits += 1
            return dict(entry.get("data", {}))

    def put(
        self,
        arxiv_id: str,
        data: Dict[str, Any],
        source: str = "default",
        persist: bool = True,
    ) -> None:
        """写入缓存。``persist=False`` 时仅写内存（用于临时数据 / 测试）。"""
        if not data:
            return  # 不缓存空数据
        key = self._key(arxiv_id, source)
        with self._lock:
            # 已存在则更新
            self._entries[key] = {
                "arxiv_id": arxiv_id,
                "source": source,
                "data": dict(data),
                "saved_at": time.time(),
            }
            self._entries.move_to_end(key)
            # 超过容量淘汰最早的
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)
            if persist:
                self._save_to_disk_locked()

    def invalidate(self, arxiv_id: str, source: str = "default") -> bool:
        key = self._key(arxiv_id, source)
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                self._save_to_disk_locked()
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._hits = 0
            self._misses = 0
            if self._cache_path is not None:
                self._save_to_disk_locked()

    # ----------------- 批量接口（与 Provider 对接） -----------------

    async def enrich_with_cache(
        self,
        provider: PaperMetadataProvider,
        arxiv_ids: list,
        source: str = "default",
    ) -> Dict[str, Dict[str, Any]]:
        """批量 enrich：先查缓存，缺失的项再走 Provider。"""
        if not arxiv_ids:
            return {}
        results: Dict[str, Dict[str, Any]] = {}
        to_fetch = []
        for aid in arxiv_ids:
            cached = self.get(aid, source=source)
            if cached is not None:
                results[aid] = cached
            else:
                to_fetch.append(aid)

        if to_fetch:
            try:
                fetched = await provider.enrich_papers(to_fetch)
                for aid, meta in (fetched or {}).items():
                    if isinstance(meta, dict) and meta:
                        results[aid] = meta
                        self.put(aid, meta, source=source)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Provider {provider.name} enrich 失败: {exc}")
        return results

    # ----------------- 预热 -----------------

    def warmup(self, top_n: int = 20) -> int:
        """预热：把磁盘中最近 saved_at 的 top_n 条加载到内存（已经是 _load_from_disk 的别名）。"""
        with self._lock:
            items = sorted(
                self._entries.items(),
                key=lambda kv: kv[1].get("saved_at", 0),
                reverse=True,
            )[:top_n]
            for k, _ in items:
                self._entries.move_to_end(k)
        return len(items)

    # ----------------- 统计 -----------------

    def stats(self) -> Dict[str, Any]:
        from ...core.paths import _PROJECT_ROOT
        with self._lock:
            total = len(self._entries)
            hits, misses = self._hits, self._misses
            ratio = (hits / (hits + misses)) if (hits + misses) > 0 else 0.0
            cache_path_rel = None
            if self._cache_path:
                try:
                    cache_path_rel = str(self._cache_path.relative_to(_PROJECT_ROOT))
                except ValueError:
                    cache_path_rel = str(self._cache_path)
            return {
                "entries": total,
                "hits": hits,
                "misses": misses,
                "hit_ratio": round(ratio, 3),
                "ttl_seconds": self._ttl,
                "max_entries": self._max,
                "cache_path": cache_path_rel,
            }

    # ----------------- 内部 -----------------

    @staticmethod
    def _key(arxiv_id: str, source: str) -> str:
        return f"{source}|{arxiv_id}"

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        saved = entry.get("saved_at", 0)
        if not saved:
            return True
        return (time.time() - saved) > self._ttl

    def _load_from_disk(self) -> None:
        if not self._cache_path or not self._cache_path.exists():
            return
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to load cache {self._cache_path}: {exc}")
            return
        items = data.get("entries", {}) or {}
        with self._lock:
            for k, v in items.items():
                if isinstance(v, dict) and v.get("data"):
                    self._entries[k] = v
                    if len(self._entries) >= self._max:
                        break
        logger.info(f"MetadataCache loaded {len(self._entries)} entries from {self._cache_path}")

    def _save_to_disk_locked(self) -> None:
        # _save_to_disk_locked 假定 self._lock 已持有
        if not self._cache_path:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "saved_at": time.time(),
                "entries": dict(self._entries),
            }
            tmp = self._cache_path.with_suffix(self._cache_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._cache_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to save cache {self._cache_path}: {exc}")


# ==================== 全局实例 ====================

_global_cache: Optional[MetadataCache] = None
_global_lock = threading.Lock()


def get_metadata_cache(
    cache_path: Optional[Path] = None,
    ttl_seconds: int = MetadataCache.DEFAULT_TTL_SECONDS,
) -> MetadataCache:
    """获取全局缓存实例。``cache_path=None`` 时用默认 ``data/paper_metadata_cache.json``。"""
    global _global_cache
    if _global_cache is None:
        with _global_lock:
            if _global_cache is None:
                from ...core.paths import get_data_dir
                if cache_path is None:
                    cache_path = get_data_dir() / "paper_metadata_cache.json"
                _global_cache = MetadataCache(
                    cache_path=cache_path, ttl_seconds=ttl_seconds,
                )
    return _global_cache
