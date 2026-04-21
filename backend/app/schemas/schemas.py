"""Pydantic 模型定义"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"


class TaskStep(BaseModel):
    step_id: str
    agent_name: str
    status: TaskStatus = TaskStatus.PENDING
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    current_step: Optional[str] = "0"
    total_steps: int = 0
    steps: List[TaskStep] = []
    progress_percentage: float = 0.0


class TaskResultResponse(BaseModel):
    task_id: str
    status: TaskStatus
    output: Dict[str, Any] = Field(default_factory=dict)
    completed_at: Optional[datetime] = None


class TaskCreateRequest(BaseModel):
    problem_text: str
    workflow: Optional[List[Dict[str, Any]]] = None
    mode: Optional[str] = "batch"  # "batch"=一次性, "sequential"=逐个递进
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)


class TaskCancelRequest(BaseModel):
    reason: Optional[str] = None


class ChatMessage(BaseModel):
    sender: str
    content: str
    msg_type: str = "text"
    mentions: List[str] = Field(default_factory=list)
    timestamp: Optional[datetime] = None


class WorkflowStep(BaseModel):
    agent: str
    input: Dict[str, Any] = Field(default_factory=dict)
    condition: Optional[str] = None


class WorkflowDefinition(BaseModel):
    name: str
    description: str = ""
    steps: List[WorkflowStep] = []
    enabled: bool = True
