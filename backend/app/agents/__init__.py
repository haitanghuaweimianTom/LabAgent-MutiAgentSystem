"""Agents包"""
from .base import BaseAgent, AgentFactory
from .orchestrator import Orchestrator
from .research_agent import ResearchAgent
from .analyzer_agent import AnalyzerAgent
from .modeler_agent import ModelerAgent
from .solver_agent import SolverAgent
from .writer_agent import WriterAgent
from .algorithm_engineer_agent import AlgorithmEngineerAgent
from .financial_analyst_agent import FinancialAnalystAgent
from .figure_agent import FigureAgent

try:
    from .data_agent import DataAgent
except ImportError:
    DataAgent = None

__all__ = [
    "BaseAgent", "AgentFactory", "Orchestrator",
    "ResearchAgent", "AnalyzerAgent", "ModelerAgent",
    "SolverAgent", "WriterAgent", "DataAgent",
    "AlgorithmEngineerAgent", "FinancialAnalystAgent",
    "FigureAgent",
]
