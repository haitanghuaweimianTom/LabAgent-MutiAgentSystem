"""Tests for embedding_client.py - embedding with lexical fallback."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

from embedding_client import EmbeddingClient, cosine_similarity, lexical_similarity


class TestLexicalSimilarity:
    def test_identical_texts_score_high(self):
        assert lexical_similarity("VRPTW 物流路径优化", "VRPTW 物流路径优化") > 0.9

    def test_related_texts_score_positive(self):
        # English shares tokens; Chinese is unsegmented so lexical may give 0
        assert lexical_similarity("VRPTW with time window constraints", "VRPTW with time windows") > 0.0
        assert lexical_similarity("graph neural network training", "graph neural network inference") > 0.0

    def test_unrelated_texts_lower(self):
        a = lexical_similarity("共享单车调度优化", "神经网络图像分类")
        b = lexical_similarity("共享单车调度优化", "共享单车调度优化")  # identical -> 1.0
        assert a < b

    def test_empty_returns_zero(self):
        assert lexical_similarity("", "anything string") == 0.0


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestEmbeddingClient:
    def test_lexical_backend_when_no_fastembed(self):
        # Force lexical backend by pointing at a dummy model name that fails to load.
        client = EmbeddingClient(model_name="definitely-not-a-real-model-name-xyz")
        assert client.backend == "lexical"
        assert client.embed(["some text"]) is None
        s = client.similarity("VRPTW optimization", "VRPTW 路径优化")
        assert 0.0 <= s <= 1.0

    def test_default_constructor_supported(self):
        client = EmbeddingClient()
        assert client.backend in ("embedding", "lexical")

    def test_similarity_between_relevant_and_irrelevant(self):
        client = EmbeddingClient()
        high = client.similarity("物流网络最优路径规划", "物流网络最短路径求解")
        low = client.similarity("物流网络最优路径规划", "蛋白质三维结构预测")
        # even with lexical fallback, relevant quote should rank >= irrelevant
        assert high >= low