"""
Memory Module - Persistent Knowledge Base

Inspired by Sibyl's 5-tier architecture and AutoResearchClaw's memory system.
Provides semantic retrieval of past research experiences with time-decay weighting.

Components:
- MemoryCategory: Categorization for memories
- MemoryEntry: Single memory with content, category, metadata
- MemoryStore: JSONL-backed store with semantic search and time-decay weighting
- add(): Store new memories
- recall(): Retrieve relevant memories based on semantic similarity
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "MemoryCategory",
    "MemoryEntry",
    "MemoryStore",
]


class MemoryCategory:
    """Memory categories for organizing knowledge."""

    IDEATION = "ideation"
    EXPERIMENT = "experiment"
    WRITING = "writing"
    ANALYSIS = "analysis"
    REFERENCE = "reference"
    SYSTEM = "system"
    PIPELINE = "pipeline"


@dataclass
class MemoryEntry:
    """Single memory entry with content and metadata."""

    content: str
    category: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "category": self.category,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "source": self.source,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        return cls(
            content=data.get("content", ""),
            category=data.get("category", "general"),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", 0.0),
            source=data.get("source", ""),
            tags=data.get("tags", []),
        )


def _tokenize(text: str) -> list[str]:
    """Simple tokenization for semantic similarity."""
    return re.findall(r'\w+', text.lower())


def _semantic_similarity(query: str, content: str) -> float:
    """Compute simple semantic similarity using word overlap.

    For production, consider using embeddings. This is a lightweight fallback.
    """
    query_tokens = set(_tokenize(query))
    content_tokens = set(_tokenize(content))

    if not query_tokens or not content_tokens:
        return 0.0

    intersection = query_tokens & content_tokens
    union = query_tokens | content_tokens

    if not union:
        return 0.0

    # Jaccard similarity with length normalization
    jaccard = len(intersection) / len(union)

    # Boost for exact substring match
    substring_boost = 0.3 if query.lower() in content.lower() else 0.0

    return min(jaccard + substring_boost, 1.0)


def _time_weight(timestamp: float, half_life_days: float = 30.0) -> float:
    """Compute time-decay weight. Recent memories matter more."""
    if timestamp <= 0:
        return 0.0
    half_life_seconds = half_life_days * 86400.0
    return math.exp(-0.693 * (time.time() - timestamp) / half_life_seconds)


class MemoryStore:
    """JSONL-backed store for persistent research knowledge.

    Supports:
    - Semantic search with time-decay weighting
    - Category-based filtering
    - Tag-based filtering
    - Cross-project knowledge persistence
    """

    def __init__(self, store_dir: Path | str) -> None:
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._memory_path = self._dir / "memory.jsonl"

    @property
    def memory_path(self) -> Path:
        return self._memory_path

    def add(
        self,
        content: str,
        category: str = "general",
        metadata: dict[str, Any] | None = None,
        source: str = "",
        tags: list[str] | None = None,
    ) -> MemoryEntry:
        """Add a new memory entry."""
        entry = MemoryEntry(
            content=content,
            category=category,
            metadata=metadata or {},
            timestamp=time.time(),
            source=source,
            tags=tags or [],
        )
        with self._memory_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return entry

    def add_many(self, entries: list[MemoryEntry]) -> int:
        """Add multiple memory entries atomically. Returns count added."""
        if not entries:
            return 0
        with self._memory_path.open("a", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return len(entries)

    def load_all(self) -> list[MemoryEntry]:
        """Load all memories from disk."""
        if not self._memory_path.exists():
            return []
        memories: list[MemoryEntry] = []
        for line in self._memory_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                memories.append(MemoryEntry.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                continue
        return memories

    def recall(
        self,
        query: str,
        category: str | None = None,
        tags: list[str] | None = None,
        max_results: int = 5,
        min_score: float = 0.1,
    ) -> list[MemoryEntry]:
        """Recall relevant memories based on semantic similarity.

        Combines semantic similarity with time-decay weighting to rank results.
        """
        all_memories = self.load_all()
        scored: list[tuple[float, MemoryEntry]] = []

        for memory in all_memories:
            # Category filter
            if category and memory.category != category:
                continue

            # Tag filter
            if tags:
                if not any(t in memory.tags for t in tags):
                    continue

            # Compute relevance score
            sim = _semantic_similarity(query, memory.content)
            time_w = _time_weight(memory.timestamp)

            # Combined score: 70% semantic + 30% recency
            score = 0.7 * sim + 0.3 * time_w

            if score >= min_score:
                scored.append((score, memory))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:max_results]]

    def count(self, category: str | None = None) -> int:
        """Count memories, optionally filtered by category."""
        if category is None:
            return len(self.load_all())
        return sum(1 for m in self.load_all() if m.category == category)

    def get_categories(self) -> dict[str, int]:
        """Get memory counts by category."""
        categories: dict[str, int] = {}
        for memory in self.load_all():
            categories[memory.category] = categories.get(memory.category, 0) + 1
        return categories

    def export_to_evolution(self, evolution_store: Any) -> int:
        """Export memories to an evolution store."""
        append_fn = getattr(evolution_store, "append", None)
        if append_fn is None or not callable(append_fn):
            return 0

        memories = self.load_all()
        exported = 0
        for memory in memories:
            try:
                from self_evolution import LessonEntry
                lesson = LessonEntry(
                    stage_name="memory_export",
                    category=memory.category,
                    severity="info",
                    description=memory.content[:500],
                    timestamp=memory.timestamp,
                    metadata={**memory.metadata, "source": "memory"},
                )
                append_fn(lesson)
                exported += 1
            except Exception:
                continue
        return exported

    def search_by_tag(self, tag: str) -> list[MemoryEntry]:
        """Find all memories with a specific tag."""
        return [m for m in self.load_all() if tag in m.tags]

    def get_recent(self, limit: int = 10) -> list[MemoryEntry]:
        """Get the most recent memories."""
        all_memories = self.load_all()
        all_memories.sort(key=lambda m: m.timestamp, reverse=True)
        return all_memories[:limit]

    def clear(self, category: str | None = None) -> int:
        """Clear memories, optionally filtered by category. Returns count removed."""
        if category is None:
            count = self.count()
            if self._memory_path.exists():
                self._memory_path.unlink()
            return count

        # Remove specific category
        all_memories = self.load_all()
        to_keep = [m for m in all_memories if m.category != category]
        removed = len(all_memories) - len(to_keep)

        if self._memory_path.exists():
            self._memory_path.unlink()
        if to_keep:
            with self._memory_path.open("a", encoding="utf-8") as f:
                for entry in to_keep:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

        return removed
