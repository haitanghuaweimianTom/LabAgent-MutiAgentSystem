"""环境管理器测试"""
import json
import sys
from pathlib import Path

import pytest

from app.core.environment_manager import (
    EnvironmentManager,
    VenvBackend,
    CondaBackend,
    get_active_python,
    get_environment_manager,
    ACTIVE_ENV_FILE,
)


def test_manager_lists_available_backends():
    manager = EnvironmentManager()
    backends = manager.available_backends()
    # 至少 venv 可用（python 一定存在）
    assert "venv" in backends


def test_venv_backend_detects_python():
    backend = VenvBackend()
    assert backend.is_available()


def test_conda_backend_availability_matches_system():
    backend = CondaBackend()
    # 不假设系统一定有 conda
    from shutil import which
    assert backend.is_available() == (which("conda") is not None)


def test_active_python_fallback_to_current():
    # 未设置激活环境时返回当前解释器
    ACTIVE_ENV_FILE.unlink(missing_ok=True)
    assert get_active_python() == sys.executable


def test_active_python_returns_current_when_backend_missing():
    ACTIVE_ENV_FILE.write_text(json.dumps({"name": "ghost", "backend": "conda"}), "utf-8")
    try:
        assert get_active_python() == sys.executable
    finally:
        ACTIVE_ENV_FILE.unlink(missing_ok=True)


def test_get_environment_manager_singleton():
    a = get_environment_manager()
    b = get_environment_manager()
    assert a is b
