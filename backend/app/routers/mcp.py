"""
数学建模多Agent系统 - MCP工具路由

提供MCP工具管理API：
- 列出所有MCP工具
- 获取工具详情
- 添加自定义工具
- 启用/禁用工具
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ..mcp import get_mcp_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mcp", tags=["MCP工具"])


@router.get("/servers", response_model=List[Dict[str, Any]])
async def list_servers() -> List[Dict[str, Any]]:
    """
    列出所有MCP服务器

    Returns:
        服务器列表
    """
    mcp_manager = get_mcp_manager()
    return mcp_manager.list_servers()


@router.get("/tools", response_model=List[Dict[str, Any]])
async def list_tools() -> List[Dict[str, Any]]:
    """
    列出所有MCP工具

    Returns:
        工具列表
    """
    mcp_manager = get_mcp_manager()
    return mcp_manager.list_tools()


@router.get("/tools/{tool_name}", response_model=Dict[str, Any])
async def get_tool(tool_name: str) -> Dict[str, Any]:
    """
    获取指定工具信息

    Args:
        tool_name: 工具名称

    Returns:
        工具详细信息
    """
    mcp_manager = get_mcp_manager()
    tools = mcp_manager.list_tools()

    for tool in tools:
        if tool["name"] == tool_name:
            return tool

    raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")


@router.get("/agents/{agent_name}/tools", response_model=List[str])
async def get_agent_tools(agent_name: str) -> List[str]:
    """
    获取Agent可用的工具列表

    Args:
        agent_name: Agent名称

    Returns:
        工具名称列表
    """
    mcp_manager = get_mcp_manager()
    return mcp_manager.get_tools_for_agent(agent_name)


@router.post("/tools", response_model=Dict[str, Any])
async def add_custom_tool(tool_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    添加自定义工具

    Args:
        tool_config: 工具配置

    Returns:
        添加结果
    """
    mcp_manager = get_mcp_manager()

    tool_name = tool_config.get("name")
    if not tool_name:
        raise HTTPException(status_code=400, detail="Tool name is required")

    mcp_manager.add_custom_tool(tool_config)

    logger.info(f"Added custom tool: {tool_name}")

    return {
        "success": True,
        "message": f"Tool {tool_name} added",
        "tool": tool_config,
    }


