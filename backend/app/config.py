"""
多智能体协作论文生产系统 - 配置管理
"""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "多智能体协作论文生产系统"
    app_version: str = "8.0.0"
    debug: bool = True

    api_prefix: str = "/api/v1"
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "*"]

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
    # 默认使用的 Provider: "anthropic" | "openai" | "gemini" | "ollama" | "claude_cli" | "minimax" | "mimo"
    # 留空则自动检测（优先使用 cc-switch 同步的 Provider）
    default_llm_provider: str = ""

    # ===== Claude Code 后端配置 =====
    # 各Agent的默认LLM后端: 留空则自动检测（优先使用已配置的 Provider）
    # analyzer / modeler / solver 默认使用 claude
    # research / writer 默认使用已配置 Provider
    default_llm_backend: str = ""

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
    claude_enabled_agents: List[str] = [
        "analyzer_agent", "modeler_agent", "solver_agent", "research_agent", "writer_agent",
        "peer_review_agent", "experimentation_agent",
    ]

    # ===== 学术元数据增强配置 =====
    semantic_scholar_api_key: str = ""

    # ===== LangGraph + ReAct + 自主迭代求解 功能开关 =====
    use_langgraph_orchestrator: bool = True
    use_react_tools: bool = True
    use_iterative_solver: bool = True

    # ===== 自动化实验执行配置 =====
    experiment_sandbox_enabled: bool = True
    experiment_max_runtime_seconds: int = 3600
    experiment_max_memory_mb: int = 8192
    experiment_gpu_required: bool = False
    experiment_auto_download_datasets: bool = True
    experiment_enable_ablation: bool = True
    experiment_enable_baseline: bool = True
    experiment_allow_network: bool = True

    # ===== Knowledge Graph settings =====
    kg_enabled: bool = True
    kg_extraction_batch_size: int = 5
    kg_max_traversal_depth: int = 3
    kg_rrf_weight_graph: float = 0.3

    # ===== 全自动模式配置 =====
    auto_mode_enabled: bool = True              # 全自动模式开关
    max_concurrent_tasks: int = 3               # 最大并发任务数
    task_timeout_seconds: int = 7200            # 单任务超时（2小时）
    auto_retry_on_failure: bool = True          # 失败自动重试
    max_retry_count: int = 2                    # 最大重试次数
    human_intervention_timeout: int = 300       # 人类介入超时（5分钟无人响应则自动决策）
    experiment_max_iterations: int = 3          # 实验自动迭代上限

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
