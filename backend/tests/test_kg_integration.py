"""Knowledge Graph 集成测试

测试 extraction → storage → search 全流程（全部使用 mock，无需真实 Neo4j）。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock, patch
import pytest


# ============================================================================
# 模块导入测试
# ============================================================================

class TestImports:
    def test_import_neo4j_store(self):
        from app.core.neo4j_store import Neo4jStore
        assert Neo4jStore is not None

    def test_import_entity_extractor(self):
        from app.services.kg_extractor import EntityExtractor
        assert EntityExtractor is not None

    def test_import_graph_searcher(self):
        from app.services.kg_search import GraphSearcher
        assert GraphSearcher is not None

    def test_import_graph_search_adapter(self):
        from app.core.graph_search_adapter import GraphSearchAdapter
        assert GraphSearchAdapter is not None

    def test_import_build_kg(self):
        from scripts import build_kg
        assert hasattr(build_kg, "scan_papers")
        assert hasattr(build_kg, "import_to_neo4j")

    def test_import_all_modules_together(self):
        """验证所有 KG 模块可以一起导入，无循环依赖。"""
        from app.core.neo4j_store import Neo4jStore
        from app.services.kg_extractor import EntityExtractor
        from app.services.kg_search import GraphSearcher
        from app.core.graph_search_adapter import GraphSearchAdapter
        from app.core.hybrid_search import SearchResult
        assert all([Neo4jStore, EntityExtractor, GraphSearcher, GraphSearchAdapter, SearchResult])


# ============================================================================
# 全流程集成测试（mock Neo4j）
# ============================================================================

class TestFullPipelineMock:
    """测试 extraction → storage → search 完整流程（使用 mock）。"""

    def test_extract_then_store(self):
        """EntityExtractor 提取的结果可以写入 Neo4jStore。"""
        from app.services.kg_extractor import EntityExtractor
        from app.core.neo4j_store import Neo4jStore

        ext = EntityExtractor()
        # 模拟 LLM 返回结构化实体
        sample_content = (
            "Title: Deep Learning for Image Classification\n"
            "We propose a novel CNN architecture. "
            "Evaluated on ImageNet dataset achieving 95% accuracy."
        )
        extracted = ext.extract(sample_content)
        assert "nodes" in extracted
        assert "relationships" in extracted

        # mock Neo4jStore 并写入
        store = MagicMock(spec=Neo4jStore)
        for node in extracted["nodes"]:
            store.upsert_node.return_value = node["properties"].get("id", "auto-id")

        for rel in extracted["relationships"]:
            store.create_relationship.return_value = True

        # 执行写入
        for node in extracted["nodes"]:
            result = store.upsert_node(node["label"], node["properties"])
            assert result is not None

        for rel in extracted["relationships"]:
            result = store.create_relationship(
                rel["from_label"], rel["from_id"],
                rel["to_label"], rel["to_id"],
                rel["type"]
            )
            assert result is True

    def test_store_then_search(self):
        """Neo4jStore 中的数据可以通过 GraphSearcher 搜索。"""
        from app.services.kg_search import GraphSearcher
        from app.core.neo4j_store import Neo4jStore

        mock_store = MagicMock(spec=Neo4jStore)
        mock_store._run_query.return_value = [
            {"node": {"id": "m1", "name": "CNN", "labels": ["Method"]}},
        ]

        searcher = GraphSearcher(mock_store)
        results = searcher.entity_search("CNN")
        assert len(results) == 1
        assert results[0]["name"] == "CNN"

    def test_search_then_adapter(self):
        """GraphSearcher 结果可以通过 GraphSearchAdapter 转换为 SearchResult。"""
        from app.services.kg_search import GraphSearcher
        from app.core.graph_search_adapter import GraphSearchAdapter
        from app.core.hybrid_search import SearchResult

        mock_searcher = MagicMock(spec=GraphSearcher)
        mock_searcher.entity_search.return_value = [
            {"id": "m1", "name": "Transformer", "labels": ["Method"]},
        ]
        mock_searcher.neighbor_search.return_value = []

        adapter = GraphSearchAdapter(mock_searcher)
        results = adapter.search("transformer")

        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].retrieval_method == "graph"
        assert results[0].source == "knowledge_graph"
        assert "Transformer" in results[0].content

    def test_full_pipeline_extract_store_search(self):
        """完整管道：提取 → 存储 → 搜索 → 适配。"""
        from app.services.kg_extractor import EntityExtractor
        from app.services.kg_search import GraphSearcher
        from app.core.graph_search_adapter import GraphSearchAdapter

        # Step 1: Extract
        ext = EntityExtractor()
        content = (
            "Title: Attention Is All You Need\n"
            "We propose the Transformer architecture. "
            "Evaluated on WMT dataset achieving BLEU score 28.4."
        )
        extracted = ext.extract(content)
        assert len(extracted["nodes"]) >= 1

        # Step 2: Mock store (simulate writing)
        mock_store = MagicMock()
        mock_store.upsert_node.return_value = "new-id"
        mock_store.create_relationship.return_value = True

        for node in extracted["nodes"]:
            mock_store.upsert_node(node["label"], node["properties"])

        for rel in extracted["relationships"]:
            mock_store.create_relationship(
                rel["from_label"], rel["from_id"],
                rel["to_label"], rel["to_id"],
                rel["type"]
            )

        assert mock_store.upsert_node.call_count == len(extracted["nodes"])
        assert mock_store.create_relationship.call_count == len(extracted["relationships"])

        # Step 3: Search via GraphSearcher
        mock_store._run_query.return_value = [
            {"node": {"id": "m1", "name": "Transformer", "labels": ["Method"]}},
        ]
        mock_store.find_neighbors.return_value = [
            {"id": "d1", "name": "WMT", "labels": ["Dataset"]},
        ]

        searcher = GraphSearcher(mock_store)
        entity_results = searcher.entity_search("Transformer")
        assert len(entity_results) >= 1

        # Step 4: Adapt for hybrid search
        mock_searcher = MagicMock()
        mock_searcher.entity_search.return_value = entity_results
        mock_searcher.neighbor_search.return_value = mock_store.find_neighbors.return_value

        adapter = GraphSearchAdapter(mock_searcher)
        adapted = adapter.search("Transformer")
        assert len(adapted) >= 1
        assert adapted[0].retrieval_method == "graph"

    def test_empty_extraction_produces_no_store_calls(self):
        """空内容提取后不产生任何存储调用。"""
        from app.services.kg_extractor import EntityExtractor

        ext = EntityExtractor()
        extracted = ext.extract("")
        assert extracted == {"nodes": [], "relationships": []}

        mock_store = MagicMock()
        for node in extracted["nodes"]:
            mock_store.upsert_node(node["label"], node["properties"])
        for rel in extracted["relationships"]:
            mock_store.create_relationship(
                rel["from_label"], rel["from_id"],
                rel["to_label"], rel["to_id"],
                rel["type"]
            )

        mock_store.upsert_node.assert_not_called()
        mock_store.create_relationship.assert_not_called()


# ============================================================================
# Config 集成测试
# ============================================================================

class TestConfigIntegration:
    def test_kg_config_exists(self):
        from app.config import Settings
        s = Settings()
        assert hasattr(s, "kg_enabled")
        assert hasattr(s, "kg_extraction_batch_size")
        assert hasattr(s, "kg_max_traversal_depth")

    def test_kg_config_values(self):
        from app.config import Settings
        s = Settings()
        assert s.kg_enabled is True
        assert s.kg_extraction_batch_size >= 1
        assert s.kg_max_traversal_depth >= 1


# ============================================================================
# 边界情况
# ============================================================================

class TestEdgeCases:
    def test_extractor_batch_then_store(self):
        """批量提取后批量写入。"""
        from app.services.kg_extractor import EntityExtractor

        ext = EntityExtractor()
        contents = ["Paper one about CNN", "Paper two about RNN"]
        results = ext.batch_extract(contents)
        assert len(results) == 2

        mock_store = MagicMock()
        total_nodes = 0
        for extracted in results:
            for node in extracted["nodes"]:
                mock_store.upsert_node(node["label"], node["properties"])
                total_nodes += 1

        assert mock_store.upsert_node.call_count == total_nodes

    def test_adapter_with_empty_searcher(self):
        """GraphSearcher 返回空时，adapter 也返回空。"""
        from app.core.graph_search_adapter import GraphSearchAdapter

        mock_searcher = MagicMock()
        mock_searcher.entity_search.return_value = []

        adapter = GraphSearchAdapter(mock_searcher)
        results = adapter.search("nonexistent")
        assert results == []
