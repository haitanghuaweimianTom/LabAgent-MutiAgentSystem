"""
向量存储与检索
==============

借鉴 cherry-studio 的向量存储设计，
实现基于余弦相似度的文档检索。
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass

from .document import Document
from .embeddings import EmbeddingModel


@dataclass
class RetrievalResult:
    """检索结果"""
    document: Document
    score: float
    rank: int


class VectorStore:
    """向量存储"""

    def __init__(self, embedding_model: EmbeddingModel):
        self.embedding_model = embedding_model
        self.documents: List[Document] = []
        self.vectors: Optional[np.ndarray] = None

    def add_documents(self, documents: List[Document]) -> None:
        """添加文档并编码"""
        if not documents:
            return

        texts = [doc.content for doc in documents]
        new_vectors = self.embedding_model.embed(texts)

        self.documents.extend(documents)

        if self.vectors is None:
            self.vectors = new_vectors
        else:
            self.vectors = np.vstack([self.vectors, new_vectors])

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[RetrievalResult]:
        """
        检索与查询最相关的文档

        Args:
            query_text: 查询文本
            top_k: 返回结果数量
            min_score: 最低相似度阈值

        Returns:
            List[RetrievalResult]: 检索结果，按相似度降序排列
        """
        if not self.documents or self.vectors is None:
            return []

        query_vector = self.embedding_model.embed_query(query_text)

        # 计算余弦相似度
        similarities = self._cosine_similarity(query_vector, self.vectors)

        # 获取 top_k 结果
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        rank = 1
        for idx in top_indices:
            score = float(similarities[idx])
            if score < min_score:
                continue
            results.append(RetrievalResult(
                document=self.documents[idx],
                score=score,
                rank=rank
            ))
            rank += 1

        return results

    def _cosine_similarity(
        self,
        query: np.ndarray,
        vectors: np.ndarray
    ) -> np.ndarray:
        """计算余弦相似度"""
        query_norm = query / (np.linalg.norm(query) + 1e-10)
        vectors_norm = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-10)
        return np.dot(vectors_norm, query_norm)

    def clear(self) -> None:
        """清空存储"""
        self.documents.clear()
        self.vectors = None

    def __len__(self) -> int:
        return len(self.documents)

    def __repr__(self) -> str:
        return f"VectorStore(documents={len(self)}, model={self.embedding_model})"
