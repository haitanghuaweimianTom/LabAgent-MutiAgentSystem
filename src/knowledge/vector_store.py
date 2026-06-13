"""
向量存储与检索
==============

借鉴 cherry-studio 的向量存储设计，
实现基于余弦相似度的文档检索，支持重排模型优化结果。
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass

from .document import Document
from .embeddings import EmbeddingModel
from .rerankers import RerankerModel, RerankResult


@dataclass
class RetrievalResult:
    """检索结果"""
    document: Document
    score: float
    rank: int


class VectorStore:
    """向量存储"""

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        reranker_model: Optional[RerankerModel] = None,
    ):
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
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
        min_score: float = 0.0,
    ) -> List[RetrievalResult]:
        """
        检索与查询最相关的文档。
        若配置了重排模型，会先检索 top_k * 4 的候选，再重排返回 top_k。
        """
        if not self.documents or self.vectors is None:
            return []

        query_vector = self.embedding_model.embed_query(query_text)

        # 计算余弦相似度
        similarities = self._cosine_similarity(query_vector, self.vectors)

        # 获取初始候选（若需要重排则多取一些）
        recall_k = top_k * 4 if self.reranker_model else top_k
        top_indices = np.argsort(similarities)[::-1][:recall_k]

        candidates = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score < min_score:
                continue
            candidates.append(self.documents[idx])

        # 若配置了重排模型，对候选进行重排
        if self.reranker_model and candidates:
            rerank_results = self.reranker_model.rerank(query_text, candidates, top_k=top_k)
            return [
                RetrievalResult(
                    document=r.document,
                    score=r.score,
                    rank=r.rank,
                )
                for r in rerank_results
            ]

        # 否则直接按相似度返回
        results = []
        rank = 1
        for idx in top_indices[:top_k]:
            score = float(similarities[idx])
            if score < min_score:
                continue
            results.append(RetrievalResult(
                document=self.documents[idx],
                score=score,
                rank=rank,
            ))
            rank += 1

        return results

    def _cosine_similarity(
        self,
        query: np.ndarray,
        vectors: np.ndarray,
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
        return f"VectorStore(documents={len(self)}, model={self.embedding_model}, reranker={self.reranker_model})"
