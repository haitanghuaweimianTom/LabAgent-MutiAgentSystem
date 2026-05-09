from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from .agent import Agent
from .task import Task


class Process(Enum):
    SEQUENTIAL = "sequential"
    HIERARCHICAL = "hierarchical"
    CONSENSUS = "consensus"


class Crew:
    """Orchestrates a team of agents to complete a set of tasks."""

    def __init__(
        self,
        agents: List[Agent],
        tasks: List[Task],
        process: Process = Process.SEQUENTIAL,
        manager_agent: Optional[Agent] = None,
        shared_memory: Optional[Dict[str, Any]] = None,
        verbose: bool = True,
    ):
        self.agents = agents
        self.tasks = tasks
        self.process = process
        self.manager_agent = manager_agent
        self.shared_memory = shared_memory or {}
        self.verbose = verbose
        for a in agents:
            a.crew = self

    def kickoff(self) -> Dict[str, Any]:
        if self.verbose:
            print(f"[Crew] 启动，流程：{self.process.value}，任务数：{len(self.tasks)}")
        if self.process == Process.SEQUENTIAL:
            return self._run_sequential()
        elif self.process == Process.HIERARCHICAL:
            return self._run_hierarchical()
        elif self.process == Process.CONSENSUS:
            return self._run_consensus()
        return self._run_sequential()

    def _run_sequential(self) -> Dict[str, Any]:
        for task in self.tasks:
            task.execute(self.shared_memory)
        return self.shared_memory

    def _run_hierarchical(self) -> Dict[str, Any]:
        manager = self.manager_agent or self.agents[0]
        for task in self.tasks:
            if manager != task.agent and manager.allow_delegation:
                manager.delegate(task.description, task.agent, task.context)
            else:
                task.execute(self.shared_memory)
        return self.shared_memory

    def _run_consensus(self) -> Dict[str, Any]:
        for task in self.tasks:
            results = []
            for agent in self.agents:
                r = agent.execute(task.description, task.context)
                results.append((agent.role, r))
            if len(results) > 1 and self.manager_agent:
                consensus_prompt = f"以下是对同一任务的不同结果，请综合形成共识：\n"
                for role, r in results:
                    consensus_prompt += f"\n[{role}]\n{r[:500]}\n"
                consensus = self.manager_agent.execute(consensus_prompt, "")
                self.shared_memory[task.output_key or f"consensus_{id(task)}"] = consensus
        return self.shared_memory
