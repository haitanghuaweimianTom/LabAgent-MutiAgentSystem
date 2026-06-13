"""
嵌入模型
========

借鉴 cherry-studio 的 Embeddings 设计，
支持多种嵌入方式：TF-IDF / sentence-transformers / OpenAI / Ollama / Azure 等。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
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
    """基于 sentence-transformers 的本地嵌入模型"""

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


class OpenAIEmbedding(EmbeddingModel):
    """基于 OpenAI API 的嵌入模型（兼容任何 OpenAI-compatible 接口）"""

    DEFAULT_MODEL = "text-embedding-3-small"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"
        self.model = model or self.DEFAULT_MODEL
        self.dimensions = dimensions
        self._client = None
        self._dimension = None

    def _load_client(self):
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
            except ImportError:
                raise ImportError("openai 未安装，请运行: pip install openai")

    def embed(self, texts: List[str]) -> np.ndarray:
        self._load_client()
        kwargs: Dict[str, Any] = {"model": self.model, "input": texts}
        if self.dimensions:
            kwargs["dimensions"] = self.dimensions
        resp = self._client.embeddings.create(**kwargs)
        vectors = np.array([item.embedding for item in resp.data], dtype=np.float32)
        self._dimension = vectors.shape[1]
        return vectors

    def embed_query(self, text: str) -> np.ndarray:
        self._load_client()
        kwargs: Dict[str, Any] = {"model": self.model, "input": [text]}
        if self.dimensions:
            kwargs["dimensions"] = self.dimensions
        resp = self._client.embeddings.create(**kwargs)
        vector = np.array(resp.data[0].embedding, dtype=np.float32)
        self._dimension = len(vector)
        return vector

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # 通过一次查询推断维度
            self.embed_query("test")
        return self._dimension

    def __repr__(self) -> str:
        return f"OpenAIEmbedding(model={self.model})"


class OllamaEmbedding(EmbeddingModel):
    """基于 Ollama 本地服务的嵌入模型"""

    DEFAULT_MODEL = "nomic-embed-text"

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        self.model = model or self.DEFAULT_MODEL
        self._dimension = None

    def _call_embed(self, texts: List[str]) -> np.ndarray:
        import urllib.request
        import json

        url = f"{self.base_url}/api/embed"
        payload = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # Ollama /api/embed 返回 embeddings 数组
        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise RuntimeError(f"Ollama embed 返回空: {data}")
        vectors = np.array(embeddings, dtype=np.float32)
        self._dimension = vectors.shape[-1]
        return vectors

    def embed(self, texts: List[str]) -> np.ndarray:
        return self._call_embed(texts)

    def embed_query(self, text: str) -> np.ndarray:
        vectors = self._call_embed([text])
        return vectors[0]

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self.embed_query("test")
        return self._dimension

    def __repr__(self) -> str:
        return f"OllamaEmbedding(model={self.model})"


class VoyageAIEmbedding(EmbeddingModel):
    """基于 VoyageAI API 的嵌入模型"""

    DEFAULT_MODEL = "voyage-3"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self._dimension = None

    def _call_embed(self, texts: List[str]) -> np.ndarray:
        import urllib.request
        import json

        url = "https://api.voyageai.com/v1/embeddings"
        payload = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
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
        embeddings = [item["embedding"] for item in data.get("data", [])]
        if not embeddings:
            raise RuntimeError(f"VoyageAI embed 返回空: {data}")
        vectors = np.array(embeddings, dtype=np.float32)
        self._dimension = vectors.shape[1]
        return vectors

    def embed(self, texts: List[str]) -> np.ndarray:
        all_vectors = []
        batch_size = 8
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            all_vectors.append(self._call_embed(batch))
        return np.vstack(all_vectors)

    def embed_query(self, text: str) -> np.ndarray:
        vectors = self._call_embed([text])
        return vectors[0]

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self.embed_query("test")
        return self._dimension

    def __repr__(self) -> str:
        return f"VoyageAIEmbedding(model={self.model})"


# ===== 工厂方法 =====

EmbeddingConfig = Dict[str, Any]


def create_embedding_model(config: Optional[EmbeddingConfig] = None) -> EmbeddingModel:
    """根据配置创建嵌入模型实例"""
    if config is None:
        config = {"type": "tfidf"}

    etype = config.get("type", "tfidf")

    if etype == "tfidf":
        return TfidfEmbedding(max_features=config.get("max_features", 5000))

    if etype == "sentence-transformers":
        return SentenceTransformerEmbedding(model_name=config.get("model_name"))

    if etype == "openai":
        return OpenAIEmbedding(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
            model=config.get("model_name"),
            dimensions=config.get("dimensions"),
        )

    if etype == "ollama":
        return OllamaEmbedding(
            base_url=config.get("base_url"),
            model=config.get("model_name"),
        )

    if etype == "voyageai":
        return VoyageAIEmbedding(
            api_key=config.get("api_key"),
            model=config.get("model_name"),
        )

    # 默认回退
    return TfidfEmbedding(max_features=2000)
