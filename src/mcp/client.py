"""
MCP 客户端实现
==============

封装 mcp Python SDK，提供简化的 MCP 客户端接口。
修复了 AsyncExitStack 在任务取消时的问题。
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent, ImageContent, EmbeddedResource

logger = logging.getLogger(__name__)


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
    """MCP 客户端 - 封装 mcp SDK

    修复了 AsyncExitStack 在任务取消/超时时的问题：
    - 使用独立的退出栈管理连接生命周期
    - 在 disconnect 时忽略取消作用域错误
    - 支持重复 disconnect 调用
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.session: Optional[ClientSession] = None
        self._transport_stack = None  # 独立管理 transport
        self._session_stack = None    # 独立管理 session
        self._connected = False
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

        # 使用独立的 exit stacks 管理 transport 和 session
        # 这样即使一个出问题，另一个也能正确清理
        from contextlib import AsyncExitStack

        self._transport_stack = AsyncExitStack()
        self._session_stack = AsyncExitStack()

        try:
            stdio_transport = await self._transport_stack.enter_async_context(
                stdio_client(server_params)
            )
            read_stream, write_stream = stdio_transport

            self.session = await self._session_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self.session.initialize()
            self._connected = True
        except Exception as e:
            # 连接失败时清理已打开的资源
            await self._cleanup_force()
            raise

    async def disconnect(self) -> None:
        """断开连接（安全版本，忽略取消作用域错误）"""
        if not self._connected and not self.session:
            return

        self._connected = False
        self.session = None

        # 按相反顺序关闭 exit stacks
        # 忽略 "exit cancel scope in different task" 错误
        for stack in (self._session_stack, self._transport_stack):
            if stack is not None:
                try:
                    await stack.aclose()
                except RuntimeError as e:
                    # 忽略取消作用域相关的错误
                    if "cancel scope" in str(e).lower():
                        logger.debug(f"Ignoring cancel scope error during disconnect: {e}")
                    else:
                        raise
                except Exception as e:
                    logger.debug(f"Error during disconnect cleanup: {e}")

        self._transport_stack = None
        self._session_stack = None

    async def _cleanup_force(self) -> None:
        """强制清理（忽略所有错误）"""
        self._connected = False
        self.session = None

        for stack in (self._session_stack, self._transport_stack):
            if stack is not None:
                try:
                    await stack.aclose()
                except Exception:
                    pass

        self._transport_stack = None
        self._session_stack = None

    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出服务器提供的工具"""
        if not self.session or not self._connected:
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
        if not self.session or not self._connected:
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
        if not self.session or not self._connected:
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
        if not self.session or not self._connected:
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
        return f"MCPClient(name={self.config.name}, connected={self._connected})"
