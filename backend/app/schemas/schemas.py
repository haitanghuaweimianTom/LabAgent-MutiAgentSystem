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
    PREFLIGHT_RUNNING = "preflight_running"
    SELF_COLLECTING_DATA = "self_collecting_data"
    ITERATING_SOLVER = "iterating_solver"
    CANNOT_SOLVE = "cannot_solve"


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
    project_name: Optional[str] = None  # 项目名，如 "work_2026_guangzhou"
    workflow: Optional[List[Dict[str, Any]]] = None
    mode: Optional[str] = "batch"  # "batch"=一次性, "sequential"=逐个递进
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)
    data_files: Optional[List[str]] = None  # 前端选中的数据文件名列表（为空则使用全部上传文件）
    knowledge_base_id: Optional[str] = None  # 旧版字段（向后兼容）：单 KB
    knowledge_base_ids: Optional[List[str]] = None  # v5.3.0: 多 KB 列表（优先于单数）
    data_source: Optional[str] = "upload"  # "upload" / "self_collect" / "upload_and_collect"
    problem_type: Optional[str] = None  # 用户显式选择的问题类型

    def get_effective_kb_ids(self) -> List[str]:
        """v5.3.0: 解析实际使用的 KB 列表。

        优先级：
          1. knowledge_base_ids（多选）
          2. knowledge_base_id（单数，向后兼容）
          3. 空列表 → 由 Agent 自动选择（项目私有 + 全局公共）
        """
        if self.knowledge_base_ids:
            return list(self.knowledge_base_ids)
        if self.knowledge_base_id:
            return [self.knowledge_base_id]
        return []


class TaskCancelRequest(BaseModel):
    reason: Optional[str] = None


class RerunRequest(BaseModel):
    """重新执行请求 — 所有字段可选，不传则沿用历史任务配置"""
    template: Optional[str] = None
    workflow_type: Optional[str] = None
    mode: Optional[str] = None
    problem_text: Optional[str] = None  # 重新执行时可补充问题描述


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


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: float = 0
    updated_at: float = 0
    task_ids: List[str] = []
    path: str = ""
