"""
Base Agent Classes
==================

Core base classes for the agent system.
Separated to avoid circular imports.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Type
from dataclasses import dataclass, field
from enum import Enum


class AgentRole(Enum):
    """Agent role definitions."""
    PROBLEM_ANALYZER = "problem_analyzer"
    DATA_PROCESSOR = "data_processor"
    MODEL_BUILDER = "model_builder"
    SOLVER = "solver"
    VISUALIZER = "visualizer"
    REPORTER = "reporter"
    COORDINATOR = "coordinator"


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    role: AgentRole
    description: str
    system_prompt: str = ""
    tools: List[str] = field(default_factory=list)
    max_iterations: int = 5
    timeout: int = 300


@dataclass
class AgentMessage:
    """Message passed between agents."""
    sender: str
    receiver: Optional[str]
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    All agents inherit from this class and implement:
    - analyze(): Core analysis logic
    - get_prompt(): Return the agent's system prompt
    """

    def __init__(self, config: AgentConfig):
        """Initialize agent with configuration."""
        self.config = config
        self.name = config.name
        self.role = config.role
        self.description = config.description
        self.tools = config.tools
        self.max_iterations = config.max_iterations
        self.state: Dict[str, Any] = {}
        self.messages: List[AgentMessage] = []

    @abstractmethod
    def analyze(self, input_data: Any) -> Dict[str, Any]:
        """Core analysis logic - must be implemented by subclasses."""
        pass

    def get_prompt(self) -> str:
        """Get agent's system prompt."""
        return self.config.system_prompt

    def update_state(self, key: str, value: Any) -> None:
        """Update agent state."""
        self.state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get value from agent state."""
        return self.state.get(key, default)

    def receive_message(self, message: AgentMessage) -> None:
        """Receive a message from another agent."""
        self.messages.append(message)

    def send_message(self, receiver: str, content: Any,
                     metadata: Dict[str, Any] = None) -> AgentMessage:
        """Create a message to send to another agent."""
        msg = AgentMessage(
            sender=self.name,
            receiver=receiver,
            content=content,
            metadata=metadata or {}
        )
        return msg

    def broadcast(self, content: Any, metadata: Dict[str, Any] = None) -> AgentMessage:
        """Broadcast message to all agents."""
        return self.send_message(None, content, metadata)

    def reset(self) -> None:
        """Reset agent state."""
        self.state = {}
        self.messages = []


class AgentRegistry:
    """Registry for managing available agents."""

    _agents: Dict[str, Type[BaseAgent]] = {}
    _configs: Dict[str, AgentConfig] = {}

    @classmethod
    def register(cls, name: str, agent_class: Type[BaseAgent],
                 config: AgentConfig):
        """Register an agent class with its configuration."""
        cls._agents[name] = agent_class
        cls._configs[name] = config

    @classmethod
    def get_agent(cls, name: str) -> Optional[BaseAgent]:
        """Get an instance of a registered agent."""
        if name in cls._agents:
            config = cls._configs[name]
            return cls._agents[name](config)
        return None

    @classmethod
    def list_agents(cls) -> List[str]:
        """List all registered agent names."""
        return list(cls._agents.keys())

    @classmethod
    def get_config(cls, name: str) -> Optional[AgentConfig]:
        """Get configuration for a registered agent."""
        return cls._configs.get(name)


def register_agent(name: str,
                   role: AgentRole,
                   description: str,
                   tools: List[str] = None,
                   max_iterations: int = 5):
    """
    Decorator to register an agent class.

    Usage:
        @register_agent("my_agent", AgentRole.SOLVER, "Solves problems")
        class MySolverAgent(BaseAgent):
            ...
    """
    def decorator(cls: Type[BaseAgent]) -> Type[BaseAgent]:
        config = AgentConfig(
            name=name,
            role=role,
            description=description,
            tools=tools or [],
            max_iterations=max_iterations
        )
        AgentRegistry.register(name, cls, config)
        return cls
    return decorator
