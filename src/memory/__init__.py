"""
Per-Agent Memory System (GMemory-inspired)
==========================================

Hierarchical persistent memory for multi-agent systems:
- Individual agent memory: {work_dir}/memory/{agent_name}/
- Shared/group memory: {work_dir}/memory/shared/
- Retrieval via keyword overlap scoring

Inspired by G-Memory: Tracing Hierarchical Memory for Multi-Agent Systems (NeurIPS 2026)
"""

import json
import os
import uuid
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


# Role name mapping: Chinese role -> English memory directory name
ROLE_TO_NAME = {
    "问题分析师": "analyst",
    "数学建模师": "modeler",
    "求解工程师": "solver",
    "论文写作专家": "writer",
    "协调者": "coordinator",
    "problem_analyzer": "analyst",
    "model_builder": "modeler",
    "solver": "solver",
    "writer": "writer",
    "coordinator": "coordinator",
}


class MemoryEntry:
    """Single memory entry."""

    def __init__(
        self,
        key: str,
        content: str,
        agent: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.timestamp = datetime.now().isoformat()
        self.agent = agent
        self.key = key
        self.content = content
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "agent": self.agent,
            "key": self.key,
            "content": self.content,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        entry = cls(
            key=data.get("key", ""),
            content=data.get("content", ""),
            agent=data.get("agent", ""),
            metadata=data.get("metadata", {}),
        )
        entry.id = data.get("id", entry.id)
        entry.timestamp = data.get("timestamp", entry.timestamp)
        return entry


class MemorySystem:
    """
    Hierarchical persistent memory for multi-agent systems.

    Directory structure:
        {work_dir}/memory/
            analyst/
                mem_*.json
                summary.md
            modeler/
                mem_*.json
                summary.md
            solver/
                mem_*.json
                summary.md
            writer/
                mem_*.json
                summary.md
            shared/
                mem_*.json
                analysis_summary.md
                modeling_summary.md
                results_summary.md
                ideation_results.json
    """

    def __init__(self, work_dir: str):
        self.work_dir = Path(work_dir)
        self.memory_root = self.work_dir / "memory"
        self.memory_root.mkdir(parents=True, exist_ok=True)
        (self.memory_root / "shared").mkdir(exist_ok=True)

        # In-memory cache for fast retrieval
        self._cache: Dict[str, List[MemoryEntry]] = {}
        self._shared_cache: List[MemoryEntry] = []

        # Load existing memories from disk
        self._load_all()

    def _agent_dir(self, agent_name: str) -> Path:
        """Get the memory directory for an agent."""
        name = ROLE_TO_NAME.get(agent_name, agent_name)
        d = self.memory_root / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _shared_dir(self) -> Path:
        return self.memory_root / "shared"

    def _load_all(self):
        """Load all existing memory entries from disk into cache."""
        # Load agent memories
        if not self.memory_root.exists():
            return
        for d in self.memory_root.iterdir():
            if not d.is_dir():
                continue
            agent_name = d.name
            entries = []
            for f in d.glob("mem_*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    entries.append(MemoryEntry.from_dict(data))
                except Exception:
                    pass
            if agent_name == "shared":
                self._shared_cache = entries
            else:
                self._cache[agent_name] = entries

    # =========================================================================
    # Individual Agent Memory
    # =========================================================================

    def store(
        self,
        agent_name: str,
        key: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a memory entry for an agent. Returns entry ID."""
        name = ROLE_TO_NAME.get(agent_name, agent_name)
        entry = MemoryEntry(key=key, content=content, agent=name, metadata=metadata)

        # Write to disk
        agent_dir = self._agent_dir(name)
        filepath = agent_dir / f"mem_{entry.id}.json"
        filepath.write_text(
            json.dumps(entry.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Update cache
        if name not in self._cache:
            self._cache[name] = []
        self._cache[name].append(entry)

        return entry.id

    def retrieve(
        self, agent_name: str, query: str, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant memories for an agent based on keyword overlap."""
        name = ROLE_TO_NAME.get(agent_name, agent_name)
        entries = self._cache.get(name, [])
        return self._score_and_rank(entries, query, top_k)

    # =========================================================================
    # Shared Memory
    # =========================================================================

    def store_shared(
        self,
        key: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a memory entry in shared memory. Returns entry ID."""
        entry = MemoryEntry(key=key, content=content, agent="shared", metadata=metadata)

        # Write to disk
        shared_dir = self._shared_dir()
        filepath = shared_dir / f"mem_{entry.id}.json"
        filepath.write_text(
            json.dumps(entry.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self._shared_cache.append(entry)
        return entry.id

    def retrieve_shared(
        self, query: str, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant entries from shared memory."""
        return self._score_and_rank(self._shared_cache, query, top_k)

    # =========================================================================
    # Summary Files
    # =========================================================================

    def save_agent_summary(self, agent_name: str, summary: str):
        """Save a summary file for an agent (human-readable)."""
        name = ROLE_TO_NAME.get(agent_name, agent_name)
        agent_dir = self._agent_dir(name)
        summary_path = agent_dir / "summary.md"
        summary_path.write_text(summary, encoding="utf-8")

    def save_shared_summary(self, filename: str, content: str):
        """Save a summary file in shared memory."""
        shared_dir = self._shared_dir()
        filepath = shared_dir / filename
        filepath.write_text(content, encoding="utf-8")

    def save_shared_json(self, filename: str, data: Any):
        """Save a JSON file in shared memory."""
        shared_dir = self._shared_dir()
        filepath = shared_dir / filename
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_shared_json(self, filename: str) -> Optional[Any]:
        """Load a JSON file from shared memory."""
        shared_dir = self._shared_dir()
        filepath = shared_dir / filename
        if filepath.exists():
            return json.loads(filepath.read_text(encoding="utf-8"))
        return None

    # =========================================================================
    # Prompt Injection
    # =========================================================================

    def load_agent_memories(self, agent_name: str) -> str:
        """Load formatted memory context for prompt injection."""
        name = ROLE_TO_NAME.get(agent_name, agent_name)

        parts = []

        # Load summary file if exists
        agent_dir = self._agent_dir(name)
        summary_path = agent_dir / "summary.md"
        if summary_path.exists():
            parts.append(
                f"【{name} 历史摘要】\n{summary_path.read_text(encoding='utf-8')}\n"
            )

        # Load recent memory entries
        entries = self._cache.get(name, [])
        if entries:
            parts.append(f"【{name} 最近记忆】")
            for entry in entries[-3:]:
                parts.append(
                    f"- [{entry.timestamp}] {entry.key}: {entry.content[:200]}"
                )
            parts.append("")

        return "\n".join(parts)

    def load_shared_context(self, query: str = "", top_k: int = 3) -> str:
        """Load formatted shared memory context for prompt injection."""
        parts = []

        # Load summary files
        shared_dir = self._shared_dir()
        for summary_file in sorted(shared_dir.glob("*.md")):
            content = summary_file.read_text(encoding="utf-8")
            parts.append(
                f"【共享记忆: {summary_file.name}】\n{content[:500]}\n"
            )

        # Load relevant entries
        entries = self.retrieve_shared(query, top_k) if query else self._shared_cache[-top_k:]
        if entries:
            parts.append("【共享记忆条目】")
            for entry in entries:
                parts.append(f"- {entry.key}: {entry.content[:200]}")
            parts.append("")

        return "\n".join(parts)

    # =========================================================================
    # Internal
    # =========================================================================

    def _score_and_rank(
        self, entries: List[MemoryEntry], query: str, top_k: int
    ) -> List[Dict[str, Any]]:
        """Score entries by keyword overlap with query, return top_k."""
        if not query or not entries:
            return [e.to_dict() for e in entries[-top_k:]]

        query_words = set(self._tokenize(query))
        scored = []
        for entry in entries:
            content_words = set(self._tokenize(entry.content))
            key_words = set(self._tokenize(entry.key))
            all_words = content_words | key_words
            if not all_words:
                continue
            overlap = len(query_words & all_words) / len(query_words)
            scored.append((entry, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [entry.to_dict() for entry, score in scored[:top_k]]

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple tokenization: split on non-alphanumeric, keep CJK chars."""
        # Extract CJK characters and words
        tokens = re.findall(r"[一-鿿]+|[a-zA-Z0-9]+", text.lower())
        return tokens
