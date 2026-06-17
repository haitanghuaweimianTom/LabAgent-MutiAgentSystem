"""环境管理器 —— 统一封装 conda / venv 环境生命周期。

目标：
- 自动发现系统可用的环境后端（conda / venv）
- 列出、创建、删除环境
- 在指定环境中安装依赖
- 持久化记录"当前激活环境"
- 支持前端通过 API 操作

当前激活环境持久化在 ``backend/data/active_environment.json``。
"""
import json
import logging
import os
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ACTIVE_ENV_FILE = Path(__file__).parent.parent.parent / "data" / "active_environment.json"
VENV_BASE_DIR = Path(__file__).parent.parent.parent / "data" / "venvs"


@dataclass
class EnvironmentInfo:
    name: str
    backend: str
    python_version: str
    path: str
    is_active: bool = False
    packages_count: int = -1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EnvBackend(ABC):
    """环境后端抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """后端名称，如 ``conda`` / ``venv``。"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """当前系统是否可用该后端。"""
        ...

    @abstractmethod
    def list_environments(self) -> List[EnvironmentInfo]:
        """列出该后端管理的所有环境。"""
        ...

    @abstractmethod
    def create(self, name: str, python_version: str = "3.11") -> bool:
        """创建环境。"""
        ...

    @abstractmethod
    def delete(self, name: str) -> bool:
        """删除环境。"""
        ...

    @abstractmethod
    def install_requirements(self, name: str, requirements_path: Path) -> bool:
        """在环境中安装 requirements.txt。"""
        ...

    @abstractmethod
    def run_command(
        self, name: str, command: List[str], cwd: Optional[Path] = None
    ) -> Tuple[bool, str, str]:
        """在环境中运行命令，返回 (success, stdout, stderr)。"""
        ...


class CondaBackend(EnvBackend):
    """Conda 环境后端。"""

    @property
    def name(self) -> str:
        return "conda"

    def _cmd(self) -> Optional[str]:
        return shutil.which("conda")

    def is_available(self) -> bool:
        return self._cmd() is not None

    def list_environments(self) -> List[EnvironmentInfo]:
        cmd = self._cmd()
        if not cmd:
            return []
        try:
            result = subprocess.run(
                [cmd, "env", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            data = json.loads(result.stdout)
            active_name = self._get_active_name()
            envs = []
            for env in data.get("envs", []):
                path = Path(env)
                name = path.name if path.name != "miniconda3" else "base"
                # 忽略 base 环境，避免误操作
                if name == "base":
                    continue
                version = self._detect_python_version(path)
                envs.append(
                    EnvironmentInfo(
                        name=name,
                        backend=self.name,
                        python_version=version,
                        path=str(path),
                        is_active=(name == active_name),
                    )
                )
            return envs
        except Exception as e:
            logger.warning(f"Failed to list conda envs: {e}")
            return []

    def create(self, name: str, python_version: str = "3.11") -> bool:
        cmd = self._cmd()
        if not cmd:
            return False
        try:
            result = subprocess.run(
                [cmd, "create", "-n", name, f"python={python_version}", "-y"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.error(f"conda create failed: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"conda create error: {e}")
            return False

    def delete(self, name: str) -> bool:
        cmd = self._cmd()
        if not cmd:
            return False
        try:
            result = subprocess.run(
                [cmd, "remove", "-n", name, "--all", "-y"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"conda remove error: {e}")
            return False

    def install_requirements(self, name: str, requirements_path: Path) -> bool:
        cmd = self._cmd()
        if not cmd:
            return False
        try:
            result = subprocess.run(
                [cmd, "run", "-n", name, "pip", "install", "-r", str(requirements_path)],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                logger.error(f"conda install requirements failed: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"conda install requirements error: {e}")
            return False

    def run_command(
        self, name: str, command: List[str], cwd: Optional[Path] = None
    ) -> Tuple[bool, str, str]:
        cmd = self._cmd()
        if not cmd:
            return False, "", "conda not found"
        full_cmd = [cmd, "run", "-n", name] + command
        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=300,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)

    def _detect_python_version(self, env_path: Path) -> str:
        python_bin = env_path / "bin" / "python"
        if not python_bin.exists():
            return "unknown"
        try:
            result = subprocess.run(
                [str(python_bin), "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() or result.stderr.strip() or "unknown"
        except Exception:
            return "unknown"

    def _get_active_name(self) -> Optional[str]:
        return _load_active_env().get("name")


class VenvBackend(EnvBackend):
    """Python venv 环境后端。"""

    @property
    def name(self) -> str:
        return "venv"

    def is_available(self) -> bool:
        return shutil.which("python") is not None

    def _env_path(self, name: str) -> Path:
        VENV_BASE_DIR.mkdir(parents=True, exist_ok=True)
        return VENV_BASE_DIR / name

    def list_environments(self) -> List[EnvironmentInfo]:
        active_name = self._get_active_name()
        envs = []
        if VENV_BASE_DIR.exists():
            for path in VENV_BASE_DIR.iterdir():
                if not path.is_dir():
                    continue
                python_bin = path / "bin" / "python"
                if not python_bin.exists():
                    continue
                version = self._detect_python_version(path)
                envs.append(
                    EnvironmentInfo(
                        name=path.name,
                        backend=self.name,
                        python_version=version,
                        path=str(path),
                        is_active=(path.name == active_name),
                    )
                )
        return envs

    def create(self, name: str, python_version: str = "3.11") -> bool:
        env_path = self._env_path(name)
        if env_path.exists():
            logger.error(f"venv {name} already exists")
            return False
        try:
            result = subprocess.run(
                ["python", "-m", "venv", str(env_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.error(f"venv create failed: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"venv create error: {e}")
            return False

    def delete(self, name: str) -> bool:
        env_path = self._env_path(name)
        try:
            shutil.rmtree(env_path)
            return True
        except Exception as e:
            logger.error(f"venv delete error: {e}")
            return False

    def install_requirements(self, name: str, requirements_path: Path) -> bool:
        env_path = self._env_path(name)
        pip_bin = env_path / "bin" / "pip"
        if not pip_bin.exists():
            return False
        try:
            result = subprocess.run(
                [str(pip_bin), "install", "-r", str(requirements_path)],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                logger.error(f"venv install requirements failed: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"venv install requirements error: {e}")
            return False

    def run_command(
        self, name: str, command: List[str], cwd: Optional[Path] = None
    ) -> Tuple[bool, str, str]:
        env_path = self._env_path(name)
        python_bin = env_path / "bin" / "python"
        if not python_bin.exists():
            return False, "", f"venv {name} not found"
        full_cmd = [str(python_bin)] + command
        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=300,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)

    def _detect_python_version(self, env_path: Path) -> str:
        python_bin = env_path / "bin" / "python"
        try:
            result = subprocess.run(
                [str(python_bin), "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() or result.stderr.strip() or "unknown"
        except Exception:
            return "unknown"

    def _get_active_name(self) -> Optional[str]:
        return _load_active_env().get("name")


def _load_active_env() -> Dict[str, Any]:
    if ACTIVE_ENV_FILE.exists():
        try:
            return json.loads(ACTIVE_ENV_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def _save_active_env(name: Optional[str], backend: Optional[str]) -> None:
    ACTIVE_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "backend": backend}
    ACTIVE_ENV_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


class EnvironmentManager:
    """统一环境管理入口。"""

    def __init__(self):
        self._backends: Dict[str, EnvBackend] = {
            "conda": CondaBackend(),
            "venv": VenvBackend(),
        }

    def available_backends(self) -> List[str]:
        return [name for name, backend in self._backends.items() if backend.is_available()]

    def list_environments(self) -> List[EnvironmentInfo]:
        envs: List[EnvironmentInfo] = []
        for backend in self._backends.values():
            if backend.is_available():
                envs.extend(backend.list_environments())
        return envs

    def get_backend(self, backend_name: str) -> Optional[EnvBackend]:
        return self._backends.get(backend_name)

    def create(self, backend_name: str, name: str, python_version: str = "3.11") -> bool:
        backend = self._backends.get(backend_name)
        if not backend or not backend.is_available():
            return False
        return backend.create(name, python_version)

    def delete(self, backend_name: str, name: str) -> bool:
        backend = self._backends.get(backend_name)
        if not backend or not backend.is_available():
            return False
        # 防止删除当前激活环境
        active = _load_active_env()
        if active.get("name") == name and active.get("backend") == backend_name:
            _save_active_env(None, None)
        return backend.delete(name)

    def install_requirements(
        self, backend_name: str, name: str, requirements_path: Path
    ) -> bool:
        backend = self._backends.get(backend_name)
        if not backend or not backend.is_available():
            return False
        return backend.install_requirements(name, requirements_path)

    def install_project_requirements(self, backend_name: str, name: str) -> bool:
        """安装项目默认 backend/requirements.txt。"""
        requirements_path = Path(__file__).parent.parent.parent / "requirements.txt"
        if not requirements_path.exists():
            logger.warning(f"Project requirements not found: {requirements_path}")
            return False
        return self.install_requirements(backend_name, name, requirements_path)

    def run_command(
        self, backend_name: str, name: str, command: List[str], cwd: Optional[Path] = None
    ) -> Tuple[bool, str, str]:
        backend = self._backends.get(backend_name)
        if not backend or not backend.is_available():
            return False, "", f"backend {backend_name} not available"
        return backend.run_command(name, command, cwd=cwd)

    def set_active(self, backend_name: str, name: str) -> bool:
        backend = self._backends.get(backend_name)
        if not backend or not backend.is_available():
            return False
        # 验证环境存在
        envs = backend.list_environments()
        if not any(e.name == name for e in envs):
            return False
        _save_active_env(name, backend_name)
        return True

    def get_active(self) -> Optional[Dict[str, Any]]:
        return _load_active_env()


# 全局单例
_environment_manager: Optional[EnvironmentManager] = None


def get_active_python() -> str:
    """返回当前激活环境的 python 解释器路径；未设置则返回当前解释器。"""
    active = _load_active_env()
    backend_name = active.get("backend")
    name = active.get("name")
    if not backend_name or not name:
        return sys.executable

    manager = get_environment_manager()
    backend = manager.get_backend(backend_name)
    if not backend or not backend.is_available():
        return sys.executable

    # 验证环境仍存在
    envs = backend.list_environments()
    if not any(e.name == name for e in envs):
        return sys.executable

    if backend_name == "conda":
        for env in envs:
            if env.name == name:
                python_bin = Path(env.path) / "bin" / "python"
                if python_bin.exists():
                    return str(python_bin)
                return sys.executable
        return sys.executable

    if backend_name == "venv":
        venv_path = VENV_BASE_DIR / name
        python_bin = venv_path / "bin" / "python"
        if python_bin.exists():
            return str(python_bin)
        return sys.executable

    return sys.executable


def get_environment_manager() -> EnvironmentManager:
    global _environment_manager
    if _environment_manager is None:
        _environment_manager = EnvironmentManager()
    return _environment_manager
