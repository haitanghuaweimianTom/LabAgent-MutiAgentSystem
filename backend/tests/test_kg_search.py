"""GraphSearcher 单元测试

使用 mock 模拟 Neo4jStore，无需真实数据库。
"""

from unittest.mock import MagicMock, patch
import pytest

from app.services.kg_search import GraphSearcher, get_graph_searcher, _extract_label


# ===== Fixtures =====

@pytest.fixture
def mock_store():
    """创建 mock Neo4jStore"""
    store = MagicMock()
    store._run_query = MagicMock(return_value=[])
    store.find_neighbors = MagicMock(return_value=[])
    store.find_paths = MagicMock(return_value=[])
    return store


@pytest.fixture
def searcher(mock_store):
    """创建 GraphSearcher 实例"""
    return GraphSearcher(mock_store)


# ===== entity_search 测试 =====

class TestEntitySearch:
    def test_basic_search(self, searcher, mock_store):
        mock_store._run_query.return_value = [
            {"node": {"id": "n1", "name": "Transformer", "labels": ["Method"]}},
            {"node": {"id": "n2", "name": "BERT", "labels": ["Method"]}},
        ]
        results = searcher.entity_search("transformer")
        assert len(results) == 2
        assert results[0]["name"] == "Transformer"
        # 验证 Cypher 包含 CONTAINS 和 LIMIT
        call_args = mock_store._run_query.call_args
        cypher = call_args[0][0]
        assert "CONTAINS" in cypher
        assert "LIMIT" in cypher

    def test_search_with_label(self, searcher, mock_store):
        mock_store._run_query.return_value = [
            {"node": {"id": "d1", "name": "ImageNet", "labels": ["Dataset"]}},
        ]
        results = searcher.entity_search("imagenet", label="Dataset")
        assert len(results) == 1
        call_args = mock_store._run_query.call_args
        cypher = call_args[0][0]
        assert "Dataset" in cypher

    def test_search_no_results(self, searcher, mock_store):
        mock_store._run_query.return_value = []
        results = searcher.entity_search("nonexistent")
        assert results == []

    def test_search_with_limit(self, searcher, mock_store):
        mock_store._run_query.return_value = [{"node": {"id": "n1"}}]
        searcher.entity_search("test", limit=3)
        call_args = mock_store._run_query.call_args
        assert call_args[1]["limit"] == 3


# ===== neighbor_search 测试 =====

class TestNeighborSearch:
    def test_delegates_to_store(self, searcher, mock_store):
        mock_store.find_neighbors.return_value = [
            {"id": "n2", "name": "Dataset1"},
            {"id": "n3", "name": "Dataset2"},
        ]
        results = searcher.neighbor_search("Method", "m1", depth=2)
        mock_store.find_neighbors.assert_called_once_with("Method", "m1", 2, None)
        assert len(results) == 2

    def test_with_rel_types(self, searcher, mock_store):
        searcher.neighbor_search("Method", "m1", rel_types=["EVALUATED_ON"])
        mock_store.find_neighbors.assert_called_once_with(
            "Method", "m1", 1, ["EVALUATED_ON"]
        )


# ===== path_search 测试 =====

class TestPathSearch:
    def test_delegates_to_store(self, searcher, mock_store):
        mock_store.find_paths.return_value = [
            {"nodes": [{"id": "n1"}, {"id": "n2"}], "relationships": [{"type": "CITES"}]},
        ]
        paths = searcher.path_search("Paper", "p1", "Paper", "p2", max_depth=2)
        mock_store.find_paths.assert_called_once_with("Paper", "p1", "Paper", "p2", 2)
        assert len(paths) == 1
        assert len(paths[0]["nodes"]) == 2


# ===== method_recommendation 测试 =====

class TestMethodRecommendation:
    def test_returns_methods(self, searcher, mock_store):
        mock_store._run_query.return_value = [
            {
                "method": {"id": "m1", "name": "ResNet"},
                "benchmark": {"id": "b1"},
                "metric_value": 95.5,
                "dataset_name": "ImageNet",
            },
            {
                "method": {"id": "m2", "name": "ViT"},
                "benchmark": {"id": "b2"},
                "metric_value": 93.2,
                "dataset_name": "ImageNet",
            },
        ]
        results = searcher.method_recommendation("Image Classification", "ImageNet", "Accuracy")
        assert len(results) == 2
        assert results[0]["metric_value"] == 95.5
        assert results[0]["method"]["name"] == "ResNet"
        # 验证排序
        assert results[0]["metric_value"] > results[1]["metric_value"]

    def test_empty_results(self, searcher, mock_store):
        mock_store._run_query.return_value = []
        results = searcher.method_recommendation("Unknown", "NoDataset", "NoMetric")
        assert results == []


