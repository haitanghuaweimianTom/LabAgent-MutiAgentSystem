"""
Embedding Client - Local embeddings with lexical fallback.

Inspired by Voyager's skill library (embedding retrieval). We prefer local
embeddings via fastembed (ONNX, no torch) for good Chinese semantic matching,
but degrade gracefully to a lexical backend when the model or dependency is
unavailable (e.g. off-line, no HF access, fastembed not installed).

Two backends are supported, both exposing `embed` and `similarity`:
  - "embedding": BAAI/bge-small-zh-v1.5 via fastembed
  - "lexical": Jaccard over issue_signature.normalize_text tokens
"""

from __future__ import annotations

import math
from typing import Any, Optional

from issue_signature import normalize_text

__all__ = [
    "EmbeddingClient",
    "cosine_similarity",
    "lexical_similarity",
]

_DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors; 0.0 on zero vector."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _tokenize(text: str) -> set[str]:
    return set((normalize_text(text) or "").split())


def lexical_similarity(a: str, b: str) -> float:
    """Jaccard similarity over normalized tokens (with synonym collapsing)."""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


class EmbeddingClient:
    """Embedding provider with automatic lexical fallback."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._client: Any = None
        self.backend = self._try_init(model_name)

    def _try_init(self, model_name: str) -> str:
        try:
            from fastembed import TextEmbedding  # type: ignore

            self._client = TextEmbedding(model_name=model_name)
            return "embedding"
        except Exception:
            # dependency missing, model URI bad, or offline -> lexical
            self._client = None
            return "lexical"

    def embed(self, texts: list[str]) -> Optional[list[list[float]]]:
        """Embed a list of texts. Returns None when backend is lexical."""
        if self._client is None:
            return None
        try:
            return [list(v) for v in self._client.embed(texts)]
        except Exception:
            return None

    def similarity(self, a: str, b: str) -> float:
        """Semantic similarity between two strings under the active backend."""
        if self._client is None or self.backend != "embedding":
            return lexical_similarity(a, b)
        vecs = self.embed([a, b])
        if vecs is None or len(vecs) < 2:
            return lexical_similarity(a, b)
        return cosine_similarity(vecs[0], vecs[1])