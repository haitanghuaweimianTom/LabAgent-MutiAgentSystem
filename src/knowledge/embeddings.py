"""
嵌入模型
========

借鉴 cherry-studio 的 Embeddings 设计，
支持多种嵌入方式。
"""

from abc import ABC, abstractmethod
from typing import List
import numpy as np


class EmbeddingModel(ABC):
    """嵌入模型抽象基类"""

    @abstractmethod
    def embed(self, texts: List[str]) -> np.ndarray:
        """将文本列表编码为向量"""
        pass

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray:
        """将查询文本编码为向量"""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        pass


class SentenceTransformerEmbedding(EmbeddingModel):
    """基于 sentence-transformers 的嵌入模型"""

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model = None
        self._dimension = None

    def _load_model(self):
        """惰性加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                self._dimension = self._model.get_sentence_embedding_dimension()
            except ImportError:
                raise ImportError(
                    "sentence-transformers 未安装，请运行: "
                    "pip install sentence-transformers"
                )

    def embed(self, texts: List[str]) -> np.ndarray:
        self._load_model()
        return self._model.encode(texts, convert_to_numpy=True)

    def embed_query(self, text: str) -> np.ndarray:
        self._load_model()
        return self._model.encode([text], convert_to_numpy=True)[0]

    @property
    def dimension(self) -> int:
        self._load_model()
        return self._dimension

    def __repr__(self) -> str:
        return f"SentenceTransformerEmbedding(model={self.model_name})"


class TfidfEmbedding(EmbeddingModel):
    """基于 TF-IDF 的嵌入模型（无需深度学习依赖）"""

    def __init__(self, max_features: int = 5000):
        self.max_features = max_features
        self._vectorizer = None
        self._fitted = False

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
                raise ImportError(
                    "scikit-learn 未安装，请运行: pip install scikit-learn"
                )

    def fit(self, texts: List[str]):
        """拟合 TF-IDF 模型"""
        self._load_vectorizer()
        self._vectorizer.fit(texts)
        self._fitted = True

    def embed(self, texts: List[str]) -> np.ndarray:
        self._load_vectorizer()
        if not self._fitted:
            self.fit(texts)
        return self._vectorizer.transform(texts).toarray()

    def embed_query(self, text: str) -> np.ndarray:
        self._load_vectorizer()
        if not self._fitted:
            raise RuntimeError("TF-IDF 模型未拟合，请先调用 fit()")
        return self._vectorizer.transform([text]).toarray()[0]

    @property
    def dimension(self) -> int:
        self._load_vectorizer()
        return self.max_features

    def __repr__(self) -> str:
        return f"TfidfEmbedding(max_features={self.max_features})"


from typing import Optional
