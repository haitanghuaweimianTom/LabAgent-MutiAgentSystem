"""
数学建模多Agent系统 - MCP配置管理

支持：
- 内置MCP工具配置
- 自定义MCP工具导入
- MCP工具发现和注册
- Claude Code MCP 集成（通过 --mcp-config 参数）
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ..config import get_settings

logger = logging.getLogger(__name__)


class MCPServerConfig(BaseModel):
    """MCP服务器配置"""
    name: str
    command: str
    args: List[str] = []
    env: Dict[str, str] = {}
    enabled: bool = True
    description: str = ""


class MCPToolConfig(BaseModel):
    """MCP工具配置"""
    name: str
    server: str
    description: str = ""
    parameters: Dict[str, Any] = {}


class MCPManager:
    """MCP工具管理器"""

    # 内置MCP服务器配置
    BUILTIN_SERVERS: Dict[str, MCPServerConfig] = {
        "web_search": MCPServerConfig(
            name="web_search",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-exa"],
            description="网页搜索工具",
        ),
        "file_system": MCPServerConfig(
            name="file_system",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "./workspace"],
            description="文件系统操作工具",
        ),
        "brave_search": MCPServerConfig(
            name="brave_search",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-brave"],
            env={"BRAVE_API_KEY": ""},
            description="Brave搜索工具",
        ),
        "github": MCPServerConfig(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": ""},
            description="GitHub API工具",
        ),
    }

    # 内置工具到服务器的映射
    BUILTIN_TOOLS: Dict[str, str] = {
        "web_search": "web_search",
        "paper_search": "web_search",
        "file_read": "file_system",
        "file_write": "file_system",
        "code_execute": "file_system",
        "latex_compile": "file_system",
    }

    def __init__(self):
        self.servers: Dict[str, MCPServerConfig] = {}
        self.tools: Dict[str, MCPToolConfig] = {}
        self.custom_tools: List[Dict[str, Any]] = []
        self.agent_tools_map: Dict[str, List[str]] = {}

    def load_config(self, config_path: Optional[str] = None) -> None:
        """加载MCP配置

        支持两种格式：
        1. 新格式（含 mcpServers 顶层键）：标准 MCP JSON 配置
        2. 旧格式（含 servers/tools 顶层键）：原有自定义格式
        """
        if config_path is None:
            settings = get_settings()
            if settings.claude_mcp_config_path:
                config_path = Path(settings.claude_mcp_config_path)
            else:
                config_path = Path(__file__).parent.parent.parent / "config" / "mcp_config.json"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            logger.info(f"MCP配置文件不存在（{config_path}），使用默认配置")
            self._load_default_config()
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # 检测格式
            if "mcpServers" in config:
                # 新格式：标准 MCP JSON（用于 Claude Code --mcp-config）
                self._load_standard_mcp_config(config)
                logger.info(f"Loaded 标准 MCP config: {len(self.servers)} servers, {len(self.tools)} tools")
            else:
                # 旧格式：自定义格式
                self._load_legacy_mcp_config(config)
                logger.info(f"Loaded 旧版 MCP config: {len(self.servers)} servers, {len(self.tools)} tools")

        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            self._load_default_config()

    def _load_standard_mcp_config(self, config: Dict[str, Any]) -> None:
        """加载标准 MCP JSON 配置（Claude Code 格式）"""
        # 加载服务器
        for server_name, server_config in config.get("mcpServers", {}).items():
            env = server_config.get("env", {})
            self.servers[server_name] = MCPServerConfig(
                name=server_name,
                command=server_config.get("command", ""),
                args=server_config.get("args", []),
                env=env,
                enabled=True,
                description=f"MCP服务器: {server_name}",
            )

        # 加载工具
        for tool_name, tool_config in config.get("tools", {}).items():
            self.tools[tool_name] = MCPToolConfig(
                name=tool_name,
                server=tool_config.get("server", ""),
                description=tool_config.get("description", ""),
            )

        # 加载 Agent -> 工具映射
        agent_tools = config.get("agent_tools", {})
        for agent_name, tools_list in agent_tools.items():
            self.agent_tools_map[agent_name] = tools_list

    def _load_legacy_mcp_config(self, config: Dict[str, Any]) -> None:
        """加载旧版自定义 MCP 配置"""
        # 加载服务器配置
        for server_name, server_config in config.get("servers", {}).items():
            self.servers[server_name] = MCPServerConfig(**server_config)

        # 加载工具配置
        for tool_name, tool_config in config.get("tools", {}).items():
            self.tools[tool_name] = MCPToolConfig(**tool_config)

    def _load_default_config(self) -> None:
        """加载默认配置"""
        # 添加内置服务器
        for name, config in self.BUILTIN_SERVERS.items():
            self.servers[name] = config

        # 添加内置工具映射
        for tool_name, server_name in self.BUILTIN_TOOLS.items():
            self.tools[tool_name] = MCPToolConfig(
                name=tool_name,
                server=server_name,
                description=f"内置工具: {tool_name}",
            )

        # 默认 Agent 工具映射
        self.agent_tools_map = {
            "research_agent": ["web_search", "paper_search", "file_write"],
            "analyzer_agent": ["web_search"],
            "modeler_agent": [],
            "solver_agent": ["code_execute", "file_write"],
            "writer_agent": ["file_write", "latex_compile"],
        }

    def add_custom_server(self, config: MCPServerConfig) -> None:
        """添加自定义MCP服务器"""
        self.servers[config.name] = config
        logger.info(f"Added custom MCP server: {config.name}")

    def add_custom_tool(self, tool_config: Dict[str, Any]) -> None:
        """添加自定义工具"""
        self.custom_tools.append(tool_config)
        logger.info(f"Added custom MCP tool: {tool_config.get('name')}")

    def get_tools_for_agent(self, agent_name: str) -> List[str]:
        """获取Agent可用的工具列表"""
        # 优先使用配置中的映射
        if agent_name in self.agent_tools_map:
            return self.agent_tools_map[agent_name]
        # 兜底：内置映射
        agent_tools_map = {
            "research_agent": ["web_search", "paper_search", "file_write"],
            "analyzer_agent": ["web_search", "bing_search", "sequentialthinking", "paper_search"],
            "modeler_agent": ["sequentialthinking", "web_search", "paper_search"],
            "solver_agent": ["file_read", "file_write", "web_search"],
            "writer_agent": ["file_read", "file_write", "web_search"],
        }
        return agent_tools_map.get(agent_name, [])

    def get_server_config(self, server_name: str) -> Optional[MCPServerConfig]:
        """获取服务器配置"""
        return self.servers.get(server_name)

    def list_servers(self) -> List[Dict[str, Any]]:
        """列出所有服务器"""
        return [
            {
                "name": name,
                "command": config.command,
                "args": config.args,
                "enabled": config.enabled,
                "description": config.description,
            }
            for name, config in self.servers.items()
        ]

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有工具"""
        tools = []
        for name, config in self.tools.items():
            tools.append({
                "name": name,
                "server": config.server,
                "description": config.description,
            })
        # 添加自定义工具
        tools.extend(self.custom_tools)
        return tools

    def export_config(self) -> Dict[str, Any]:
        """导出配置"""
        return {
            "mcpServers": {
                name: {
                    "command": config.command,
                    "args": config.args,
                    "env": config.env,
                }
                for name, config in self.servers.items()
            },
            "tools": {
                name: {
                    "server": config.server,
                    "description": config.description,
                }
                for name, config in self.tools.items()
            },
            "agent_tools": self.agent_tools_map,
            "custom_tools": self.custom_tools,
        }

    def save_config(self, config_path: str) -> None:
        """保存配置到文件"""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.export_config(), f, ensure_ascii=False, indent=2)

        logger.info(f"Saved MCP config to {config_path}")


# 全局MCP管理器实例
_mcp_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    """获取MCP管理器单例"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
        _mcp_manager.load_config()
    return _mcp_manager
