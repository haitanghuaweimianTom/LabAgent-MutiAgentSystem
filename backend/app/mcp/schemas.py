"""MCP 数据模型 — CC Switch 风格"""
from enum import Enum
from typing import Any, Dict, List, Optional


class McpServerType(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamableHttp"


class InstallSource(str, Enum):
    BUILTIN = "builtin"
    MANUAL = "manual"


class McpServerApp:
    """Per-app enablement for MCP servers"""
    def __init__(self, claude: bool = True, codex: bool = True, gemini: bool = True, math_modeling: bool = True):
        self.claude = claude
        self.codex = codex
        self.gemini = gemini
        self.math_modeling = math_modeling

    def to_dict(self) -> Dict[str, bool]:
        return {
            "claude": self.claude,
            "codex": self.codex,
            "gemini": self.gemini,
            "math_modeling": self.math_modeling,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "McpServerApp":
        if isinstance(data, dict):
            return cls(
                claude=data.get("claude", True),
                codex=data.get("codex", True),
                gemini=data.get("gemini", True),
                math_modeling=data.get("math_modeling", True),
            )
        return cls()


def detect_server_type(config: Dict[str, Any]) -> str:
    """从配置推断服务器传输类型"""
    if config.get("url"):
        return McpServerType.STREAMABLE_HTTP
    if config.get("command"):
        return McpServerType.STDIO
    return McpServerType.STDIO
