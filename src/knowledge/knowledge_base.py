"""
知识库
======

封装文档处理、嵌入和检索的完整 RAG 流程。
借鉴 cherry-studio 的 KnowledgeService 设计。
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from .document import Document, DocumentChunker
from .embeddings import EmbeddingModel, SentenceTransformerEmbedding, TfidfEmbedding
from .vector_store import VectorStore, RetrievalResult


class KnowledgeBase:
    """知识库"""

    def __init__(
        self,
        embedding_model: Optional[EmbeddingModel] = None,
        chunk_size: int = 512,
        chunk_overlap: int = 128,
        name: str = "default",
    ):
        self.name = name
        self.chunker = DocumentChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.embedding_model = embedding_model or self._default_embedding_model()
        self.vector_store = VectorStore(self.embedding_model)
        self._documents: Dict[str, Document] = {}

    def _default_embedding_model(self) -> EmbeddingModel:
        """获取默认嵌入模型"""
        try:
            return SentenceTransformerEmbedding()
        except Exception:
            print("[KnowledgeBase] sentence-transformers 不可用，回退到 TF-IDF")
            return TfidfEmbedding()

    def add_document(
        self,
        title: str,
        content: str,
        doc_id: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        添加文档到知识库

        Returns:
            str: 文档 ID
        """
        doc_id = doc_id or f"doc_{len(self._documents)}_{datetime.now().timestamp()}"
        doc = Document(
            id=doc_id,
            title=title,
            content=content,
            source=source,
            metadata=metadata or {},
        )

        # 分块
        chunks = self.chunker.chunk(doc)

        # 添加到向量存储
        self.vector_store.add_documents(chunks)
        self._documents[doc_id] = doc

        print(f"[KnowledgeBase] 添加文档 '{title}' ({len(chunks)} 个片段)")
        return doc_id

    def add_documents(self, documents: List[Tuple[str, str]]) -> List[str]:
        """批量添加文档"""
        ids = []
        for i, (title, content) in enumerate(documents):
            doc_id = self.add_document(title, content, doc_id=f"doc_batch_{i}")
            ids.append(doc_id)
        return ids

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> List[Tuple[Document, float]]:
        """
        查询知识库

        Returns:
            List[Tuple[Document, float]]: (文档, 相似度分数)
        """
        results = self.vector_store.query(query_text, top_k=top_k, min_score=min_score)
        return [(r.document, r.score) for r in results]

    def query_with_context(
        self,
        query_text: str,
        top_k: int = 5,
        min_score: float = 0.0,
        max_chars: int = 2000,
    ) -> str:
        """
        查询知识库并返回格式化的上下文文本

        Returns:
            str: 检索到的知识上下文
        """
        results = self.query(query_text, top_k=top_k, min_score=min_score)
        if not results:
            return ""

        context_parts = []
        total_chars = 0
        for doc, score in results:
            part = f"【{doc.title}】(相关度: {score:.3f})\n{doc.content}\n"
            if total_chars + len(part) > max_chars:
                break
            context_parts.append(part)
            total_chars += len(part)

        return "\n---\n".join(context_parts)

    def remove_document(self, doc_id: str) -> bool:
        """移除文档（注意：当前实现需要重建向量存储）"""
        if doc_id not in self._documents:
            return False
        del self._documents[doc_id]
        # 重建向量存储
        self.vector_store.clear()
        all_chunks = []
        for doc in self._documents.values():
            chunks = self.chunker.chunk(doc)
            all_chunks.extend(chunks)
        if all_chunks:
            self.vector_store.add_documents(all_chunks)
        return True

    def list_documents(self) -> List[Dict[str, Any]]:
        """列出所有文档"""
        return [
            {
                "id": doc.id,
                "title": doc.title,
                "source": doc.source,
                "content_length": len(doc.content),
                "metadata": doc.metadata,
            }
            for doc in self._documents.values()
        ]

    def save(self, filepath: str) -> None:
        """保存知识库到文件"""
        data = {
            "name": self.name,
            "documents": [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "content": doc.content,
                    "source": doc.source,
                    "metadata": doc.metadata,
                }
                for doc in self._documents.values()
            ],
            "created_at": datetime.now().isoformat(),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[KnowledgeBase] 已保存到 {filepath}")

    def load(self, filepath: str) -> None:
        """从文件加载知识库"""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"知识库文件不存在: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.name = data.get("name", self.name)
        self._documents.clear()
        self.vector_store.clear()

        for doc_data in data.get("documents", []):
            self.add_document(
                title=doc_data["title"],
                content=doc_data["content"],
                doc_id=doc_data["id"],
                source=doc_data.get("source"),
                metadata=doc_data.get("metadata", {}),
            )

        print(f"[KnowledgeBase] 已从 {filepath} 加载 {len(self._documents)} 个文档")

    def clear(self) -> None:
        """清空知识库"""
        self._documents.clear()
        self.vector_store.clear()
        print("[KnowledgeBase] 已清空")

    def __len__(self) -> int:
        return len(self._documents)

    def __repr__(self) -> str:
        return f"KnowledgeBase(name={self.name}, documents={len(self)}, chunks={len(self.vector_store)})"
