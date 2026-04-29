"""
Agent 工厂
==========

借鉴 cherry-studio 的 AgentService 工厂模式，
实现 Agent 的创建和初始化。
"""

from typing import Dict, List, Optional, Any, Type

from .base import AgentConfig, AgentRole, BaseAgent
from .registry import AgentRegistry


class AgentFactory:
    """Agent 工厂 - 创建和管理 Agent 实例"""

    _registry: Optional[AgentRegistry] = None
    _agent_classes: Dict[AgentRole, Type[BaseAgent]] = {}

    @classmethod
    def get_registry(cls) -> AgentRegistry:
        """获取 Agent 注册表"""
        if cls._registry is None:
            cls._registry = AgentRegistry()
        return cls._registry

    @classmethod
    def create_agent(cls, agent_id: str) -> Optional[BaseAgent]:
        """根据 ID 创建 Agent 实例"""
        config = cls.get_registry().get(agent_id)
        if not config:
            return None
        return cls._create_from_config(config)

    @classmethod
    def create_agent_by_role(cls, role: AgentRole) -> Optional[BaseAgent]:
        """根据角色创建 Agent 实例（返回第一个匹配的）"""
        agents = cls.get_registry().get_by_role(role)
        if not agents:
            return None
        return cls._create_from_config(agents[0])

    @classmethod
    def create_agent_by_name(cls, name: str) -> Optional[BaseAgent]:
        """根据名称创建 Agent 实例"""
        config = cls.get_registry().get_by_name(name)
        if not config:
            return None
        return cls._create_from_config(config)

    @classmethod
    def _create_from_config(cls, config: AgentConfig) -> BaseAgent:
        """根据配置创建 Agent 实例"""
        agent_class = cls._agent_classes.get(config.role, GenericAgent)
        return agent_class(config)

    @classmethod
    def register_agent_class(cls, role: AgentRole, agent_class: Type[BaseAgent]) -> None:
        """注册自定义 Agent 类"""
        cls._agent_classes[role] = agent_class

    @classmethod
    def list_available_agents(cls, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """列出所有可用的 Agent"""
        agents = cls.get_registry().list_agents(enabled_only=enabled_only)
        return [{
            "id": a.id,
            "name": a.name,
            "role": a.role.value,
            "description": a.description,
            "model": a.model,
            "enabled": a.enabled,
        } for a in agents]

    @classmethod
    def create_workflow_agents(cls) -> Dict[AgentRole, BaseAgent]:
        """创建工作流所需的全部 Agent"""
        workflow_roles = [
            AgentRole.PROBLEM_ANALYZER,
            AgentRole.MODEL_DESIGNER,
            AgentRole.ALGORITHM_DESIGNER,
            AgentRole.CODE_WRITER,
            AgentRole.RESULT_ANALYZER,
            AgentRole.CHART_DESIGNER,
            AgentRole.PAPER_WRITER,
        ]
        agents = {}
        for role in workflow_roles:
            agent = cls.create_agent_by_role(role)
            if agent:
                agents[role] = agent
        return agents


class GenericAgent(BaseAgent):
    """通用 Agent 实现"""

    def execute(self, context: Dict[str, Any], **kwargs) -> Any:
        """执行 Agent 任务（需要子类重写或外部注入逻辑）"""
        raise NotImplementedError(
            f"Agent {self.config.name} 未实现 execute 方法。"
            "请使用工作流引擎调用此 Agent。"
        )
