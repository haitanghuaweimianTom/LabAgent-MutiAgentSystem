"""
MCP 客户端实现
==============

封装 mcp Python SDK，提供简化的 MCP 客户端接口。
"""

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent, ImageContent, EmbeddedResource


@dataclass
class MCPServerConfig:
    """MCP 服务器配置"""
    name: str
    command: Optional[str] = None
    args: List[str] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    timeout: int = 30

    def __post_init__(self):
        if self.args is None:
            self.args = []


class MCPClient:
    """MCP 客户端 - 封装 mcp SDK"""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.session: Optional[ClientSession] = None
        self._exit_stack = AsyncExitStack()
        self._tools: List[Dict[str, Any]] = []

    async def connect(self) -> None:
        """连接到 MCP 服务器（stdio 方式）"""
        if not self.config.command:
            raise ValueError("MCP 服务器配置缺少 command")

        server_params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=self.config.env,
        )

        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = stdio_transport

        self.session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self.session.initialize()

    async def disconnect(self) -> None:
        """断开连接"""
        await self._exit_stack.aclose()
        self.session = None

    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出服务器提供的工具"""
        if not self.session:
            raise RuntimeError("未连接到 MCP 服务器")

        result = await self.session.list_tools()
        self._tools = []
        for tool in result.tools:
            self._tools.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            })
        return self._tools

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> str:
        """调用工具"""
        if not self.session:
            raise RuntimeError("未连接到 MCP 服务器")

        result = await self.session.call_tool(name, arguments=arguments or {})

        # 处理返回结果
        outputs = []
        for content in result.content:
            if isinstance(content, TextContent):
                outputs.append(content.text)
            elif isinstance(content, ImageContent):
                outputs.append(f"[Image: {content.mimeType}]")
            elif isinstance(content, EmbeddedResource):
                outputs.append(f"[Resource]")

        return "\n".join(outputs)

    async def list_resources(self) -> List[Dict[str, Any]]:
        """列出可用资源"""
        if not self.session:
            raise RuntimeError("未连接到 MCP 服务器")

        result = await self.session.list_resources()
        return [
            {
                "uri": r.uri,
                "name": r.name,
                "mime_type": r.mimeType,
                "description": r.description,
            }
            for r in result.resources
        ]

    async def read_resource(self, uri: str) -> str:
        """读取资源内容"""
        if not self.session:
            raise RuntimeError("未连接到 MCP 服务器")

        result = await self.session.read_resource(uri)
        contents = []
        for content in result.contents:
            if hasattr(content, "text"):
                contents.append(content.text)
            else:
                contents.append(str(content))
        return "\n".join(contents)

    def __repr__(self) -> str:
        return f"MCPClient(name={self.config.name}, connected={self.session is not None})"
