"""多库知识库管理器

参照 cherry-studio 的 KnowledgeService 设计，
支持多个独立知识库，每个库有自己的文档和向量索引。
"""

import json
import logging
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 项目根目录
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_KB_DIR = _PROJECT_ROOT / "data" / "knowledge_bases"
_KB_INDEX_FILE = _KB_DIR / "index.json"
_KB_FILES_DIR = _PROJECT_ROOT / "data" / "knowledge_files"


class FileMetadata(BaseModel):
    """文件元数据（参照 cherry-studio FileMetadata）"""
    name: str
    size: int
    ext: str = ""
    path: str = ""


class KnowledgeItem(BaseModel):
    """知识库条目（参照 cherry-studio KnowledgeItem）"""
    id: str
    type: Literal["file", "note", "url", "sitemap", "directory"]
    content: Union[str, FileMetadata] = Field(...)
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    processingStatus: Optional[Literal["pending", "processing", "completed", "failed"]] = None
    processingProgress: Optional[float] = None
    processingError: Optional[str] = None
    created_at: int = 0
    updated_at: int = 0


class KnowledgeBaseConfig(BaseModel):
    """知识库配置"""
    id: str
    name: str
    description: str = ""
    model: Optional[str] = None
    items: List[KnowledgeItem] = Field(default_factory=list)
    created_at: int = 0
    updated_at: int = 0
    chunkSize: int = 512
    chunkOverlap: int = 128
    embedding_model: Optional[Dict[str, Any]] = None  # {"type": "openai", ...}
    reranker_model: Optional[Dict[str, Any]] = None   # {"type": "cross-encoder", ...}
    # v5.3.0: 两级 KB scope
    # - "global": 全局公共，所有项目可用（默认）
    # - "project": 项目私有，仅指定项目可用
    scope: Literal["global", "project"] = "global"
    project_name: Optional[str] = None  # scope="project" 时必填


