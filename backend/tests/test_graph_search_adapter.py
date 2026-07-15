"""GraphSearchAdapter 单元测试

使用 mock 模拟 GraphSearcher，无需真实 Neo4j。
"""

from unittest.mock import MagicMock, patch
import pytest

from app.core.graph_search_adapter import GraphSearchAdapter
from app.core.hybrid_search import SearchResult
from app.services.kg_search import GraphSearcher


# ===== Fixtures =====

@pytest.fixture
def mock_searcher():
    """创建 mock GraphSearcher"""
    searcher = MagicMock(spec=GraphSearcher)
    searcher.entity_search.return_value = []
    searcher.neighbor_search.return_value = []
    return searcher


@pytest.fixture
def adapter(mock_searcher):
    """创建 GraphSearchAdapter 实例"""
    return GraphSearchAdapter(mock_searcher)


# ===== search 测试 =====

class TestSearch:
    def test_returns_empty_when_no_entities(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = []
        results = adapter.search("nonexistent")
        assert results == []

    def test_returns_entity_results(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "Transformer", "labels": ["Method"]},
        ]
        results = adapter.search("transformer")
        assert len(results) == 1
        assert results[0].retrieval_method == "graph"
        assert results[0].source == "knowledge_graph"
        assert results[0].score == 0.8
        assert results[0].chunk_id == "kg_entity_m1"

    def test_entity_format_in_content(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "Transformer", "labels": ["Method"]},
        ]
        results = adapter.search("transformer")
        assert "[Method] Transformer" in results[0].content

    def test_entity_with_extra_attributes(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "BERT", "labels": ["Method"], "year": "2018"},
        ]
        results = adapter.search("bert")
        assert "year: 2018" in results[0].content

    def test_expands_neighbors(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "Transformer", "labels": ["Method"]},
        ]
        mock_searcher.neighbor_search.return_value = [
            {"id": "d1", "name": "ImageNet", "labels": ["Dataset"]},
        ]
        results = adapter.search("transformer", expand_neighbors=True)
        # 1 entity + 1 neighbor
        assert len(results) == 2
        neighbor = [r for r in results if r.metadata["entity_type"] == "neighbor"][0]
        assert neighbor.score == 0.6
        assert neighbor.chunk_id == "kg_neighbor_d1"

    def test_skips_duplicate_neighbors(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "Transformer", "labels": ["Method"]},
        ]
        # 邻居和实体 ID 相同，应跳过
        mock_searcher.neighbor_search.return_value = [
            {"id": "m1", "name": "Transformer", "labels": ["Method"]},
        ]
        results = adapter.search("transformer")
        assert len(results) == 1

    def test_no_expand_neighbors(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "Transformer", "labels": ["Method"]},
        ]
        mock_searcher.neighbor_search.return_value = [
            {"id": "d1", "name": "ImageNet", "labels": ["Dataset"]},
        ]
        results = adapter.search("transformer", expand_neighbors=False)
        assert len(results) == 1

    def test_respects_top_k(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "A", "labels": ["Method"]},
            {"id": "m2", "name": "B", "labels": ["Method"]},
            {"id": "m3", "name": "C", "labels": ["Method"]},
        ]
        results = adapter.search("test", top_k=2)
        assert len(results) == 2

    def test_sorted_by_score(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "Low", "labels": ["Method"]},
            {"id": "m2", "name": "High", "labels": ["Method"]},
        ]
        mock_searcher.neighbor_search.side_effect = [
            [{"id": "n1", "name": "NB", "labels": ["Dataset"]}],
            [],
        ]
        results = adapter.search("test")
        # entities (0.8) come before neighbors (0.6)
        assert results[0].metadata["entity_type"] == "entity"
        assert results[0].score >= results[-1].score

    def test_neighbor_limit_per_entity(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "X", "labels": ["Method"]},
        ]
        mock_searcher.neighbor_search.return_value = [
            {"id": f"n{i}", "name": f"N{i}", "labels": ["Dataset"]}
            for i in range(10)
        ]
        results = adapter.search("test", max_neighbors_per_entity=3)
        neighbors = [r for r in results if r.metadata["entity_type"] == "neighbor"]
        assert len(neighbors) == 3

    def test_metadata_fields(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "ResNet", "labels": ["Method"]},
        ]
        results = adapter.search("resnet")
        meta = results[0].metadata
        assert meta["node_id"] == "m1"
        assert meta["label"] == "Method"
        assert meta["entity_type"] == "entity"

    def test_result_compatible_with_rrf(self, adapter, mock_searcher):
        """验证返回的 SearchResult 可以被 _rrf_fusion 使用。"""
        from app.core.hybrid_search import HybridSearchEngine

        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "BERT", "labels": ["Method"]},
        ]
        results = adapter.search("bert")

        # 模拟 RRF 融合的 key 使用方式
        score_map = {}
        for rank, r in enumerate(results):
            key = r.chunk_id
            score_map[key] = score_map.get(key, 0) + 1.0 / (60 + rank + 1)

        assert "kg_entity_m1" in score_map

    def test_no_duplicate_chunk_ids(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "A", "labels": ["Method"]},
            {"id": "m1", "name": "A", "labels": ["Method"]},  # duplicate
        ]
        mock_searcher.neighbor_search.return_value = [
            {"id": "n1", "name": "B", "labels": ["Dataset"]},
        ]
        results = adapter.search("test")
        chunk_ids = [r.chunk_id for r in results]
        assert len(chunk_ids) == len(set(chunk_ids))


# ===== _format_entity 测试 =====

class TestFormatEntity:
    def test_basic_format(self, adapter):
        entity = {"id": "m1", "name": "Transformer", "labels": ["Method"]}
        result = adapter._format_entity(entity)
        assert result == "[Method] Transformer"

    def test_no_label(self, adapter):
        entity = {"id": "m1", "name": "BERT"}
        result = adapter._format_entity(entity)
        assert result == "BERT"

    def test_with_extra_attributes(self, adapter):
        entity = {"id": "m1", "name": "ResNet", "labels": ["Method"], "year": "2015"}
        result = adapter._format_entity(entity)
        assert "ResNet" in result
        assert "year: 2015" in result

    def test_fallback_to_id(self, adapter):
        entity = {"id": "m1"}
        result = adapter._format_entity(entity)
        assert "m1" in result

    def test_empty_entity(self, adapter):
        entity = {}
        result = adapter._format_entity(entity)
        assert "unknown" in result

    def test_skips_none_values(self, adapter):
        entity = {"id": "m1", "name": "X", "description": None}
        result = adapter._format_entity(entity)
        assert "description" not in result

    def test_skips_empty_string_values(self, adapter):
        entity = {"id": "m1", "name": "X", "note": "  "}
        result = adapter._format_entity(entity)
        assert "note" not in result


# ===== 边界情况 =====

class TestEdgeCases:
    def test_empty_query(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = []
        results = adapter.search("")
        assert results == []

    def test_zero_top_k(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "X", "labels": ["Method"]},
        ]
        results = adapter.search("test", top_k=0)
        assert results == []

    def test_entity_without_id(self, adapter, mock_searcher):
        mock_searcher.entity_search.return_value = [
            {"name": "Orphan", "labels": ["Method"]},
        ]
        results = adapter.search("orphan")
        assert len(results) == 1
        assert results[0].metadata["node_id"] == ""
