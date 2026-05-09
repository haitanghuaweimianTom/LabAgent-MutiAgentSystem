from typing import Any, Dict, Optional
from .agent import Agent


class Task:
    """A unit of work assigned to an agent."""

    def __init__(
        self,
        description: str,
        agent: Agent,
        expected_output: str = "",
        context: str = "",
        output_key: Optional[str] = None,
    ):
        self.description = description
        self.agent = agent
        self.expected_output = expected_output
        self.context = context
        self.output_key = output_key
        self.output: str = ""

    def execute(self, shared_memory: Dict[str, Any]) -> str:
        ctx = self.context
        if shared_memory and self.output_key:
            deps = [f"{k}: {str(v)[:300]}" for k, v in shared_memory.items() if k != self.output_key]
            if deps:
                ctx += "\n\n共享记忆：\n" + "\n".join(deps)
        self.output = self.agent.execute(self.description, ctx)
        if self.output_key:
            shared_memory[self.output_key] = self.output
        return self.output
