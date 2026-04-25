"""
Agent System Module
==================

Generic agent framework for mathematical modeling problem solving.
Based on LLM-MM-Agent architecture with multi-agent collaboration.

Core Components:
- BaseAgent: Abstract base class for all agents
- ProblemAnalyzerAgent: Analyzes problem statements
- DataProcessorAgent: Handles data loading and preprocessing
- ModelBuilderAgent: Constructs mathematical models
- SolverAgent: Implements algorithms
- VisualizerAgent: Generates figures
- ReporterAgent: Compiles papers/reports
"""

# Import base classes first to avoid circular imports
from .base import (
    BaseAgent,
    AgentConfig,
    AgentRole,
    AgentMessage,
    AgentRegistry,
    register_agent
)

# Import specialized agents
from .specialized import (
    ProblemAnalyzerAgent,
    MethodRetrieverAgent,
    ModelBuilderAgent,
    ChartCreatorAgent,
    PaperWriterAgent
)

# Import solver and coordinator
from .solver_agent import SelfHealingSolver, ActorCriticAgent
from .coordinator import MethodKnowledgeBase, get_knowledge_base

# Export public API
__all__ = [
    'BaseAgent',
    'AgentConfig',
    'AgentRole',
    'AgentMessage',
    'AgentRegistry',
    'register_agent',
    'ProblemAnalyzerAgent',
    'MethodRetrieverAgent',
    'ModelBuilderAgent',
    'ChartCreatorAgent',
    'PaperWriterAgent',
    'SelfHealingSolver',
    'ActorCriticAgent',
    'MethodKnowledgeBase',
    'get_knowledge_base',
]