@router.post("/servers", response_model=Dict[str, Any])
async def add_custom_server(server_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    添加自定义MCP服务器

    Args:
        server_config: 服务器配置

    Returns:
        添加结果
    """
    from ..mcp import MCPServerConfig

    mcp_manager = get_mcp_manager()

    try:
        config = MCPServerConfig(**server_config)
        mcp_manager.add_custom_server(config)

        logger.info(f"Added custom server: {config.name}")

        return {
            "success": True,
            "message": f"Server {config.name} added",
            "server": config.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/servers/{server_name}/toggle", response_model=Dict[str, Any])
async def toggle_server(server_name: str, enabled: bool) -> Dict[str, Any]:
    """
    启用/禁用服务器

    Args:
        server_name: 服务器名称
        enabled: 是否启用

    Returns:
        操作结果
    """
    mcp_manager = get_mcp_manager()

    server_config = mcp_manager.get_server_config(server_name)
    if not server_config:
        raise HTTPException(status_code=404, detail=f"Server {server_name} not found")

    server_config.enabled = enabled

    return {
        "success": True,
        "message": f"Server {server_name} {'enabled' if enabled else 'disabled'}",
        "server": server_config.name,
    }


@router.get("/config/export", response_model=Dict[str, Any])
async def export_config() -> Dict[str, Any]:
    """
    导出当前MCP配置

    Returns:
        配置内容
    """
    mcp_manager = get_mcp_manager()
    return mcp_manager.export_config()


@router.get("/tags", response_model=List[str])
async def get_tags() -> List[str]:
    """获取所有MCP服务器标签"""
    mcp_manager = get_mcp_manager()
    return mcp_manager.get_server_tags()


@router.patch("/servers/{server_name}/apps", response_model=Dict[str, Any])
async def toggle_server_app(server_name: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """切换服务器在特定应用的启用状态"""
    mcp_manager = get_mcp_manager()
    server = mcp_manager.get_server_config(server_name)
    if not server:
        raise HTTPException(status_code=404, detail=f"Server {server_name} not found")

    app = body.get("app", "")
    enabled = body.get("enabled", True)
    if not app:
        raise HTTPException(status_code=400, detail="app is required")

    ok = mcp_manager.toggle_server_app(server_name, app, enabled)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to toggle server app")

    return {
        "success": True,
        "message": f"Server {server_name} app {app} {'enabled' if enabled else 'disabled'}",
        "apps": server.apps or {},
    }


@router.post("/servers/{server_name}/disabled-tools", response_model=Dict[str, Any])
async def update_disabled_tools(server_name: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """更新服务器的禁用工具列表"""
    mcp_manager = get_mcp_manager()
    server = mcp_manager.get_server_config(server_name)
    if not server:
        raise HTTPException(status_code=404, detail=f"Server {server_name} not found")

    disabled_tools = body.get("disabled_tools", [])
    server.disabled_tools = disabled_tools

    return {
        "success": True,
        "message": f"Updated disabled tools for server {server_name}",
        "disabled_tools": disabled_tools,
    }


@router.post("/discover", response_model=Dict[str, Any])
async def discover_tools(body: Dict[str, Any] = {}) -> Dict[str, Any]:
    """工具发现 — 返回所有可用服务器及其工具"""
    mcp_manager = get_mcp_manager()
    servers = mcp_manager.list_servers()
    tools = mcp_manager.list_tools()

    by_tag = {}
    for server in servers:
        for tag in server.get("tags", []):
            if tag not in by_tag:
                by_tag[tag] = []
            by_tag[tag].append(server["name"])

    return {
        "servers": servers,
        "tools": tools,
        "tags": by_tag,
        "total_servers": len(servers),
        "total_tools": len(tools),
    }


@router.post("/import-json", response_model=Dict[str, Any])
async def import_mcp_json(body: Dict[str, Any]) -> Dict[str, Any]:
    """导入标准 MCP JSON 配置

    支持两种格式:

    1. Cherry Studio / Claude Desktop 标准格式:
    {
      "mcpServers": {
        "server_name": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-xxx"],
          "env": {"API_KEY": "xxx"}
        }
      }
    }

    2. HTTP/SSE 传输格式:
    {
      "mcpServers": {
        "server_name": {
          "url": "http://localhost:8080/mcp",
          "headers": {"Authorization": "Bearer xxx"}
        }
      }
    }
    """
    from ..mcp.config import MCPServerConfig
    from ..mcp.schemas import detect_server_type, InstallSource, McpServerType

    mcp_servers = body.get("mcpServers", {})
    if not mcp_servers:
        raise HTTPException(status_code=400, detail="缺少 mcpServers 字段")

    mcp_manager = get_mcp_manager()
    imported = []
    failed = []

    for server_name, server_config in mcp_servers.items():
        try:
            command = server_config.get("command", "")
            args = server_config.get("args", [])
            env = server_config.get("env", {})
            url = server_config.get("url")
            headers = server_config.get("headers", {})

            server_type = McpServerType.STREAMABLE_HTTP if url else McpServerType.STDIO

            config = MCPServerConfig(
                name=server_name,
                command=command,
                args=args,
                env=env,
                enabled=True,
                description=f"从 JSON 导入: {server_name}",
                url=url,
                headers=headers,
                tags=["imported"],
                disabled_tools=[],
                install_source=InstallSource.MANUAL,
                is_trusted=True,
                server_type=server_type,
            )

            mcp_manager.add_custom_server(config)
            imported.append(server_name)
        except Exception as e:
            failed.append({"name": server_name, "error": str(e)})

    return {
        "success": True,
        "imported": imported,
        "failed": failed,
        "total": len(mcp_servers),
    }


@router.post("/export-json", response_model=Dict[str, Any])
async def export_mcp_json() -> Dict[str, Any]:
    """导出为标准 MCP JSON 格式 (Cherry Studio / Claude Desktop 兼容)"""
    mcp_manager = get_mcp_manager()
    config = mcp_manager.export_config()

    # 转换为标准 mcpServers 格式
    mcp_servers = {}
    for name, srv_config in config.get("mcpServers", {}).items():
        entry = {}
        if srv_config.get("command"):
            entry["command"] = srv_config["command"]
        if srv_config.get("args"):
            entry["args"] = srv_config["args"]
        if srv_config.get("env"):
            entry["env"] = srv_config["env"]
        if entry:
            mcp_servers[name] = entry

    return {
        "mcpServers": mcp_servers,
    }
