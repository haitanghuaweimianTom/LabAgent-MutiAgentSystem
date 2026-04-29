"""
Agent 管理器模块
===============

借鉴 cherry-studio 的 AgentService 架构设计，
为数学建模多Agent系统提供可配置、可扩展的 Agent 管理。

核心组件:
- AgentConfig: Agent 配置数据类
- AgentRegistry: Agent 注册表（CRUD + 持久化）
- AgentFactory: Agent 工厂（创建实例）
- BaseAgent: Agent 抽象基类

内置 Agent 角色:
- coordinator: 主编排器
- problem_analyzer: 问题分析专家
- model_designer: 数学建模专家
- algorithm_designer: 算法设计专家
- code_writer: 代码编写专家
- result_analyzer: 结果分析专家
- chart_designer: 图表设计专家
- paper_writer: 论文撰写专家

使用方法:
    from src.agents.manager import AgentFactory, AgentRole

    # 列出所有 Agent
    agents = AgentFactory.list_available_agents()

    # 获取 Agent 配置
    registry = AgentFactory.get_registry()
    config = registry.get("builtin_problem_analyzer")

    # 创建 Agent 实例
    agent = AgentFactory.create_agent_by_role(AgentRole.PROBLEM_ANALYZER)
    system_prompt = agent.get_system_prompt()
    model = agent.get_model()

    # 注册自定义 Agent
    from src.agents.manager import AgentConfig, AgentRole
    custom_agent = AgentConfig(
        name="我的自定义Agent",
        role=AgentRole.CUSTOM,
        instructions="你是一个专业的...",
        model="gpt-4o"
    )
    registry.register(custom_agent)
"""

from .base import AgentConfig, AgentRole, BaseAgent, AgentCapability
from .registry import AgentRegistry, get_builtin_agent_configs
from .factory import AgentFactory, GenericAgent

__all__ = [
    "AgentConfig",
    "AgentRole",
    "BaseAgent",
    "AgentCapability",
    "AgentRegistry",
    "AgentFactory",
    "GenericAgent",
    "get_builtin_agent_configs",
]