class KnowledgeManager:
    """多库知识库管理器"""

    def __init__(self):
        self._bases: Dict[str, KnowledgeBaseConfig] = {}
        self._kb_instances: Dict[str, Any] = {}  # base_id -> KnowledgeBase (TF-IDF)
        self._ensure_dirs()
        self._load_index()

    def _ensure_dirs(self) -> None:
        _KB_DIR.mkdir(parents=True, exist_ok=True)
        _KB_FILES_DIR.mkdir(parents=True, exist_ok=True)

    def _base_data_file(self, base_id: str) -> Path:
        return _KB_DIR / f"{base_id}.json"

    def _load_base(self, base_id: str) -> Optional[KnowledgeBaseConfig]:
        """从磁盘加载单个知识库的完整数据（含 items）"""
        filepath = self._base_data_file(base_id)
        if not filepath.exists():
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return KnowledgeBaseConfig(**data)
        except Exception as e:
            logger.warning(f"[KnowledgeManager] 加载知识库 {base_id} 失败: {e}")
            return None

    def _load_index(self) -> None:
        """加载知识库索引"""
        if not _KB_INDEX_FILE.exists():
            # 尝试迁移旧版知识库
            self._migrate_legacy()
            return

        try:
            with open(_KB_INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for base_data in data.get("bases", []):
                base = KnowledgeBaseConfig(**base_data)
                # 加载完整数据（含 items）
                full_base = self._load_base(base.id)
                if full_base:
                    base = full_base
                self._bases[base.id] = base
                # 懒加载：不在这里初始化 vector store
            logger.info(f"[KnowledgeManager] 已加载 {len(self._bases)} 个知识库")
        except Exception as e:
            logger.warning(f"[KnowledgeManager] 加载索引失败: {e}")

    def _migrate_legacy(self) -> None:
        """从旧版 knowledge_base.json 迁移（按 source 去重合并分块）"""
        legacy_file = _PROJECT_ROOT / "data" / "knowledge_base.json"
        if not legacy_file.exists():
            return

        try:
            with open(legacy_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            base_id = "default"
            # 按 source 分组，合并分块内容
            from collections import defaultdict
            groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for doc in data.get("documents", []):
                source = doc.get("source", "")
                groups[source].append(doc)

            items: List[KnowledgeItem] = []
            for source, docs in groups.items():
                item_type = "file" if source and source.startswith("file:") else "note"
                # 按 chunk_index 排序后合并内容
                docs_sorted = sorted(docs, key=lambda d: d.get("metadata", {}).get("chunk_index", 0))
                full_text = "\n".join(d.get("content", "") for d in docs_sorted)

                if item_type == "file":
                    fname = source.replace("file:", "") if source else "unknown"
                    content: Union[str, FileMetadata] = FileMetadata(
                        name=fname,
                        size=len(full_text),
                        ext=Path(fname).suffix,
                        path="",
                    )
                else:
                    content = full_text

                first_doc = docs_sorted[0]
                items.append(KnowledgeItem(
                    id=first_doc.get("id", str(uuid.uuid4())),
                    type=item_type,
                    content=content,
                    source=source,
                    metadata={
                        **first_doc.get("metadata", {}),
                        "migrated_chunks": len(docs_sorted),
                        "extracted_text": full_text,
                    },
                    processingStatus="completed",
                    created_at=int(first_doc.get("created_at", 0) * 1000) if isinstance(first_doc.get("created_at"), (int, float)) else 0,
                    updated_at=int(first_doc.get("updated_at", 0) * 1000) if isinstance(first_doc.get("updated_at"), (int, float)) else 0,
                ))

            base = KnowledgeBaseConfig(
                id=base_id,
                name="默认知识库",
                description="从旧版迁移",
                items=items,
                created_at=0,
                updated_at=0,
            )
            self._bases[base_id] = base
            self._persist_base(base)
            self._persist_index()
            logger.info(f"[KnowledgeManager] 已从旧版迁移 {len(items)} 个文档（去重前 {len(data.get('documents', []))} 个分块）到默认知识库")
        except Exception as e:
            logger.warning(f"[KnowledgeManager] 迁移旧版失败: {e}")

    def _persist_index(self) -> None:
        """保存知识库索引"""
        data = {
            "bases": [
                {
                    "id": b.id,
                    "name": b.name,
                    "description": b.description,
                    "model": b.model,
                    "created_at": b.created_at,
                    "updated_at": b.updated_at,
                    "chunkSize": b.chunkSize,
                    "chunkOverlap": b.chunkOverlap,
                    "embedding_model": b.embedding_model,
                    "reranker_model": b.reranker_model,
                }
                for b in self._bases.values()
            ]
        }
        with open(_KB_INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _persist_base(self, base: KnowledgeBaseConfig) -> None:
        """保存单个知识库的 items 数据"""
        filepath = self._base_data_file(base.id)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(base.model_dump(), f, ensure_ascii=False, indent=2)

    def _get_kb_instance(self, base_id: str) -> Any:
        """获取或创建 KnowledgeBase 实例（支持配置嵌入模型和重排模型）"""
        if base_id in self._kb_instances:
            return self._kb_instances[base_id]

        base = self._bases.get(base_id)
        if not base:
            raise ValueError(f"知识库不存在: {base_id}")

        # 延迟导入避免启动时加载 sklearn
        src_path = str(_PROJECT_ROOT)
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        from src.knowledge import KnowledgeBase, create_embedding_model, create_reranker_model

        # 读取配置并自动填充 API Key（OpenAI）
        emb_config = base.embedding_model or {"type": "tfidf"}
        if emb_config.get("type") == "openai":
            from ..config import get_settings
            settings = get_settings()
            if not emb_config.get("api_key") and settings.openai_api_key:
                emb_config = {**emb_config, "api_key": settings.openai_api_key}
            if not emb_config.get("base_url") and settings.openai_base_url:
                emb_config = {**emb_config, "base_url": settings.openai_base_url}

        rerank_config = base.reranker_model

        embedding_model = create_embedding_model(emb_config)
        reranker_model = create_reranker_model(rerank_config)

        kb = KnowledgeBase(
            name=base.name,
            embedding_model=embedding_model,
            reranker_model=reranker_model,
            chunk_size=base.chunkSize,
            chunk_overlap=base.chunkOverlap,
        )

        # 加载所有 items 的文档内容到 vector store
        self._rebuild_kb_vectors(base, kb)

        self._kb_instances[base_id] = kb
        return kb

    def _rebuild_kb_vectors(self, base: KnowledgeBaseConfig, kb: Any) -> None:
        """重建知识库的向量索引（批量添加以确保 TF-IDF 词汇表完整）"""
        kb.clear()
        pairs = []
        for item in base.items:
            text = self._extract_text(item)
            if not text:
                continue
            title = item.metadata.get("title", item.id)
            pairs.append((title, text))

        if pairs:
            kb.add_documents_batch(pairs)
            logger.info(f"[KnowledgeManager] 向量索引重建完成: {len(pairs)} 个文档")

    def _extract_text(self, item: KnowledgeItem) -> str:
        """从 item 中提取可索引的文本"""
        if item.type == "file":
            # file 类型：尝试读取文件内容
            if isinstance(item.content, FileMetadata):
                fmeta = item.content
                # 如果 metadata 中有保存的文本内容，直接返回
                if "extracted_text" in item.metadata:
                    return item.metadata["extracted_text"]
                # 否则尝试读取文件
                fpath = _KB_FILES_DIR / fmeta.name
                if fpath.exists():
                    try:
                        text = fpath.read_text(encoding="utf-8", errors="replace")
                        return text
                    except Exception:
                        pass
                return ""
            return str(item.content)
        elif item.type in ("note", "url", "sitemap", "directory"):
            return str(item.content)
        return ""

    # ===== 公开 API =====

    @staticmethod
    def _sanitize_model_config(config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """清理模型配置中的敏感字段（用于列表接口）"""
        if not config:
            return config
        safe = dict(config)
        safe.pop("api_key", None)
        return safe

    def list_bases(
        self,
        scope: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出所有知识库（v5.3.0: 支持按 scope / project 过滤）。

        Args:
            scope: 'global' / 'project' / None（None = 全部）
            project_name: 当 scope='project' 时按项目过滤
        """
        results: List[Dict[str, Any]] = []
        for b in self._bases.values():
            # 默认旧 KB 是 global
            b_scope = getattr(b, "scope", "global")
            b_proj = getattr(b, "project_name", None)

            if scope == "global" and b_scope != "global":
                continue
            if scope == "project":
                if b_scope != "project":
                    continue
                if project_name and b_proj != project_name:
                    continue
            # scope is None → 不过滤
            results.append({
                "id": b.id,
                "name": b.name,
                "description": b.description,
                "model": b.model,
                "item_count": len(b.items),
                "created_at": b.created_at,
                "updated_at": b.updated_at,
                "embedding_model": self._sanitize_model_config(b.embedding_model),
                "reranker_model": self._sanitize_model_config(b.reranker_model),
                "scope": b_scope,
                "project_name": b_proj,
            })
        return results

    def get_base(self, base_id: str) -> Optional[KnowledgeBaseConfig]:
        """获取知识库配置"""
        return self._bases.get(base_id)

    def create_base(
        self,
        name: str,
        description: str = "",
        scope: str = "global",
        project_name: Optional[str] = None,
    ) -> KnowledgeBaseConfig:
        """创建新知识库（v5.3.0: 支持 scope）。

        Args:
            scope: 'global'（默认）/ 'project'
            project_name: scope='project' 时必填；scope='global' 时忽略

        Raises:
            ValueError: scope='project' 但 project_name 为空
        """
        if scope not in ("global", "project"):
            raise ValueError(f"invalid scope: {scope!r}")
        if scope == "project" and not project_name:
            raise ValueError("scope='project' requires project_name")

        now = int(__import__("time").time() * 1000)
        base = KnowledgeBaseConfig(
            id=f"kb_{uuid.uuid4().hex[:8]}",
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
            scope=scope,
            project_name=project_name if scope == "project" else None,
        )
        self._bases[base.id] = base
        self._persist_index()
        self._persist_base(base)
        logger.info(
            f"[KnowledgeManager] 创建知识库: {name} ({base.id}, scope={scope})"
        )
        return base

    def delete_base(self, base_id: str) -> bool:
        """删除知识库"""
        if base_id not in self._bases:
            return False
        del self._bases[base_id]
        if base_id in self._kb_instances:
            del self._kb_instances[base_id]
        # 删除数据文件
        data_file = self._base_data_file(base_id)
        if data_file.exists():
            data_file.unlink()
        self._persist_index()
        logger.info(f"[KnowledgeManager] 删除知识库: {base_id}")
        return True

    def rename_base(self, base_id: str, name: str) -> bool:
        """重命名知识库"""
        base = self._bases.get(base_id)
        if not base:
            return False
        base.name = name
        base.updated_at = int(__import__("time").time() * 1000)
        self._persist_index()
        self._persist_base(base)
        return True

    def update_base(self, base_id: str, description: Optional[str] = None) -> bool:
        """更新知识库配置"""
        base = self._bases.get(base_id)
        if not base:
            return False
        if description is not None:
            base.description = description
        base.updated_at = int(__import__("time").time() * 1000)
        self._persist_index()
        self._persist_base(base)
        return True

    def add_item(self, base_id: str, item: KnowledgeItem) -> str:
        """添加条目到知识库"""
        base = self._bases.get(base_id)
        if not base:
            raise ValueError(f"知识库不存在: {base_id}")

        if not item.id:
            item.id = f"item_{uuid.uuid4().hex[:8]}"
        now = int(__import__("time").time() * 1000)
        item.created_at = now
        item.updated_at = now

        base.items.append(item)
        base.updated_at = now

        # 增量更新向量索引（避免每次重建 O(n^2) 嵌入）
        kb = self._get_kb_instance(base_id)
        text = self._extract_text(item)
        if text:
            try:
                kb.add_document(
                    title=item.metadata.get("original_title", item.id),
                    content=text,
                    doc_id=f"{item.id}_{item.updated_at}",
                    source=item.source,
                    metadata={"item_id": item.id, **item.metadata},
                )
            except Exception as e:
                logger.debug(f"[KnowledgeManager] 添加文档到向量库失败: {e}")

        self._persist_base(base)
        self._persist_index()
        logger.info(f"[KnowledgeManager] 添加条目到 {base.name}: {item.id} (type={item.type})")
        return item.id

    def remove_item(self, base_id: str, item_id: str) -> bool:
        """从知识库删除条目"""
        base = self._bases.get(base_id)
        if not base:
            return False

        item = next((i for i in base.items if i.id == item_id), None)
        if not item:
            return False

        base.items = [i for i in base.items if i.id != item_id]
        base.updated_at = int(__import__("time").time() * 1000)

        # 删除关联的文件
        if item.type == "file" and isinstance(item.content, FileMetadata):
            fpath = _KB_FILES_DIR / item.content.name
            if fpath.exists():
                fpath.unlink()

        # 更新向量索引
        kb = self._get_kb_instance(base_id)
        self._rebuild_kb_vectors(base, kb)

        self._persist_base(base)
        self._persist_index()
        logger.info(f"[KnowledgeManager] 删除条目 {item_id} 从 {base.name}")
        return True

    def update_item(
        self,
        base_id: str,
        item_id: str,
        content: Optional[Union[str, FileMetadata]] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """更新知识库条目。

        对于 note/url/sitemap/directory 类型，传入新的字符串 content。
        对于 file 类型，传入新的 FileMetadata 以替换文件引用；旧物理文件会被删除。
        """
        base = self._bases.get(base_id)
        if not base:
            return False

        item = next((i for i in base.items if i.id == item_id), None)
        if not item:
            return False

        now = int(__import__("time").time() * 1000)

        if content is not None:
            if item.type == "file":
                if not isinstance(content, FileMetadata):
                    raise ValueError("file 类型条目必须使用 FileMetadata 更新")
                # 删除旧物理文件（路径变化时）
                if isinstance(item.content, FileMetadata):
                    old_path = _KB_FILES_DIR / item.content.name
                    if old_path.exists() and old_path.name != content.name:
                        try:
                            old_path.unlink()
                        except Exception as e:
                            logger.warning(f"[KnowledgeManager] 删除旧文件失败: {e}")
                item.content = content
            else:
                if not isinstance(content, str):
                    raise ValueError(f"{item.type} 类型条目必须使用字符串更新")
                item.content = content

        if source is not None:
            item.source = source

        if metadata is not None:
            # 浅合并，保留自动生成的字段
            item.metadata = {**item.metadata, **metadata}

        item.updated_at = now
        base.updated_at = now

        # 更新向量索引
        kb = self._get_kb_instance(base_id)
        self._rebuild_kb_vectors(base, kb)

        self._persist_base(base)
        self._persist_index()
        logger.info(f"[KnowledgeManager] 更新条目 {item_id} 在 {base.name}")
        return True

    def search(self, base_id: str, query: str, top_k: int = 5, min_score: float = 0.0) -> List[Dict[str, Any]]:
        """在指定知识库中搜索"""
        kb = self._get_kb_instance(base_id)
        results = kb.query(query, top_k=top_k, min_score=min_score)
        return [
            {
                "id": doc.id,
                "title": doc.title,
                "content": doc.content,
                "source": doc.source,
                "score": round(score, 4),
            }
            for doc, score in results
        ]

    def query_context(self, base_id: str, query: str, top_k: int = 3, max_chars: int = 1500) -> str:
        """查询并返回格式化上下文"""
        try:
            kb = self._get_kb_instance(base_id)
            context = kb.query_with_context(query, top_k=top_k, max_chars=max_chars)
            return context
        except Exception as e:
            logger.debug(f"[KnowledgeManager] 查询上下文失败: {e}")
            return ""

    def query_all_context(self, query: str, top_k: int = 3, max_chars: int = 1500) -> str:
        """查询所有知识库，合并上下文"""
        parts = []
        for base_id in self._bases:
            try:
                ctx = self.query_context(base_id, query, top_k=top_k, max_chars=max_chars // max(1, len(self._bases)))
                if ctx:
                    parts.append(ctx)
            except Exception as e:
                logger.warning(f"[KnowledgeManager] 知识库 {base_id} 查询失败，已跳过: {e}")
        return "\n---\n".join(parts)

    # ===== v5.3.0: 任务级 KB 注入 =====

    def _resolve_task_bases(
        self,
        task_project_name: Optional[str],
        base_ids: Optional[List[str]],
    ) -> List[KnowledgeBaseConfig]:
        """解析任务应该用哪些 KB。

        优先级：
          1. base_ids 显式列表（前端勾选）
          2. 自动 = 项目私有 KB (project_name=task_project_name) + 全局公共 KB
          3. 全部 KB（旧兜底）

        Returns: 按 [项目私有优先, 全局次之, 字母] 排序的列表
        """
        if base_ids:
            bases = [self._bases[bid] for bid in base_ids if bid in self._bases]
            return bases

        # 自动模式：项目私有 + 全局公共
        candidates: List[KnowledgeBaseConfig] = []
        for b in self._bases.values():
            b_scope = getattr(b, "scope", "global")
            b_proj = getattr(b, "project_name", None)
            if b_scope == "global":
                candidates.append(b)
            elif b_scope == "project" and b_proj == task_project_name:
                candidates.append(b)
        # 排序：项目私有在前，全局在后
        candidates.sort(
            key=lambda b: (
                0 if getattr(b, "scope", "global") == "project" else 1,
                b.id,
            )
        )
        return candidates

    def query_context_for_task(
        self,
        task_project_name: Optional[str],
        base_ids: Optional[List[str]],
        query: str,
        top_k: int = 3,
        max_chars: int = 4000,
    ) -> str:
        """v5.3.0: 任务级 KB 注入（支持多 KB）。

        按 KB 数均分 max_chars，避免超 token 预算。

        Returns: 合并的上下文字符串（每个 KB 之间用 --- 分隔）
        """
        bases = self._resolve_task_bases(task_project_name, base_ids)
        if not bases:
            return ""

        per_base_chars = max_chars // len(bases)
        parts: List[str] = []
        for b in bases:
            try:
                ctx = self.query_context(b.id, query, top_k=top_k, max_chars=per_base_chars)
                if ctx:
                    header = f"【知识库: {b.name}】"
                    if getattr(b, "scope", "global") == "project":
                        header += f" (项目私有)"
                    parts.append(f"{header}\n{ctx}")
            except Exception as e:
                logger.warning(
                    f"[KnowledgeManager] 任务 KB {b.id} 查询失败，已跳过: {e}"
                )
        return "\n---\n".join(parts)

    def get_items(self, base_id: str, item_type: Optional[str] = None) -> List[KnowledgeItem]:
        """获取知识库条目列表"""
        base = self._bases.get(base_id)
        if not base:
            return []
        if item_type:
            return [i for i in base.items if i.type == item_type]
        return base.items

    def save_file(self, filename: str, content: bytes) -> Path:
        """保存上传的文件"""
        _KB_FILES_DIR.mkdir(parents=True, exist_ok=True)
        # 避免文件名冲突
        save_path = _KB_FILES_DIR / filename
        counter = 1
        while save_path.exists():
            stem = Path(filename).stem
            ext = Path(filename).suffix
            save_path = _KB_FILES_DIR / f"{stem}_{counter}{ext}"
            counter += 1
        save_path.write_bytes(content)
        return save_path


# 全局单例
_knowledge_manager: Optional[KnowledgeManager] = None


def get_knowledge_manager() -> KnowledgeManager:
    """获取知识库管理器单例"""
    global _knowledge_manager
    if _knowledge_manager is None:
        _knowledge_manager = KnowledgeManager()
    return _knowledge_manager
