"""
数学建模多Agent系统 - MCP配置管理

支持：
- 内置MCP工具配置
- 自定义MCP工具导入
- MCP工具发现和注册
- Claude Code MCP 集成（通过 --mcp-config 参数）
- CC Switch 风格：HTTP/SSE 传输类型、标签、per-app 启用
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ..config import get_settings
from .schemas import McpServerType, InstallSource, McpServerApp, detect_server_type

import shutil

logger = logging.getLogger(__name__)

# 尝试定位 uvx；若不在 PATH 中则回退到命令名，由调用方/系统 PATH 解析
_UVX_CMD = shutil.which("uvx") or "uvx"


class MCPServerConfig(BaseModel):
    """MCP服务器配置 — 向后兼容"""
    name: str
    command: str = ""
    args: List[str] = []
    env: Dict[str, str] = {}
    enabled: bool = True
    description: str = ""
    # CC Switch 扩展字段
    url: Optional[str] = None
    headers: Dict[str, str] = {}
    tags: List[str] = []
    disabled_tools: List[str] = []
    apps: Optional[Dict[str, bool]] = None
    install_source: str = "manual"
    is_trusted: bool = True
    server_type: str = "stdio"


class MCPToolConfig(BaseModel):
    """MCP工具配置"""
    name: str
    server: str
    description: str = ""
    parameters: Dict[str, Any] = {}


class MCPManager:
    """MCP工具管理器"""

    # 内置MCP服务器配置（增强版）
    BUILTIN_SERVERS: Dict[str, MCPServerConfig] = {
        "web_search": MCPServerConfig(
            name="web_search",
            command="npx",
            args=["-y", "@nachoretro/internetsearch"],
            description="网页搜索工具 (DuckDuckGo / Brave)",
            tags=["search", "web"],
            install_source=InstallSource.BUILTIN,
            is_trusted=True,
        ),
        "file_system": MCPServerConfig(
            name="file_system",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "./workspace", "./output"],
            description="文件系统操作工具（workspace + output）",
            tags=["filesystem"],
            install_source=InstallSource.BUILTIN,
            is_trusted=True,
        ),
        "github": MCPServerConfig(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": ""},
            description="GitHub API工具",
            tags=["git", "code"],
            install_source=InstallSource.BUILTIN,
            is_trusted=True,
        ),
        "scholarly_research": MCPServerConfig(
            name="scholarly_research",
            command="npx",
            args=["-y", "scholarly-research-mcp"],
            description="学术论文检索 (Google Scholar, ArXiv, PubMed, JSTOR)",
            tags=["search", "academic", "paper"],
            install_source=InstallSource.BUILTIN,
            is_trusted=True,
        ),
        "arxiv_server": MCPServerConfig(
            name="arxiv_server",
            command=_UVX_CMD,
            args=["--from", "arxiv-mcp-server", "arxiv-mcp-server"],
            description="arXiv 论文检索 (搜索/下载/摘要/引用图谱)",
            tags=["search", "academic", "paper", "arxiv"],
            install_source=InstallSource.BUILTIN,
            is_trusted=True,
        ),
    }

    # 内置工具到服务器的映射
    BUILTIN_TOOLS: Dict[str, str] = {
        "web_search": "web_search",
        "paper_search": "scholarly_research",
        "arxiv_search": "arxiv_server",
        "scholar_search": "scholarly_research",
        "arxiv_download": "arxiv_server",
        "arxiv_abstract": "arxiv_server",
        "arxiv_citation": "arxiv_server",
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
        """加载MCP配置"""
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

            if "mcpServers" in config:
                self._load_standard_mcp_config(config)
                logger.info(f"Loaded 标准 MCP config: {len(self.servers)} servers, {len(self.tools)} tools")
            else:
                self._load_legacy_mcp_config(config)
                logger.info(f"Loaded 旧版 MCP config: {len(self.servers)} servers, {len(self.tools)} tools")

        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            self._load_default_config()

    def _load_standard_mcp_config(self, config: Dict[str, Any]) -> None:
        """加载标准 MCP JSON 配置"""
        for server_name, server_config in config.get("mcpServers", {}).items():
            env = server_config.get("env", {})
            self.servers[server_name] = MCPServerConfig(
                name=server_name,
                command=server_config.get("command", ""),
                args=server_config.get("args", []),
                env=env,
                enabled=True,
                description=f"MCP服务器: {server_name}",
                tags=["builtin"],
                install_source=InstallSource.BUILTIN,
            )

        for tool_name, tool_config in config.get("tools", {}).items():
            self.tools[tool_name] = MCPToolConfig(
                name=tool_name,
                server=tool_config.get("server", ""),
                description=tool_config.get("description", ""),
            )

        agent_tools = config.get("agent_tools", {})
        for agent_name, tools_list in agent_tools.items():
            self.agent_tools_map[agent_name] = tools_list

    def _load_legacy_mcp_config(self, config: Dict[str, Any]) -> None:
        """加载旧版自定义 MCP 配置（迁移到新 schema）"""
        for server_name, server_config in config.get("servers", {}).items():
            sc = dict(server_config)
            # 迁移旧字段
            if "server_type" not in sc:
                sc["server_type"] = detect_server_type(server_config)
            if "tags" not in sc:
                sc["tags"] = []
            if "install_source" not in sc:
                sc["install_source"] = InstallSource.MANUAL
            if "is_trusted" not in sc:
                sc["is_trusted"] = True
            self.servers[server_name] = MCPServerConfig(**sc)

        for tool_name, tool_config in config.get("tools", {}).items():
            self.tools[tool_name] = MCPToolConfig(**tool_config)

    def _load_default_config(self) -> None:
        """加载默认配置"""
        for name, config in self.BUILTIN_SERVERS.items():
            self.servers[name] = config

        for tool_name, server_name in self.BUILTIN_TOOLS.items():
            self.tools[tool_name] = MCPToolConfig(
                name=tool_name,
                server=server_name,
                description=f"内置工具: {tool_name}",
            )

        self.agent_tools_map = {
            "research_agent": ["web_search", "paper_search", "file_write"],
            "analyzer_agent": ["web_search"],
            "modeler_agent": [],
            "solver_agent": ["code_execute", "file_write"],
            "writer_agent": ["file_write", "latex_compile"],
        }

    def add_custom_server(self, config: MCPServerConfig) -> None:
        """添加自定义MCP服务器"""
        if not config.server_type:
            config.server_type = detect_server_type(config.model_dump())
        if not config.install_source:
            config.install_source = InstallSource.MANUAL
        self.servers[config.name] = config
        logger.info(f"Added custom MCP server: {config.name}")

    def add_custom_tool(self, tool_config: Dict[str, Any]) -> None:
        """添加自定义工具"""
        self.custom_tools.append(tool_config)
        logger.info(f"Added custom MCP tool: {tool_config.get('name')}")

    def toggle_server_app(self, server_name: str, app: str, enabled: bool) -> bool:
        """切换服务器在特定应用的启用状态"""
        server = self.servers.get(server_name)
        if not server:
            return False
        if server.apps is None:
            server.apps = {}
        server.apps[app] = enabled
        return True

    def get_server_tags(self) -> List[str]:
        """获取所有可用标签"""
        tags = set()
        for s in self.servers.values():
            tags.update(s.tags)
        return sorted(tags)

    def get_tools_for_agent(self, agent_name: str) -> List[str]:
        """获取Agent可用的工具列表"""
        if agent_name in self.agent_tools_map:
            return self.agent_tools_map[agent_name]
        agent_tools_map = {
            "research_agent": ["web_search", "paper_search", "arxiv_search", "arxiv_download", "arxiv_abstract", "arxiv_citation", "scholar_search", "file_write"],
            "analyzer_agent": ["web_search", "bing_search", "sequentialthinking", "paper_search", "arxiv_search", "arxiv_abstract", "scholar_search"],
            "modeler_agent": ["sequentialthinking", "web_search", "paper_search", "arxiv_search", "arxiv_abstract", "scholar_search"],
            "solver_agent": ["file_read", "file_write", "web_search", "paper_search"],
            "writer_agent": ["file_read", "file_write", "web_search", "paper_search", "arxiv_abstract"],
        }
        return agent_tools_map.get(agent_name, [])

    def get_server_config(self, server_name: str) -> Optional[MCPServerConfig]:
        """获取服务器配置"""
        return self.servers.get(server_name)

    def list_servers(self) -> List[Dict[str, Any]]:
        """列出所有服务器"""
        result = []
        for name, config in self.servers.items():
            entry = {
                "name": name,
                "command": config.command,
                "args": config.args,
                "enabled": config.enabled,
                "description": config.description,
            }
            # 添加 CC Switch 扩展字段
            if config.url:
                entry["url"] = config.url
            if config.headers:
                entry["headers"] = config.headers
            if config.tags:
                entry["tags"] = config.tags
            if config.disabled_tools:
                entry["disabled_tools"] = config.disabled_tools
            if config.apps:
                entry["apps"] = config.apps
            if config.install_source:
                entry["install_source"] = config.install_source
            if config.server_type:
                entry["server_type"] = config.server_type
            entry["is_trusted"] = config.is_trusted
            result.append(entry)
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有工具（过滤禁用的）"""
        tools = []
        for name, config in self.tools.items():
            # 检查是否在某个服务器的 disabled_tools 中
            disabled = False
            for server in self.servers.values():
                if name in server.disabled_tools:
                    disabled = True
                    break
            if not disabled:
                tools.append({
                    "name": name,
                    "server": config.server,
                    "description": config.description,
                })
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
