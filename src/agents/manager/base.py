"""
Agent 管理基类
==============

借鉴 cherry-studio 的 Agent 架构设计，
实现可配置、可扩展的 Agent 管理系统。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import json
import uuid
from pathlib import Path


class AgentRole(str, Enum):
    """Agent 角色类型"""
    COORDINATOR = "coordinator"
    PROBLEM_ANALYZER = "problem_analyzer"
    MODEL_DESIGNER = "model_designer"
    ALGORITHM_DESIGNER = "algorithm_designer"
    CODE_WRITER = "code_writer"
    RESULT_ANALYZER = "result_analyzer"
    CHART_DESIGNER = "chart_designer"
    PAPER_WRITER = "paper_writer"
    CUSTOM = "custom"


@dataclass
class AgentCapability:
    """Agent 能力定义"""
    name: str
    description: str
    enabled: bool = True


@dataclass
class AgentConfig:
    """Agent 配置（借鉴 cherry-studio AgentEntity）"""
    id: str = ""
    name: str = ""
    role: AgentRole = AgentRole.CUSTOM
    description: str = ""
    instructions: str = ""  # 系统提示词
    model: str = ""  # 主模型
    plan_model: str = ""  # 规划模型
    small_model: str = ""  # 轻量模型（用于简单任务）
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    timeout: int = 600
    capabilities: List[AgentCapability] = field(default_factory=list)
    configuration: Dict[str, Any] = field(default_factory=dict)
    accessible_paths: List[str] = field(default_factory=list)  # 可访问的路径
    tools: List[str] = field(default_factory=list)  # 可用工具列表
    enabled: bool = True
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"agent_{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            from datetime import datetime
            self.created_at = datetime.now().isoformat()
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role.value,
            "description": self.description,
            "instructions": self.instructions,
            "model": self.model,
            "plan_model": self.plan_model,
            "small_model": self.small_model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "capabilities": [
                {"name": c.name, "description": c.description, "enabled": c.enabled}
                for c in self.capabilities
            ],
            "configuration": self.configuration,
            "accessible_paths": self.accessible_paths,
            "tools": self.tools,
            "enabled": self.enabled,
            "sort_order": self.sort_order,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        """从字典创建"""
        caps = [
            AgentCapability(**c) for c in data.get("capabilities", [])
        ]
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            role=AgentRole(data.get("role", "custom")),
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            model=data.get("model", ""),
            plan_model=data.get("plan_model", ""),
            small_model=data.get("small_model", ""),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens"),
            timeout=data.get("timeout", 600),
            capabilities=caps,
            configuration=data.get("configuration", {}),
            accessible_paths=data.get("accessible_paths", []),
            tools=data.get("tools", []),
            enabled=data.get("enabled", True),
            sort_order=data.get("sort_order", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def save(self, filepath: str) -> None:
        """保存到 JSON 文件"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "AgentConfig":
        """从 JSON 文件加载"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


class BaseAgent(ABC):
    """Agent 抽象基类"""

    def __init__(self, config: AgentConfig):
        self.config = config

    @abstractmethod
    def execute(self, context: Dict[str, Any], **kwargs) -> Any:
        """执行 Agent 任务"""
        pass

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self.config.instructions

    def get_model(self, task_type: str = "default") -> str:
        """根据任务类型获取合适的模型"""
        if task_type == "plan" and self.config.plan_model:
            return self.config.plan_model
        if task_type == "simple" and self.config.small_model:
            return self.config.small_model
        return self.config.model or ""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.config.id}, name={self.config.name}, role={self.config.role.value})"
