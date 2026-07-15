"""Neo4jStore 单元测试

使用 mock 模拟 Neo4j 驱动，无需真实数据库。
"""

from unittest.mock import MagicMock, patch
import pytest

from app.core.neo4j_store import Neo4jStore


# ===== Fixtures =====

@pytest.fixture
def mock_neo4j():
    """Mock neo4j module"""
    with patch("app.core.neo4j_store.GraphDatabase") as mock_gdb:
        yield mock_gdb


@pytest.fixture
def store(mock_neo4j):
    """创建已连接的 Neo4jStore"""
    s = Neo4jStore(uri="bolt://test:7687", user="test", password="test")
    # 模拟连接 - mock_neo4j 就是 GraphDatabase 的 mock
    mock_driver = MagicMock()
    mock_neo4j.driver.return_value = mock_driver
    s.connect()
    return s


@pytest.fixture
def session(store):
    """获取 mock session"""
    mock_session = MagicMock()
    store._driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    store._driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return mock_session


# ===== 连接测试 =====

class TestConnection:
    def test_init_with_params(self):
        s = Neo4jStore(uri="bolt://a:7687", user="u", password="p")
        assert s._uri == "bolt://a:7687"
        assert s._user == "u"
        assert s._password == "p"

    def test_init_with_env(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://env:7687")
        monkeypatch.setenv("NEO4J_USER", "env_user")
        monkeypatch.setenv("NEO4J_PASSWORD", "env_pass")
        s = Neo4jStore()
        assert s._uri == "bolt://env:7687"
        assert s._user == "env_user"
        assert s._password == "env_pass"

    def test_connect_success(self, mock_neo4j):
        s = Neo4jStore()
        result = s.connect()
        assert result is True
        assert s._driver is not None
        mock_neo4j.driver.assert_called_once()

    def test_connect_failure(self, mock_neo4j):
        mock_neo4j.driver.side_effect = Exception("Connection refused")
        s = Neo4jStore()
        result = s.connect()
        assert result is False
        assert s._driver is None

    def test_disconnect(self, store):
        driver = store._driver  # 保存引用
        store.disconnect()
        driver.close.assert_called_once()
        assert store._driver is None

    def test_is_connected_true(self, store):
        assert store.is_connected() is True

    def test_is_connected_false_no_driver(self):
        s = Neo4jStore()
        assert s.is_connected() is False

    def test_is_connected_false_error(self, store):
        store._driver.verify_connectivity.side_effect = Exception("dead")
        assert store.is_connected() is False


# ===== 节点 CRUD 测试 =====

class TestNodeCRUD:
    def test_create_node_generates_id(self, store, session):
        session.run.return_value.single.return_value = {"id": "generated-uuid"}
        node_id = store.create_node("Paper", {"title": "Test"})
        assert node_id == "generated-uuid"
        session.run.assert_called_once()

    def test_create_node_uses_existing_id(self, store, session):
        session.run.return_value.single.return_value = {"id": "my-id"}
        node_id = store.create_node("Paper", {"id": "my-id", "title": "Test"})
        assert node_id == "my-id"

    def test_upsert_node_creates(self, store, session):
        session.run.return_value.single.return_value = {"id": "new-id"}
        node_id = store.upsert_node("Paper", {"id": "new-id", "title": "X"})
        assert node_id == "new-id"

    def test_get_node_found(self, store, session):
        # _run_query 返回列表，所以 mock 应该返回一个列表
        session.run.return_value = [{"node": {"id": "n1", "title": "Paper"}}]
        result = store.get_node("Paper", "n1")
        assert result["id"] == "n1"

    def test_get_node_not_found(self, store, session):
        session.run.return_value = []
        result = store.get_node("Paper", "missing")
        assert result is None

    def test_update_node(self, store, session):
        session.run.return_value.single.return_value = {"id": "n1"}
        ok = store.update_node("Paper", "n1", {"title": "Updated"})
        assert ok is True

    def test_delete_node(self, store, session):
        session.run.return_value.single.return_value = {"cnt": 1}
        ok = store.delete_node("Paper", "n1")
        assert ok is True

    def test_delete_node_not_found(self, store, session):
        session.run.return_value.single.return_value = {"cnt": 0}
        ok = store.delete_node("Paper", "missing")
        assert ok is False


# ===== 关系测试 =====

class TestRelationships:
    def test_create_relationship_with_id(self, store, session):
        session.run.return_value.single.return_value = {"rel_id": "r1"}
        ok = store.create_relationship(
            "Paper", "p1", "Author", "a1",
            "AUTHORED_BY", {"id": "r1", "weight": 0.9}
        )
        assert ok is True

    def test_create_relationship_generates_id(self, store, session):
        session.run.return_value.single.return_value = {"rel_id": "auto-uuid"}
        ok = store.create_relationship(
            "Paper", "p1", "Author", "a1", "AUTHORED_BY"
        )
        assert ok is True

    def test_create_relationship_failure(self, store, session):
        session.run.return_value.single.return_value = None
        ok = store.create_relationship("Paper", "p1", "Author", "a1", "AUTHORED_BY")
        assert ok is False

    def test_delete_relationship(self, store, session):
        session.run.return_value.single.return_value = {"cnt": 1}
        ok = store.delete_relationship("Paper", "p1", "Author", "a1", "AUTHORED_BY")
        assert ok is True

    def test_delete_relationship_not_found(self, store, session):
        session.run.return_value.single.return_value = {"cnt": 0}
        ok = store.delete_relationship("Paper", "p1", "Author", "a1", "AUTHORED_BY")
        assert ok is False


# ===== 图遍历测试 =====

class TestGraphTraversal:
    def test_find_neighbors(self, store, session):
        session.run.return_value = [
            {"node": {"id": "n2"}, "id": "n2"},
            {"node": {"id": "n3"}, "id": "n3"},
        ]
        neighbors = store.find_neighbors("Paper", "n1", depth=2)
        assert len(neighbors) == 2

    def test_find_neighbors_with_rel_types(self, store, session):
        session.run.return_value = []
        store.find_neighbors("Paper", "n1", depth=1, rel_types=["CITES"])
        call_args = session.run.call_args
        assert "CITES" in call_args[0][0]

    def test_find_paths(self, store, session):
        # 模拟路径对象
        mock_node1 = MagicMock()
        mock_node1.__iter__ = MagicMock(return_value=iter({"id": "n1", "label": "Paper"}.items()))
        mock_node2 = MagicMock()
        mock_node2.__iter__ = MagicMock(return_value=iter({"id": "n2", "label": "Paper"}.items()))

        mock_rel = MagicMock()
        mock_rel.type = "CITES"
        mock_rel.start_node = mock_node1
        mock_rel.end_node = mock_node2
        mock_rel.__iter__ = MagicMock(return_value=iter({"id": "r1"}.items()))

        mock_path = MagicMock()
        mock_path.nodes = [mock_node1, mock_node2]
        mock_path.relationships = [mock_rel]

        session.run.return_value = [{"path": mock_path}]

        paths = store.find_paths("Paper", "n1", "Paper", "n2", max_depth=3)
        assert len(paths) == 1
        assert len(paths[0]["nodes"]) == 2
        assert len(paths[0]["relationships"]) == 1


# ===== 搜索查询测试 =====

class TestSearchQueries:
    def test_find_by_property(self, store, session):
        session.run.return_value = [
            {"node": {"id": "n1", "title": "Test"}},
        ]
        results = store.find_by_property("Paper", "title", "Test")
        assert len(results) == 1
        assert results[0]["title"] == "Test"

    def test_find_sota(self, store, session):
        session.run.return_value = [
            {"result": {"id": "r1"}, "metric_value": 95.5},
            {"result": {"id": "r2"}, "metric_value": 92.0},
        ]
        results = store.find_sota("imagenet", "accuracy")
        assert len(results) == 2
        assert results[0]["metric_value"] == 95.5


# ===== 统计与管理测试 =====

class TestStatsAndManagement:
    def test_get_stats(self, store, session):
        # get_stats 调用多次 _run_query，每次返回不同结果
        # 按查询顺序返回: node_count, relationship_count, labels, Paper count, Author count
        call_count = [0]

        def side_effect(query, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # node_count
                return [{"count": 10}]
            elif call_count[0] == 2:  # relationship_count
                return [{"count": 20}]
            elif "db.labels" in query:  # labels
                return [{"label": "Paper"}, {"label": "Author"}]
            elif "Paper" in query:  # Paper count
                return [{"count": 5}]
            else:  # Author count
                return [{"count": 5}]

        session.run.side_effect = side_effect
        stats = store.get_stats()
        assert stats["node_count"] == 10
        assert stats["relationship_count"] == 20
        assert stats["labels"]["Paper"] == 5

    def test_clear(self, store, session):
        store.clear()
        session.run.assert_called_once()

    def test_context_manager(self, mock_neo4j):
        s = Neo4jStore()
        with s as store:
            assert store._driver is not None
            mock_driver = store._driver
        mock_driver.close.assert_called_once()


# ===== 错误处理测试 =====

class TestErrorHandling:
    def test_run_query_without_connection(self):
        s = Neo4jStore()
        with pytest.raises(RuntimeError, match="未连接"):
            s._run_query("MATCH (n) RETURN n")

    def test_run_write_without_connection(self):
        s = Neo4jStore()
        with pytest.raises(RuntimeError, match="未连接"):
            s._run_write("CREATE (n:Test) RETURN n")
