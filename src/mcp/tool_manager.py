"""
MCP 工具管理器
==============

借鉴 cherry-studio 的 MCP Hub 设计，
统一管理多个 MCP 服务器的工具发现和调用。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from pathlib import Path

from .client import MCPClient, MCPServerConfig


@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    server_name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "server_name": self.server_name,
            "description": self.description,
            "input_schema": self.input_schema,
            "enabled": self.enabled,
        }


class MCPToolManager:
    """MCP 工具管理器"""

    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
        self._tools: Dict[str, ToolInfo] = {}
        self._configs: Dict[str, MCPServerConfig] = {}

    async def connect_stdio(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> MCPClient:
        """通过 stdio 连接 MCP 服务器"""
        config = MCPServerConfig(
            name=name,
            command=command,
            args=args or [],
            env=env,
        )
        return await self._connect(config)

    async def connect_from_config(self, config_dict: Dict[str, Any]) -> MCPClient:
        """从配置字典连接 MCP 服务器"""
        config = MCPServerConfig(
            name=config_dict.get("name", "default"),
            command=config_dict.get("command"),
            args=config_dict.get("args", []),
            env=config_dict.get("env"),
            url=config_dict.get("url"),
            timeout=config_dict.get("timeout", 30),
        )
        return await self._connect(config)

    async def _connect(self, config: MCPServerConfig) -> MCPClient:
        """内部连接方法"""
        client = MCPClient(config)
        await client.connect()
        self._clients[config.name] = client
        self._configs[config.name] = config

        # 自动发现工具
        tools = await client.list_tools()
        for tool in tools:
            tool_id = f"{config.name}__{tool['name']}"
            self._tools[tool_id] = ToolInfo(
                name=tool["name"],
                server_name=config.name,
                description=tool.get("description", ""),
                input_schema=tool.get("input_schema", {}),
            )

        print(f"[MCP] 已连接服务器 '{config.name}'，发现 {len(tools)} 个工具")
        return client

    async def disconnect(self, name: Optional[str] = None) -> None:
        """断开 MCP 服务器连接"""
        if name:
            client = self._clients.pop(name, None)
            if client:
                await client.disconnect()
                # 移除该服务器的工具
                self._tools = {
                    k: v for k, v in self._tools.items()
                    if v.server_name != name
                }
                print(f"[MCP] 已断开服务器 '{name}'")
        else:
            for client in self._clients.values():
                await client.disconnect()
            self._clients.clear()
            self._tools.clear()
            print("[MCP] 已断开所有服务器")

    def list_tools(self, server_name: Optional[str] = None) -> List[ToolInfo]:
        """列出可用工具"""
        tools = list(self._tools.values())
        if server_name:
            tools = [t for t in tools if t.server_name == server_name]
        return [t for t in tools if t.enabled]

    async def call_tool(
        self,
        tool_id: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> str:
        """调用工具（支持 namespaced id: serverName__toolName）"""
        if "__" in tool_id:
            server_name, tool_name = tool_id.split("__", 1)
        else:
            # 尝试查找
            tool_info = self._tools.get(tool_id)
            if not tool_info:
                raise ValueError(f"未找到工具: {tool_id}")
            server_name = tool_info.server_name
            tool_name = tool_info.name

        client = self._clients.get(server_name)
        if not client:
            raise ValueError(f"MCP 服务器未连接: {server_name}")

        return await client.call_tool(tool_name, arguments)

    def get_tool_info(self, tool_id: str) -> Optional[ToolInfo]:
        """获取工具信息"""
        return self._tools.get(tool_id)

    def get_server_status(self) -> Dict[str, Dict[str, Any]]:
        """获取服务器状态"""
        return {
            name: {
                "connected": client.session is not None,
                "command": client.config.command,
                "args": client.config.args,
            }
            for name, client in self._clients.items()
        }

    def save_configs(self, filepath: str) -> None:
        """保存服务器配置到文件"""
        data = {
            "servers": [
                {
                    "name": c.name,
                    "command": c.command,
                    "args": c.args,
                    "env": c.env,
                    "url": c.url,
                    "timeout": c.timeout,
                }
                for c in self._configs.values()
            ],
            "tools": [t.to_dict() for t in self._tools.values()],
            "saved_at": datetime.now().isoformat(),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def load_configs(self, filepath: str) -> int:
        """从配置文件加载并连接服务器"""
        if not Path(filepath).exists():
            return 0

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        count = 0
        for server_config in data.get("servers", []):
            try:
                await self.connect_from_config(server_config)
                count += 1
            except Exception as e:
                print(f"[MCP] 连接服务器失败 {server_config.get('name')}: {e}")

        return count

    def __repr__(self) -> str:
        return f"MCPToolManager(servers={len(self._clients)}, tools={len(self._tools)})"


# 全局工具管理器实例
_default_tool_manager: Optional[MCPToolManager] = None


def get_tool_manager() -> MCPToolManager:
    """获取全局 MCP 工具管理器"""
    global _default_tool_manager
    if _default_tool_manager is None:
        _default_tool_manager = MCPToolManager()
    return _default_tool_manager
