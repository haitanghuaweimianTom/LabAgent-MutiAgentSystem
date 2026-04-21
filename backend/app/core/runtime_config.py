"""运行时配置 - 直接读写 .env 文件，永久保存"""
import os
from pathlib import Path
from typing import Any, Dict

# .env 文件路径（backend/.env）
ENV_FILE = Path(__file__).parent.parent.parent / ".env"


def _read_env() -> Dict[str, str]:
    """读取 .env 文件"""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _write_env(env: Dict[str, str]) -> None:
    """写入 .env 文件"""
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_runtime_api_key() -> str:
    """获取运行时API密钥（优先读.env文件）"""
    env = _read_env()
    key = env.get("MINIMAX_API_KEY", "")
    if key:
        return key
    # 回退到环境变量
    return os.environ.get("MINIMAX_API_KEY", "")


def update_runtime_api_key(key: str) -> None:
    """更新 .env 文件中的 API 密钥（永久保存）"""
    env = _read_env()
    env["MINIMAX_API_KEY"] = key
    _write_env(env)


def is_api_key_set() -> bool:
    """检查 .env 中是否有 API 密钥"""
    env = _read_env()
    return bool(env.get("MINIMAX_API_KEY", "").strip())

