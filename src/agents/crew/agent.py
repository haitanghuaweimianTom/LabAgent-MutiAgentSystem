import json
from typing import Any, Callable, Dict, List, Optional


class Agent:
    """Role-based agent with memory and tool use."""

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str = "",
        tools: Optional[List[Callable]] = None,
        allow_delegation: bool = True,
        verbose: bool = True,
        llm_callback: Optional[Callable[[str, str], str]] = None,
        memory_system: Optional[Any] = None,
    ):
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.tools = tools or []
        self.allow_delegation = allow_delegation
        self.verbose = verbose
        self.llm_callback = llm_callback
        self.memory: List[Dict[str, Any]] = []
        self.crew: Optional[Any] = None
        self.memory_system = memory_system  # MemorySystem instance (optional)

    def execute(self, task_description: str, context: str = "") -> str:
        if self.verbose:
            print(f"  [{self.role}] 执行任务...")
        prompt = self._build_prompt(task_description, context)
        system = f"你是{self.role}。{self.goal}。{self.backstory}"
        result = ""
        if self.llm_callback:
            result = self.llm_callback(prompt, system)
        self.memory.append({"task": task_description, "result": result})
        # Persist to memory system if available
        if self.memory_system and result:
            self.memory_system.store(
                self.role,
                task_description[:50],
                result[:2000],
                metadata={"task": task_description, "role": self.role},
            )
        if self.verbose:
            print(f"  [{self.role}] 完成")
        return result

    def _build_prompt(self, task: str, context: str) -> str:
        parts = [f"任务：{task}"]

        # Inject persistent memory context
        if self.memory_system:
            mem_context = self.memory_system.load_agent_memories(self.role)
            shared_context = self.memory_system.load_shared_context(task[:100])
            if mem_context:
                parts.append(f"持久记忆：\n{mem_context}")
            if shared_context:
                parts.append(f"共享记忆：\n{shared_context}")

        if context:
            parts.append(f"上下文：{context}")
        if self.memory:
            recent = self.memory[-2:]
            mem_text = "\n".join(f"- 历史任务：{m['task'][:80]}" for m in recent)
            parts.append(f"会话记忆：\n{mem_text}")
        return "\n\n".join(parts)

    def delegate(self, task_description: str, to_agent: "Agent", context: str = "") -> str:
        if not self.allow_delegation:
            return self.execute(task_description, context)
        if self.verbose:
            print(f"  [{self.role}] 委托任务给 [{to_agent.role}]")
        return to_agent.execute(task_description, context)

    def receive_message(self, sender: str, message: str) -> str:
        self.memory.append({"sender": sender, "message": message, "type": "received"})
        return self.execute(f"收到来自 {sender} 的消息，请回复：{message}", "")
