"""MCP 工具管理模块

提供 MCP 工具的定义和管理功能。
从 base.py 中提取，减少 BaseAgent 类的职责。
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# MCP 工具注册表
MCP_SERVER_MAP: Dict[str, str] = {
    "bing_search": "bing_search",
    "web_search": "web_search",
    "paper_search": "paper_search",
    "python_execute": "python_execute",
    "sequentialthinking": "sequentialthinking",
}

# MCP 工具 Schema 定义
MCP_TOOL_SCHEMAS: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "web_search": (
        "搜索网页获取实时信息。支持 DuckDuckGo/Brave 搜索。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        }
    ),
    "bing_search": (
        "使用 Bing 搜索网页。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        }
    ),
    "paper_search": (
        "搜索学术论文。支持 Google Scholar, ArXiv, PubMed, JSTOR。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回结果数量", "default": 5},
            },
            "required": ["query"],
        }
    ),
    "arxiv_search": (
        "搜索 arXiv 论文。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "description": "最大结果数", "default": 5},
            },
            "required": ["query"],
        }
    ),
    "arxiv_download": (
        "下载 arXiv 论文 PDF。",
        {
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "arXiv 论文 ID (如 2401.12345)"},
            },
            "required": ["paper_id"],
        }
    ),
    "arxiv_abstract": (
        "获取 arXiv 论文摘要。",
        {
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "arXiv 论文 ID"},
            },
            "required": ["paper_id"],
        }
    ),
    "arxiv_citation": (
        "获取 arXiv 论文引用信息。",
        {
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "arXiv 论文 ID"},
            },
            "required": ["paper_id"],
        }
    ),
    "scholar_search": (
        "搜索 Google Scholar 学术论文。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回结果数量", "default": 5},
            },
            "required": ["query"],
        }
    ),
    "file_read": (
        "读取文件内容。",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
            },
            "required": ["path"],
        }
    ),
    "file_write": (
        "写入文件内容。",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["path", "content"],
        }
    ),
    "code_execute": (
        "执行 Python 代码。",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码"},
            },
            "required": ["code"],
        }
    ),
    "latex_compile": (
        "编译 LaTeX 文档。",
        {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "LaTeX 文件路径"},
            },
            "required": ["file_path"],
        }
    ),
    "python_execute": (
        "执行 Python 代码（通过 MCP 服务器）。",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码"},
            },
            "required": ["code"],
        }
    ),
    "sequentialthinking": (
        "逐步思考复杂问题。",
        {
            "type": "object",
            "properties": {
                "thought": {"type": "string", "description": "当前思考步骤"},
                "nextThoughtNeeded": {"type": "boolean", "description": "是否需要下一步思考"},
            },
            "required": ["thought", "nextThoughtNeeded"],
        }
    ),
}


def build_mcp_tool_def(tool_name: str) -> Optional[Dict[str, Any]]:
    """根据 MCP 工具名称构建 ToolDef（供 LLM 使用）。

    Args:
        tool_name: MCP 工具名称

    Returns:
        ToolDef 字典，如果工具不存在则返回 None
    """
    if tool_name in MCP_TOOL_SCHEMAS:
        description, parameters = MCP_TOOL_SCHEMAS[tool_name]
        return {
            "name": tool_name,
            "description": description,
            "parameters": parameters,
        }
    return None


def get_tool_schemas_for_agent(agent_name: str, agent_tools_map: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """获取指定 Agent 的工具定义列表。

    Args:
        agent_name: Agent 名称
        agent_tools_map: Agent -> 工具列表映射

    Returns:
        ToolDef 列表
    """
    tool_names = agent_tools_map.get(agent_name, [])
    tool_defs = []
    for tool_name in tool_names:
        tool_def = build_mcp_tool_def(tool_name)
        if tool_def:
            tool_defs.append(tool_def)
    return tool_defs
