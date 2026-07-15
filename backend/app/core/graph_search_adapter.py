"""GraphSearchAdapter — 知识图谱检索适配器

将 GraphSearcher 的查询结果转换为 SearchResult 格式，
使图谱检索结果可以与向量/BM25 结果一起送入 RRF 融合。
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.hybrid_search import SearchResult
from app.services.kg_search import GraphSearcher, _extract_label

logger = logging.getLogger(__name__)


class GraphSearchAdapter:
    """适配 GraphSearcher 以兼容 HybridSearchEngine 的 RRF 融合。

    使用方式::

        adapter = GraphSearchAdapter(graph_searcher)
        graph_results = adapter.search("transformer architecture", top_k=10)
        # graph_results 是 List[SearchResult]，可直接传入 _rrf_fusion
    """

    # 实体匹配的基础分数
    ENTITY_SCORE = 0.8
    # 邻居扩展的基础分数
    NEIGHBOR_SCORE = 0.6

    def __init__(self, graph_searcher: GraphSearcher):
        self._searcher = graph_searcher

    def search(
        self,
        query: str,
        top_k: int = 10,
        expand_neighbors: bool = True,
        neighbor_depth: int = 1,
        max_neighbors_per_entity: int = 5,
    ) -> List[SearchResult]:
        """搜索知识图谱并返回 SearchResult 列表。

        流程：实体搜索 → 邻居扩展 → 格式化为 SearchResult。

        Args:
            query: 搜索关键词
            top_k: 最大返回结果数
            expand_neighbors: 是否扩展邻居节点
            neighbor_depth: 邻居遍历深度
            max_neighbors_per_entity: 每个实体最多扩展的邻居数
        """
        entities = self._searcher.entity_search(query, limit=top_k)
        if not entities:
            return []

        results: List[SearchResult] = []
        seen_ids: set = set()

        for rank, entity in enumerate(entities):
            node_id = entity.get("id", "")
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            label = _extract_label(entity)
            name = entity.get("name", node_id)
            content = self._format_entity(entity)
            chunk_id = f"kg_entity_{node_id}"

            results.append(SearchResult(
                content=content,
                score=self.ENTITY_SCORE,
                source="knowledge_graph",
                title=f"[{label}] {name}" if label else name,
                metadata={
                    "node_id": node_id,
                    "label": label,
                    "entity_type": "entity",
                },
                retrieval_method="graph",
                chunk_id=chunk_id,
            ))

            # 邻居扩展
            if expand_neighbors and node_id and label:
                neighbors = self._searcher.neighbor_search(
                    label, node_id, depth=neighbor_depth
                )
                for nb in neighbors[:max_neighbors_per_entity]:
                    nb_id = nb.get("id", "")
                    if nb_id in seen_ids:
                        continue
                    seen_ids.add(nb_id)

                    nb_label = _extract_label(nb)
                    nb_name = nb.get("name", nb_id)
                    nb_content = f"{nb_label}: {nb_name}" if nb_label else nb_name
                    nb_chunk_id = f"kg_neighbor_{nb_id}"

                    results.append(SearchResult(
                        content=nb_content,
                        score=self.NEIGHBOR_SCORE,
                        source="knowledge_graph",
                        title=f"[{nb_label}] {nb_name}" if nb_label else nb_name,
                        metadata={
                            "node_id": nb_id,
                            "label": nb_label,
                            "entity_type": "neighbor",
                            "parent_entity": node_id,
                        },
                        retrieval_method="graph",
                        chunk_id=nb_chunk_id,
                    ))

        # 按 score 降序排列，截取 top_k
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _format_entity(self, entity: Dict[str, Any]) -> str:
        """将实体格式化为可读文本。"""
        label = _extract_label(entity)
        name = entity.get("name", entity.get("id", "unknown"))
        parts = [f"[{label}] {name}" if label else name]

        # 附加非 name/id 的属性
        for key, value in entity.items():
            if key in ("id", "name", "labels", "label"):
                continue
            if value is not None and str(value).strip():
                parts.append(f"{key}: {value}")

        return " | ".join(parts)
