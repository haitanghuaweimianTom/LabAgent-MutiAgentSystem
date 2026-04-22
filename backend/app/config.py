"""
数学建模多Agent系统 - 配置管理
"""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "数学建模多Agent系统"
    app_version: str = "3.0.0"
    debug: bool = True

    api_prefix: str = "/api/v1"
    cors_origins: List[str] = ["*"]

    default_model: str = "minimax-m2.7"
    fallback_model: str = "minimax-m2.1"
    api_base_url: str = "https://api.minimax.chat/v1"
    minimax_api_key: str = ""

    # ===== Claude Code 后端配置 =====
    # 各Agent的默认LLM后端: "minimax" | "claude"
    # analyzer / modeler / solver 默认使用 claude
    # research  / writer   默认使用 minimax
    default_llm_backend: str = "minimax"

    # Claude Code CLI 路径（留空则自动搜索PATH）
    claude_code_path: str = ""

    # 本地 claude-code-source 目录路径（供集成使用）
    claude_code_source_path: str = "D:/coding/MathModel-MutiAgentSyStem/claude-code-source"

    # Claude Code MCP 工具（逗号分隔的工具名，留空则不启用MCP）
    # 可用工具: bing_search, web_search, paper_search, python_execute, sequentialthinking
    claude_mcp_tools: str = "bing_search,web_search,paper_search,sequentialthinking"

    # Claude Code 模型（支持 claude-3-5-sonnet-20241022 等）
    claude_model: str = "claude-3-5-sonnet-20241022"

    # Claude Code 温度
    claude_temperature: float = 0.3

    # Claude Code 最大输出 token
    claude_max_tokens: int = 8192

    # Claude Code MCP 服务器配置路径（JSON文件）
    claude_mcp_config_path: str = ""

    # 允许使用 Claude Code 后端的 Agent 列表
    claude_enabled_agents: List[str] = ["analyzer_agent", "modeler_agent", "solver_agent", "research_agent", "writer_agent"]

    # GitHub 仓库配置
    main_repo: str = "https://github.com/haitanghuaweimianTom/MathModel-MutiAgentSystem"
    github_personal_access_token: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
