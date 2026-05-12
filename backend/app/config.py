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

    default_model: str = ""
    fallback_model: str = ""
    api_base_url: str = ""
    minimax_api_key: str = ""

    # ===== Kimi 后端配置（已废弃，使用 Provider 系统）=====
    kimi_api_key: str = ""
    kimi_base_url: str = ""

    # ===== 多 LLM Provider 配置 =====
    # Anthropic
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = "claude-sonnet-4-6-20250514"
    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-pro"
    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:latest"
    # 默认使用的 Provider: "anthropic" | "openai" | "gemini" | "ollama" | "claude_cli" | "minimax"
    default_llm_provider: str = "claude_cli"

    # ===== Claude Code 后端配置 =====
    # 各Agent的默认LLM后端: "minimax" | "claude"
    # analyzer / modeler / solver 默认使用 claude
    # research  / writer   默认使用 minimax
    default_llm_backend: str = "minimax"

    # Claude Code CLI 路径（留空则自动搜索PATH）
    claude_code_path: str = ""

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
