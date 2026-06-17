"""环境管理路由测试"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_list_backends(client):
    res = client.get("/api/v1/environments/backends")
    assert res.status_code == 200
    backends = res.json()
    assert "venv" in backends


def test_list_environments(client):
    res = client.get("/api/v1/environments")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_active_environment(client):
    res = client.get("/api/v1/environments/active")
    assert res.status_code == 200
    data = res.json()
    assert "name" in data
    assert "backend" in data
