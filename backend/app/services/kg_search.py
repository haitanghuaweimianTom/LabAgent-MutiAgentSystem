"""GraphSearcher — 知识图谱查询层

提供结构化查询，结合图遍历与实体相关性。
查询流程：实体抽取 → 图遍历 → 邻居扩展 → 格式化上下文。
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.neo4j_store import Neo4jStore

logger = logging.getLogger(__name__)

# 单例缓存
_searcher_instance: Optional["GraphSearcher"] = None


class GraphSearcher:
    """知识图谱结构化查询层"""

    def __init__(self, store: Neo4jStore):
        self._store = store

    def entity_search(
        self,
        query: str,
        label: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """按名称搜索实体

        Args:
            query: 搜索关键词（模糊匹配 name 属性）
            label: 限定节点标签（可选）
            limit: 最大返回数
        """
        if label:
            cypher = f"""
            MATCH (n:{label})
            WHERE toLower(n.name) CONTAINS toLower($query)
            RETURN n AS node
            LIMIT $limit
            """
        else:
            cypher = """
            MATCH (n)
            WHERE toLower(n.name) CONTAINS toLower($query)
            RETURN n AS node
            LIMIT $limit
            """
        results = self._store._run_query(cypher, query=query, limit=limit)
        return [r["node"] for r in results]

    def neighbor_search(
        self,
        label: str,
        node_id: str,
        depth: int = 1,
        rel_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """查找节点的邻居

        Args:
            label: 起始节点标签
            node_id: 起始节点 ID
            depth: 遍历深度
            rel_types: 过滤的关系类型
        """
        return self._store.find_neighbors(label, node_id, depth, rel_types)

    def path_search(
        self,
        start_label: str,
        start_id: str,
        end_label: str,
        end_id: str,
        max_depth: int = 3,
    ) -> List[Dict[str, Any]]:
        """查找两个节点间的路径

        Args:
            start_label: 起始节点标签
            start_id: 起始节点 ID
            end_label: 目标节点标签
            end_id: 目标节点 ID
            max_depth: 最大跳数
        """
        return self._store.find_paths(start_label, start_id, end_label, end_id, max_depth)

    def method_recommendation(
        self,
        problem_type: str,
        dataset: str,
        metric: str,
    ) -> List[Dict[str, Any]]:
        """根据问题类型、数据集和指标推荐方法

        查询流程：
        1. 找到匹配的 ProblemType 节点
        2. 通过 SOLVES 关系找到相关 Method
        3. 通过 EVALUATED_ON 找到在指定数据集上的评测
        4. 通过 ACHIEVES 获取指标值
        """
        cypher = """
        MATCH (p:ProblemType)
        WHERE toLower(p.name) CONTAINS toLower($problem)
        MATCH (p)<-[:SOLVES]-(m:Method)
        MATCH (br:BenchmarkResult)-[:USED_METHOD]->(m)
        MATCH (br)-[:ON_DATASET]->(d:Dataset)
        WHERE toLower(d.name) CONTAINS toLower($dataset)
        MATCH (br)-[:ACHIEVES]->(met:Metric)
        WHERE toLower(met.name) CONTAINS toLower($metric)
        RETURN m AS method, br AS benchmark, met.value AS metric_value, d.name AS dataset_name
        ORDER BY met.value DESC
        """
        results = self._store._run_query(
            cypher, problem=problem_type, dataset=dataset, metric=metric
        )
        return [
            {
                "method": r["method"],
                "benchmark": r["benchmark"],
                "metric_value": r["metric_value"],
                "dataset_name": r["dataset_name"],
            }
            for r in results
        ]

    def sota_search(
        self,
        dataset_name: str,
        metric_name: str,
    ) -> List[Dict[str, Any]]:
        """查找指定数据集和指标的 SOTA 结果

        通过 Dataset 名称模糊匹配，返回在该数据集上取得最优指标的方法。
        """
        cypher = """
        MATCH (d:Dataset)
        WHERE toLower(d.name) CONTAINS toLower($dataset)
        MATCH (br:BenchmarkResult)-[:ON_DATASET]->(d)
        MATCH (br)-[:ACHIEVES]->(m:Metric)
        WHERE toLower(m.name) CONTAINS toLower($metric)
        MATCH (br)-[:USED_METHOD]->(meth:Method)
        RETURN br AS benchmark, m.value AS metric_value, meth AS method, d.name AS dataset_name
        ORDER BY m.value DESC
        """
        results = self._store._run_query(
            cypher, dataset=dataset_name, metric=metric_name
        )
        return [
            {
                "benchmark": r["benchmark"],
                "metric_value": r["metric_value"],
                "method": r["method"],
                "dataset_name": r["dataset_name"],
            }
            for r in results
        ]

    def paper_search(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """搜索论文（按标题或摘要模糊匹配）

        Args:
            query: 搜索关键词
            limit: 最大返回数
        """
        cypher = """
        MATCH (p:Paper)
        WHERE toLower(p.title) CONTAINS toLower($query)
           OR toLower(p.abstract) CONTAINS toLower($query)
        RETURN p AS paper
        LIMIT $limit
        """
        results = self._store._run_query(cypher, query=query, limit=limit)
        return [r["paper"] for r in results]

    def get_context_for_query(
        self,
        query: str,
        max_entities: int = 5,
    ) -> str:
        """为 Agent 生成格式化的图谱上下文

        流程：实体搜索 → 邻居扩展 → 格式化输出。

        Args:
            query: 用户查询
            max_entities: 最多扩展的实体数
        """
        entities = self.entity_search(query, limit=max_entities)
        if not entities:
            return "No relevant entities found in knowledge graph."

        sections = []
        for entity in entities:
            name = entity.get("name", entity.get("id", "unknown"))
            label = _extract_label(entity)
            section = f"[{label}] {name}"

            # 扩展邻居
            node_id = entity.get("id")
            if node_id and label:
                neighbors = self._store.find_neighbors(label, node_id, depth=1)
                if neighbors:
                    neighbor_strs = []
                    for nb in neighbors[:5]:
                        nb_name = nb.get("name", nb.get("id", "?"))
                        nb_label = _extract_label(nb)
                        neighbor_strs.append(f"{nb_label}:{nb_name}")
                    section += f"\n  Related: {', '.join(neighbor_strs)}"

            sections.append(section)

        return "\n".join(sections)


def _extract_label(node: Dict[str, Any]) -> str:
    """从节点字典中提取标签（Neo4j 返回的 node dict 可能含 labels）"""
    labels = node.get("labels", node.get("label"))
    if isinstance(labels, list) and labels:
        return labels[0]
    if isinstance(labels, str):
        return labels
    return ""


def get_graph_searcher(store: Neo4jStore) -> GraphSearcher:
    """获取 GraphSearcher 单例"""
    global _searcher_instance
    if _searcher_instance is None:
        _searcher_instance = GraphSearcher(store)
    return _searcher_instance
