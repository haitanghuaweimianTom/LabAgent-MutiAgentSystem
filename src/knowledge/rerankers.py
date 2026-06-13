"""
重排模型 (Reranker)
==================

借鉴 cherry-studio 的 Reranker 设计，
在向量检索后使用更精确的模型对候选结果重新排序，提升检索质量。

支持:
- CrossEncoder (sentence-transformers)
- TfidfReranker (简单回退)
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass

from .document import Document


@dataclass
class RerankResult:
    """重排结果"""
    document: Document
    score: float
    rank: int


class RerankerModel(ABC):
    """重排模型抽象基类"""

    @abstractmethod
    def rerank(self, query: str, documents: List[Document], top_k: int = 5) -> List[RerankResult]:
        """对候选文档重新排序"""
        pass


class CrossEncoderReranker(RerankerModel):
    """基于 CrossEncoder 的重排模型（最常用，效果较好）"""

    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers 未安装，请运行: "
                    "pip install sentence-transformers"
                )

    def rerank(self, query: str, documents: List[Document], top_k: int = 5) -> List[RerankResult]:
        if not documents:
            return []

        self._load_model()
        pairs = [[query, doc.content] for doc in documents]
        scores = self._model.predict(pairs, show_progress_bar=False)

        # 按分数降序排列
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for rank, (idx, score) in enumerate(indexed_scores[:top_k], start=1):
            results.append(RerankResult(
                document=documents[idx],
                score=float(score),
                rank=rank,
            ))
        return results

    def __repr__(self) -> str:
        return f"CrossEncoderReranker(model={self.model_name})"


class TfidfReranker(RerankerModel):
    """基于 TF-IDF 余弦相似度的简单重排（无额外依赖）"""

    def __init__(self, max_features: int = 5000):
        self.max_features = max_features
        self._vectorizer = None

    def _load_vectorizer(self):
        if self._vectorizer is None:
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                self._vectorizer = TfidfVectorizer(
                    max_features=self.max_features,
                    stop_words="english",
                    token_pattern=r"(?u)\b\w+\b",
                )
            except ImportError:
                raise ImportError("scikit-learn 未安装，请运行: pip install scikit-learn")

    def rerank(self, query: str, documents: List[Document], top_k: int = 5) -> List[RerankResult]:
        if not documents:
            return []

        self._load_vectorizer()
        texts = [doc.content for doc in documents]
        all_texts = [query] + texts
        vectors = self._vectorizer.fit_transform(all_texts).toarray()
        query_vec = vectors[0]
        doc_vectors = vectors[1:]

        import numpy as np
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
        doc_norms = doc_vectors / (np.linalg.norm(doc_vectors, axis=1, keepdims=True) + 1e-10)
        similarities = np.dot(doc_norms, query_norm)

        indexed_scores = list(enumerate(similarities))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for rank, (idx, score) in enumerate(indexed_scores[:top_k], start=1):
            results.append(RerankResult(
                document=documents[idx],
                score=float(score),
                rank=rank,
            ))
        return results

    def __repr__(self) -> str:
        return f"TfidfReranker(max_features={self.max_features})"


class NoOpReranker(RerankerModel):
    """空重排器：直接按输入顺序返回，用于关闭重排"""

    def rerank(self, query: str, documents: List[Document], top_k: int = 5) -> List[RerankResult]:
        results = []
        for rank, doc in enumerate(documents[:top_k], start=1):
            results.append(RerankResult(document=doc, score=0.0, rank=rank))
        return results

    def __repr__(self) -> str:
        return "NoOpReranker()"


class VoyageAIReranker(RerankerModel):
    """基于 VoyageAI API 的重排模型"""

    DEFAULT_MODEL = "rerank-2"

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key
        self.model_name = model_name or self.DEFAULT_MODEL

    def rerank(self, query: str, documents: List[Document], top_k: int = 5) -> List[RerankResult]:
        if not documents:
            return []
        import urllib.request
        import json

        url = "https://api.voyageai.com/v1/rerank"
        payload = json.dumps({
            "model": self.model_name,
            "query": query,
            "documents": [doc.content for doc in documents],
            "top_k": top_k,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results", [])
        rank_results = []
        for rank, item in enumerate(results, start=1):
            idx = item.get("index", 0)
            score = item.get("relevance_score", 0.0)
            rank_results.append(RerankResult(
                document=documents[idx],
                score=float(score),
                rank=rank,
            ))
        return rank_results

    def __repr__(self) -> str:
        return f"VoyageAIReranker(model={self.model_name})"


class BailianReranker(RerankerModel):
    """基于阿里云百炼 (Bailian/DashScope) 的重排模型"""

    DEFAULT_MODEL = "gte-rerank"

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key
        self.model_name = model_name or self.DEFAULT_MODEL

    def rerank(self, query: str, documents: List[Document], top_k: int = 5) -> List[RerankResult]:
        if not documents:
            return []
        import urllib.request
        import json

        url = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
        payload = json.dumps({
            "model": self.model_name,
            "input": {
                "query": query,
                "documents": [doc.content for doc in documents],
            },
            "parameters": {
                "top_n": top_k,
            },
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("output", {}).get("results", [])
        rank_results = []
        for rank, item in enumerate(results, start=1):
            idx = item.get("index", 0)
            score = item.get("relevance_score", 0.0)
            rank_results.append(RerankResult(
                document=documents[idx],
                score=float(score),
                rank=rank,
            ))
        return rank_results

    def __repr__(self) -> str:
        return f"BailianReranker(model={self.model_name})"


class JinaReranker(RerankerModel):
    """基于 Jina AI API 的重排模型"""

    DEFAULT_MODEL = "jina-reranker-v2-base-multilingual"

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key
        self.model_name = model_name or self.DEFAULT_MODEL

    def rerank(self, query: str, documents: List[Document], top_k: int = 5) -> List[RerankResult]:
        if not documents:
            return []
        import urllib.request
        import json

        url = "https://api.jina.ai/v1/rerank"
        payload = json.dumps({
            "model": self.model_name,
            "query": query,
            "documents": [doc.content for doc in documents],
            "top_n": top_k,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results", [])
        rank_results = []
        for rank, item in enumerate(results, start=1):
            idx = item.get("index", 0)
            score = item.get("relevance_score", 0.0)
            rank_results.append(RerankResult(
                document=documents[idx],
                score=float(score),
                rank=rank,
            ))
        return rank_results

    def __repr__(self) -> str:
        return f"JinaReranker(model={self.model_name})"


class TEIReranker(RerankerModel):
    """基于 HuggingFace Text Embeddings Inference (TEI) 的重排模型"""

    DEFAULT_BASE_URL = "http://localhost:8080"

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")

    def rerank(self, query: str, documents: List[Document], top_k: int = 5) -> List[RerankResult]:
        if not documents:
            return []
        import urllib.request
        import json

        url = f"{self.base_url}/rerank"
        payload = json.dumps({
            "query": query,
            "texts": [doc.content for doc in documents],
            "truncate": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data if isinstance(data, list) else data.get("results", [])
        # 按分数降序排列
        indexed_scores = [(item.get("index", 0), item.get("score", 0.0)) for item in results]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        rank_results = []
        for rank, (idx, score) in enumerate(indexed_scores[:top_k], start=1):
            rank_results.append(RerankResult(
                document=documents[idx],
                score=float(score),
                rank=rank,
            ))
        return rank_results

    def __repr__(self) -> str:
        return f"TEIReranker(base_url={self.base_url})"


# ===== 工厂方法 =====

RerankerConfig = Dict[str, Any]


def create_reranker_model(config: Optional[RerankerConfig] = None) -> Optional[RerankerModel]:
    """根据配置创建重排模型实例，返回 None 表示不重排"""
    if config is None:
        return None

    rtype = config.get("type")
    if rtype is None or rtype == "none":
        return None

    if rtype == "cross-encoder":
        return CrossEncoderReranker(model_name=config.get("model_name"))

    if rtype == "tfidf":
        return TfidfReranker(max_features=config.get("max_features", 5000))

    if rtype == "voyageai":
        return VoyageAIReranker(api_key=config.get("api_key"), model_name=config.get("model_name"))

    if rtype == "bailian":
        return BailianReranker(api_key=config.get("api_key"), model_name=config.get("model_name"))

    if rtype == "jina":
        return JinaReranker(api_key=config.get("api_key"), model_name=config.get("model_name"))

    if rtype == "tei":
        return TEIReranker(base_url=config.get("base_url"))

    return None
