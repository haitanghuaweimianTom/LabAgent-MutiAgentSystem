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
