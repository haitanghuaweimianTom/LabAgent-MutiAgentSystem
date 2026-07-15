"""知识图谱 Agent 集成测试

测试 _inject_graph_context() 方法：
- 正常查询返回格式化上下文
- Neo4j 不可用时静默返回空字符串
- GraphSearcher 返回空结果时处理正确
- get_kg_store / get_graph_searcher 单例行为
"""
import pytest
from unittest.mock import MagicMock, patch


# ============================================================================
# get_kg_store 单例测试
# ============================================================================

class TestGetKgStore:
    """测试 neo4j_store.get_kg_store() 单例。"""

    @patch("app.core.neo4j_store._kg_store", None)
    @patch("app.core.neo4j_store.Neo4jStore")
    def test_singleton_returns_connected_store(self, MockStore):
        """成功连接时返回 store 实例。"""
        from app.core.neo4j_store import get_kg_store

        mock_instance = MagicMock()
        mock_instance.connect.return_value = True
        MockStore.return_value = mock_instance

        result = get_kg_store()
        assert result is mock_instance
        mock_instance.connect.assert_called_once()

    @patch("app.core.neo4j_store._kg_store", None)
    @patch("app.core.neo4j_store.Neo4jStore")
    def test_singleton_returns_none_on_failure(self, MockStore):
        """连接失败时返回 None。"""
        from app.core.neo4j_store import get_kg_store

        MockStore.side_effect = Exception("connection refused")

        result = get_kg_store()
        assert result is None

    @patch("app.core.neo4j_store._kg_store", None)
    @patch("app.core.neo4j_store.Neo4jStore")
    def test_singleton_caches_instance(self, MockStore):
        """第二次调用复用同一个实例。"""
        from app.core.neo4j_store import get_kg_store

        mock_instance = MagicMock()
        mock_instance.connect.return_value = True
        MockStore.return_value = mock_instance

        first = get_kg_store()
        second = get_kg_store()
        assert first is second
        assert MockStore.call_count == 1


# ============================================================================
# get_graph_searcher 单例测试
# ============================================================================

class TestGetGraphSearcher:
    """测试 kg_search.get_graph_searcher() 单例。"""

    @patch("app.services.kg_search._searcher_instance", None)
    def test_singleton_returns_searcher(self):
        """正常返回 GraphSearcher 实例。"""
        from app.services.kg_search import get_graph_searcher, GraphSearcher

        mock_store = MagicMock()
        result = get_graph_searcher(mock_store)
        assert isinstance(result, GraphSearcher)

    @patch("app.services.kg_search._searcher_instance", None)
    def test_singleton_caches_instance(self):
        """第二次调用复用同一个实例。"""
        from app.services.kg_search import get_graph_searcher

        mock_store = MagicMock()
        first = get_graph_searcher(mock_store)
        second = get_graph_searcher(mock_store)
        assert first is second


# ============================================================================
# _inject_graph_context 测试
# ============================================================================

class TestInjectGraphContext:
    """测试 BaseAgent._inject_graph_context()。"""

    @pytest.fixture
    def agent(self):
        from app.agents.analyzer_agent import AnalyzerAgent
        return AnalyzerAgent()

    @patch("app.services.kg_search.get_graph_searcher")
    @patch("app.core.neo4j_store.get_kg_store")
    def test_returns_formatted_context(self, mock_get_store, mock_get_searcher, agent):
        """正常查询返回格式化的图谱上下文。"""
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store

        mock_searcher = MagicMock()
        mock_searcher.get_context_for_query.return_value = (
            "[Method] Transformer\n  Related: Dataset:ImageNet, Metric:Accuracy"
        )
        mock_get_searcher.return_value = mock_searcher

        result = agent._inject_graph_context("Transformer model")

        assert "知识图谱参考" in result
        assert "Transformer" in result
        assert "ImageNet" in result
        mock_searcher.get_context_for_query.assert_called_once_with("Transformer model")

    @patch("app.core.neo4j_store.get_kg_store")
    def test_returns_empty_when_store_none(self, mock_get_store, agent):
        """Neo4j 不可用时静默返回空字符串。"""
        mock_get_store.return_value = None

        result = agent._inject_graph_context("test query")
        assert result == ""

    @patch("app.services.kg_search.get_graph_searcher")
    @patch("app.core.neo4j_store.get_kg_store")
    def test_returns_empty_when_no_entities(self, mock_get_store, mock_get_searcher, agent):
        """无相关实体时返回空字符串。"""
        mock_get_store.return_value = MagicMock()

        mock_searcher = MagicMock()
        mock_searcher.get_context_for_query.return_value = "No relevant entities found in knowledge graph."
        mock_get_searcher.return_value = mock_searcher

        result = agent._inject_graph_context("nonexistent topic")
        assert result == ""

    @patch("app.core.neo4j_store.get_kg_store", side_effect=ImportError("module not found"))
    def test_returns_empty_on_exception(self, mock_get_store, agent):
        """导入失败时静默返回空字符串。"""
        result = agent._inject_graph_context("test")
        assert result == ""

    @patch("app.services.kg_search.get_graph_searcher")
    @patch("app.core.neo4j_store.get_kg_store")
    def test_handles_empty_string_result(self, mock_get_store, mock_get_searcher, agent):
        """GraphSearcher 返回空字符串时处理正确。"""
        mock_get_store.return_value = MagicMock()

        mock_searcher = MagicMock()
        mock_searcher.get_context_for_query.return_value = ""
        mock_get_searcher.return_value = mock_searcher

        result = agent._inject_graph_context("query")
        assert result == ""


# ============================================================================
# GraphSearcher.get_context_for_query 测试
# ============================================================================

class TestGraphSearcherGetContext:
    """测试 GraphSearcher.get_context_for_query() 格式化输出。"""

    def test_returns_no_entities_message(self):
        """无实体时返回提示信息。"""
        from app.services.kg_search import GraphSearcher

        mock_store = MagicMock()
        mock_store._run_query.return_value = []

        searcher = GraphSearcher(mock_store)
        result = searcher.get_context_for_query("nonexistent")
        assert "No relevant entities found" in result

    def test_formats_entity_with_neighbors(self):
        """有实体和邻居时格式化输出。"""
        from app.services.kg_search import GraphSearcher

        mock_store = MagicMock()
        # entity_search 返回一个实体
        mock_store._run_query.side_effect = [
            [{"node": {"name": "CNN", "id": "cnn-1", "labels": ["Method"]}}],
        ]
        mock_store.find_neighbors.return_value = [
            {"name": "ImageNet", "id": "img-1", "labels": ["Dataset"]}
        ]

        searcher = GraphSearcher(mock_store)
        result = searcher.get_context_for_query("CNN")

        assert "CNN" in result
        assert "ImageNet" in result
        assert "Method" in result
