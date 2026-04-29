"""
MCP (Model Context Protocol) 客户端模块
========================================

借鉴 cherry-studio 的 MCP 架构设计，
为数学建模多Agent系统提供工具调用能力。

支持的 MCP 传输方式:
- stdio: 通过子进程连接本地 MCP 服务器
- sse: 通过 HTTP SSE 连接远程 MCP 服务器

使用方法:
    from src.mcp import MCPToolManager

    # 连接 MCP 服务器
    manager = MCPToolManager()
    await manager.connect_stdio("npx", ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])

    # 列出可用工具
    tools = await manager.list_tools()

    # 调用工具
    result = await manager.call_tool("read_file", {"path": "/tmp/test.txt"})
"""

from .client import MCPClient, MCPServerConfig
from .tool_manager import MCPToolManager, ToolInfo

__all__ = [
    "MCPClient",
    "MCPServerConfig",
    "MCPToolManager",
    "ToolInfo",
]