# ===== sota_search 测试 =====

class TestSotaSearch:
    def test_returns_sota(self, searcher, mock_store):
        mock_store._run_query.return_value = [
            {
                "benchmark": {"id": "b1"},
                "metric_value": 98.1,
                "method": {"id": "m1", "name": "GPT-4"},
                "dataset_name": "MMLU",
            },
        ]
        results = searcher.sota_search("MMLU", "Accuracy")
        assert len(results) == 1
        assert results[0]["metric_value"] == 98.1

    def test_cypher_uses_fuzzy_match(self, searcher, mock_store):
        mock_store._run_query.return_value = []
        searcher.sota_search("imagenet", "accuracy")
        call_args = mock_store._run_query.call_args
        cypher = call_args[0][0]
        assert "toLower" in cypher
        assert "CONTAINS" in cypher


# ===== paper_search 测试 =====

class TestPaperSearch:
    def test_finds_papers(self, searcher, mock_store):
        mock_store._run_query.return_value = [
            {"paper": {"id": "p1", "title": "Attention Is All You Need"}},
            {"paper": {"id": "p2", "title": "BERT: Pre-training of Deep Bidirectional Transformers"}},
        ]
        results = searcher.paper_search("attention", limit=5)
        assert len(results) == 2
        assert results[0]["title"] == "Attention Is All You Need"

    def test_search_no_results(self, searcher, mock_store):
        mock_store._run_query.return_value = []
        results = searcher.paper_search("nonexistent paper")
        assert results == []


# ===== get_context_for_query 测试 =====

class TestGetContextForQuery:
    def test_formats_entity_with_neighbors(self, searcher, mock_store):
        # entity_search 返回实体
        mock_store._run_query.side_effect = [
            # entity_search call
            [{"node": {"id": "m1", "name": "Transformer", "labels": ["Method"]}}],
        ]
        # find_neighbors 返回邻居
        mock_store.find_neighbors.return_value = [
            {"id": "d1", "name": "ImageNet", "labels": ["Dataset"]},
            {"id": "b1", "name": "BERT", "labels": ["Method"]},
        ]
        context = searcher.get_context_for_query("transformer architecture")
        assert "Transformer" in context
        assert "Related:" in context
        assert "Dataset" in context or "ImageNet" in context

    def test_no_entities(self, searcher, mock_store):
        mock_store._run_query.return_value = []
        context = searcher.get_context_for_query("nonexistent")
        assert "No relevant entities" in context

    def test_entity_without_neighbors(self, searcher, mock_store):
        mock_store._run_query.side_effect = [
            [{"node": {"id": "x1", "name": "Unknown", "labels": ["Method"]}}],
        ]
        mock_store.find_neighbors.return_value = []
        context = searcher.get_context_for_query("unknown thing")
        assert "[Method] Unknown" in context
        # No "Related:" since neighbors is empty
        assert "Related:" not in context


# ===== _extract_label 测试 =====

class TestExtractLabel:
    def test_labels_list(self):
        assert _extract_label({"labels": ["Method"]}) == "Method"

    def test_label_string(self):
        assert _extract_label({"label": "Paper"}) == "Paper"

    def test_no_labels(self):
        assert _extract_label({"id": "n1"}) == ""

    def test_empty_labels_list(self):
        assert _extract_label({"labels": []}) == ""


# ===== get_graph_searcher 单例测试 =====

class TestSingleton:
    def test_returns_same_instance(self, mock_store):
        import app.services.kg_search as mod
        mod._searcher_instance = None

        s1 = get_graph_searcher(mock_store)
        s2 = get_graph_searcher(mock_store)
        assert s1 is s2

    def test_resets_after_none(self, mock_store):
        import app.services.kg_search as mod
        mod._searcher_instance = None

        s1 = get_graph_searcher(mock_store)
        mod._searcher_instance = None
        s2 = get_graph_searcher(mock_store)
        assert s1 is not s2
