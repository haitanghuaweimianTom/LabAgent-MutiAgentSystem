"""Neo4jStore — 知识图谱 Neo4j 存储层

提供节点 CRUD、关系管理和图遍历查询的基础封装。
连接参数通过环境变量配置：NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD。
"""

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

# 默认连接参数
_DEFAULT_URI = "bolt://localhost:7687"
_DEFAULT_USER = "neo4j"
_DEFAULT_PASSWORD = "password"


class Neo4jStore:
    """Neo4j 图数据库存储层"""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._uri = uri or os.getenv("NEO4J_URI", _DEFAULT_URI)
        self._user = user or os.getenv("NEO4J_USER", _DEFAULT_USER)
        self._password = password or os.getenv("NEO4J_PASSWORD", _DEFAULT_PASSWORD)
        self._driver = None

    def connect(self) -> bool:
        """建立 Neo4j 连接"""
        try:
            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
            # 验证连接
            self._driver.verify_connectivity()
            logger.info(f"Neo4j 连接成功: {self._uri}")
            return True
        except Exception as e:
            logger.error(f"Neo4j 连接失败: {e}")
            self._driver = None
            return False

    def disconnect(self) -> None:
        """关闭连接"""
        if self._driver:
            try:
                self._driver.close()
            except Exception as e:
                logger.warning(f"关闭 Neo4j 连接时出错: {e}")
            finally:
                self._driver = None

    def is_connected(self) -> bool:
        """检查连接是否有效"""
        if self._driver is None:
            return False
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            self._driver = None
            return False

    def _run_query(self, query: str, **params) -> List[Dict[str, Any]]:
        """执行查询并返回结果列表"""
        if not self._driver:
            raise RuntimeError("Neo4j 未连接，请先调用 connect()")
        with self._driver.session() as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    def _run_write(self, query: str, **params) -> Any:
        """执行写操作"""
        if not self._driver:
            raise RuntimeError("Neo4j 未连接，请先调用 connect()")
        with self._driver.session() as session:
            result = session.run(query, **params)
            return result.single()

    # ===== 节点 CRUD =====

    def create_node(self, label: str, properties: Dict[str, Any]) -> str:
        """创建节点，返回节点 ID

        如果 properties 中没有 'id' 字段，自动生成 UUID。
        """
        if "id" not in properties:
            properties["id"] = str(uuid.uuid4())

        query = f"CREATE (n:{label} $props) RETURN n.id AS id"
        result = self._run_write(query, props=properties)
        return result["id"]

    def upsert_node(self, label: str, properties: Dict[str, Any]) -> str:
        """合并节点（基于 id 属性）

        如果 id 存在则更新属性，否则创建新节点。
        """
        node_id = properties.get("id", str(uuid.uuid4()))
        properties["id"] = node_id

        query = f"""
        MERGE (n:{label} {{id: $id}})
        SET n += $props
        RETURN n.id AS id
        """
        result = self._run_write(query, id=node_id, props=properties)
        return result["id"]

    def get_node(self, label: str, node_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取单个节点"""
        query = f"MATCH (n:{label} {{id: $id}}) RETURN n AS node"
        results = self._run_query(query, id=node_id)
        if results:
            return results[0]["node"]
        return None

    def update_node(self, label: str, node_id: str, properties: Dict[str, Any]) -> bool:
        """更新节点属性"""
        query = f"""
        MATCH (n:{label} {{id: $id}})
        SET n += $props
        RETURN n.id AS id
        """
        result = self._run_write(query, id=node_id, props=properties)
        return result is not None

    def delete_node(self, label: str, node_id: str) -> bool:
        """删除节点及其所有关系"""
        query = f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n RETURN count(n) AS cnt"
        result = self._run_write(query, id=node_id)
        return result["cnt"] > 0

    # ===== 关系管理 =====

    def create_relationship(
        self,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """创建关系

        如果 properties 中有 'id' 字段，使用 MERGE 避免重复；否则使用 CREATE。
        """
        props = properties or {}

        if props.get("id"):
            query = f"""
            MATCH (a:{from_label} {{id: $from_id}})
            MATCH (b:{to_label} {{id: $to_id}})
            MERGE (a)-[r:{rel_type} {{id: $rel_id}}]->(b)
            SET r += $props
            RETURN r.id AS rel_id
            """
            result = self._run_write(
                query, from_id=from_id, to_id=to_id,
                rel_id=props["id"], props={k: v for k, v in props.items() if k != "id"}
            )
        else:
            props["id"] = str(uuid.uuid4())
            query = f"""
            MATCH (a:{from_label} {{id: $from_id}})
            MATCH (b:{to_label} {{id: $to_id}})
            CREATE (a)-[r:{rel_type} $props]->(b)
            RETURN r.id AS rel_id
            """
            result = self._run_write(
                query, from_id=from_id, to_id=to_id, props=props
            )

        return result is not None

    def delete_relationship(
        self,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        rel_type: str,
    ) -> bool:
        """删除指定类型的关系"""
        query = f"""
        MATCH (a:{from_label} {{id: $from_id}})-[r:{rel_type}]->(b:{to_label} {{id: $to_id}})
        DELETE r
        RETURN count(r) AS cnt
        """
        result = self._run_write(query, from_id=from_id, to_id=to_id)
        return result["cnt"] > 0

    # ===== 图遍历查询 =====

    def find_neighbors(
        self,
        label: str,
        node_id: str,
        depth: int = 1,
        rel_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """查找邻居节点

        Args:
            label: 起始节点标签
            node_id: 起始节点 ID
            depth: 遍历深度（默认 1）
            rel_types: 过滤的关系类型列表（可选）
        """
        if depth < 1:
            depth = 1

        if rel_types:
            rel_filter = ":" + "|".join(rel_types)
            query = f"""
            MATCH (n:{label} {{id: $id}})-[{rel_filter}*1..{depth}]-(m)
            RETURN DISTINCT m AS node, m.id AS id
            """
        else:
            query = f"""
            MATCH (n:{label} {{id: $id}})-[*1..{depth}]-(m)
            RETURN DISTINCT m AS node, m.id AS id
            """

        results = self._run_query(query, id=node_id)
        return [r["node"] for r in results]

    def find_paths(
        self,
        start_label: str,
        start_id: str,
        end_label: str,
        end_id: str,
        max_depth: int = 5,
    ) -> List[Dict[str, Any]]:
        """查找两个节点间的所有路径

        Returns:
            路径列表，每个路径包含 nodes 和 relationships
        """
        query = f"""
        MATCH path = (a:{start_label} {{id: $start_id}})-[*1..{max_depth}]-(b:{end_label} {{id: $end_id}})
        RETURN path
        """
        results = self._run_query(query, start_id=start_id, end_id=end_id)

        paths = []
        for record in results:
            path = record["path"]
            nodes = [dict(node) for node in path.nodes]
            rels = [
                {
                    "type": rel.type,
                    "start_node": dict(rel.start_node).get("id"),
                    "end_node": dict(rel.end_node).get("id"),
                    **dict(rel),
                }
                for rel in path.relationships
            ]
            paths.append({"nodes": nodes, "relationships": rels})

        return paths

    # ===== 搜索查询 =====

    def find_by_property(
        self,
        label: str,
        prop_name: str,
        prop_value: Any,
    ) -> List[Dict[str, Any]]:
        """按属性值查找节点"""
        query = f"""
        MATCH (n:{label})
        WHERE n.{prop_name} = $value
        RETURN n AS node
        """
        results = self._run_query(query, value=prop_value)
        return [r["node"] for r in results]

    def find_sota(
        self,
        dataset_id: str,
        metric_name: str,
    ) -> List[Dict[str, Any]]:
        """查找某个数据集在指定指标上的 SOTA 结果

        假设图中存在 BenchmarkResult 节点和 ON_DATASET、ACHIEVES 关系。
        """
        query = """
        MATCH (r:BenchmarkResult)-[:ON_DATASET]->(d:Dataset {id: $dataset_id})
        MATCH (r)-[:ACHIEVES]->(m:Metric {name: $metric_name})
        RETURN r AS result, m.value AS metric_value
        ORDER BY m.value DESC
        """
        results = self._run_query(query, dataset_id=dataset_id, metric_name=metric_name)
        return [
            {**r["result"], "metric_value": r["metric_value"]}
            for r in results
        ]

    # ===== 统计与管理 =====

    def get_stats(self) -> Dict[str, Any]:
        """获取图数据库统计信息"""
        queries = {
            "node_count": "MATCH (n) RETURN count(n) AS count",
            "relationship_count": "MATCH ()-[r]->() RETURN count(r) AS count",
        }
        stats: Dict[str, Any] = {}
        for key, query in queries.items():
            result = self._run_query(query)
            stats[key] = result[0]["count"] if result else 0

        # 按标签统计节点
        label_query = "CALL db.labels() YIELD label RETURN label"
        labels = self._run_query(label_query)
        stats["labels"] = {}
        for record in labels:
            label = record["label"]
            count_query = f"MATCH (n:{label}) RETURN count(n) AS count"
            count_result = self._run_query(count_query)
            stats["labels"][label] = count_result[0]["count"] if count_result else 0

        return stats

    def clear(self) -> None:
        """清空所有节点和关系（仅用于测试）"""
        self._run_write("MATCH (n) DETACH DELETE n")
        logger.info("Neo4j 数据已清空")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False


_kg_store = None


def get_kg_store():
    global _kg_store
    if _kg_store is None:
        try:
            _kg_store = Neo4jStore()
            _kg_store.connect()
        except Exception:
            _kg_store = None
    return _kg_store
