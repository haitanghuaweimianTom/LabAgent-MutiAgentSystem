"""
统一工作流引擎
================

融合 LLM-MM-Agent 的 Coordinator + DAG + Critique-Improvement 架构
与 cherry-studio 的 Agent Manager + Knowledge Base + Document Processing 能力

核心组件:
- Coordinator: DAG调度与黑板内存
- PaperTemplate: 通用论文模板系统
- CritiqueEngine: Actor-Critic-Improvement 质量保障
- CodeExecutor: Claude CLI 代码执行沙箱
- PaperGenerator: 大纲驱动的论文章节生成
"""

from .coordinator import Coordinator, TaskNode, DependencyType
from .templates import (
    PaperTemplate,
    MathModelingTemplate,
    CourseworkTemplate,
    FinancialAnalysisTemplate,
    get_template,
    list_templates,
)
from .critique_engine import CritiqueEngine
from .code_executor import CodeExecutor
from .paper_generator import PaperGenerator

__all__ = [
    "Coordinator",
    "TaskNode",
    "DependencyType",
    "PaperTemplate",
    "MathModelingTemplate",
    "CourseworkTemplate",
    "FinancialAnalysisTemplate",
    "get_template",
    "CritiqueEngine",
    "CodeExecutor",
    "PaperGenerator",
]
