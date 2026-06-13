"""MCP 客户端封装 —— 基于官方 mcp SDK 的 stdio 传输。"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """MCP 服务器配置（与 research_agent.py 中引用的接口保持一致）。"""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


class MCPClient:
    """MCP stdio 客户端封装。

    用法：
        config = MCPServerConfig(name="arxiv_server", command="uvx", args=["..."])
        client = MCPClient(config)
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("search_papers", {"query": "..."})
        await client.disconnect()
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._session: Optional[ClientSession] = None
        self._exit_stack = None
        self._stdio_transport = None

    async def connect(self) -> None:
        """建立到 MCP 服务器的 stdio 连接。"""
        if self._session is not None:
            return

        params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=self.config.env or None,
        )
        logger.debug(f"Connecting to MCP server {self.config.name}: {self.config.command} {self.config.args}")

        self._exit_stack = __import__("contextlib").AsyncExitStack()
        stdio_transport = await self._exit_stack.enter_async_context(stdio_client(params))
        self._stdio_transport = stdio_transport
        read, write = stdio_transport
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session
        logger.debug(f"MCP server {self.config.name} connected")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出服务器提供的工具。"""
        if self._session is None:
            raise RuntimeError("MCP client not connected")
        tools_resp = await self._session.list_tools()
        tools = getattr(tools_resp, "tools", tools_resp)
        if not isinstance(tools, list):
            logger.warning(f"Unexpected list_tools response type: {type(tools)}")
            return []
        return [{"name": t.name, "description": getattr(t, "description", "")} for t in tools]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
        """调用指定工具并返回文本结果。"""
        if self._session is None:
            raise RuntimeError("MCP client not connected")

        logger.debug(f"Calling MCP tool {tool_name} on {self.config.name}")
        result = await self._session.call_tool(tool_name, arguments)
        contents = getattr(result, "content", result)
        if not isinstance(contents, list):
            return str(contents)

        text_parts: List[str] = []
        for item in contents:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
                else:
                    text_parts.append(str(item))
            elif hasattr(item, "type") and getattr(item, "type") == "text":
                text_parts.append(str(getattr(item, "text", "")))
            else:
                text_parts.append(str(item))

        return "\n".join(text_parts) if text_parts else None

    async def disconnect(self) -> None:
        """关闭连接。"""
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.debug(f"Error closing MCP client: {e}")
            finally:
                self._exit_stack = None
                self._session = None
                self._stdio_transport = None
