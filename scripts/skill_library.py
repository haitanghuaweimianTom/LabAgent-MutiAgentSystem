"""
Skill Library - Reusable, verified solutions across projects (Voyager-style).

Skills store three kinds of reusable knowledge:
  - code:   a verified, working solver/implementation (entry gated by execution +
            quality evidence). Description is generated from the problem text.
  - writing: paper / prose patterns that produced good output.
  - prompt:  a small prompt patch (<= 3 sentences) fixing a recurring failure.

Skill entries are versioned: adding a skill for the same underlying problem
signature bumps the version while keeping the previous one, so older code is
always recoverable (Voyager's versioning behavior).

Retrieval is embedding/lexical similarity against the skill's search text
(description + when_to_use), gated by a threshold so unrelated skills are not
mixed into prompts.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from embedding_client import EmbeddingClient

__all__ = ["SkillKind", "Skill", "SkillLibrary"]


class SkillKind(str, Enum):
    CODE = "code"
    WRITING = "writing"
    PROMPT = "prompt"


@dataclass
class Skill:
    skill_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    kind: str = "code"                # SkillKind value
    name: str = ""
    description: str = ""
    content: str = ""
    version: int = 1
    when_to_use: str = ""
    template_id: str = ""
    entry_evidence: dict[str, Any] = field(default_factory=dict)
    use_count: int = 0
    created_at: float = field(default_factory=time.time)
    run_id: str = ""

    def aggregate_text(self) -> str:
        return (self.description + " " + self.when_to_use).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "version": self.version,
            "when_to_use": self.when_to_use,
            "template_id": self.template_id,
            "entry_evidence": self.entry_evidence,
            "use_count": self.use_count,
            "created_at": self.created_at,
            "run_id": self.run_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        return cls(
            skill_id=data.get("skill_id", ""),
            kind=data.get("kind", "code"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            content=data.get("content", ""),
            version=int(data.get("version", 1) or 1),
            when_to_use=data.get("when_to_use", ""),
            template_id=data.get("template_id", ""),
            entry_evidence=data.get("entry_evidence", {}),
            use_count=int(data.get("use_count", 0) or 0),
            created_at=data.get("created_at", 0.0),
            run_id=data.get("run_id", ""),
        )


# Keywords used to generate a "code" skill's description from the problem text.
_ALGO_KEYWORDS = [
    "VRPTW", "optimization", "规划", "调度", "路径", "约束", "整数规划",
    "线性规划", "动态规划", "贪心", "分支定界", "遗传算法", "模拟退火",
    "graph neural", "时间窗", "classifier", "回归", "分类", "linear programming",
]


def _generate_code_description(problem: str, code: str, template_id: str) -> str:
    """Rule-based description for a code skill (zero LLM cost, Voyager-style)."""
    head = (problem or "").strip()[:80]
    hits = [kw for kw in _ALGO_KEYWORDS if kw.lower() in (problem + code).lower()]
    algo = ", ".join(hits[:5]) if hits else template_id
    return f"{head} | 算法: {algo}" if head else f"{template_id} 求解技能"


class SkillLibrary:
    """Persistent JSONL store of skills with similarity retrieval."""

    def __init__(
        self,
        store_dir: Path | str,
        embedding: EmbeddingClient | None = None,
    ) -> None:
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "skills.jsonl"
        self.embedding = embedding or EmbeddingClient()

    @property
    def path(self) -> Path:
        return self._path

    def load_all(self) -> list[Skill]:
        if not self._path.exists():
            return []
        out: list[Skill] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Skill.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    def count(self) -> int:
        return len(self.load_all())

    def _append(self, skill: Skill) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(skill.to_dict(), ensure_ascii=False) + "\n")

    def _latest_version(self, name: str) -> int:
        return max((s.version for s in self.load_all() if s.name == name), default=0)

    def add_skill(
        self,
        kind: str,
        name: str,
        description: str,
        content: str,
        *,
        when_to_use: str = "",
        template_id: str = "",
        evidence: dict[str, Any] | None = None,
        run_id: str = "",
    ) -> Skill:
        version = self._latest_version(name) + 1
        skill = Skill(
            skill_id=uuid.uuid4().hex[:12],
            kind=kind,
            name=name,
            description=description,
            content=content,
            version=version,
            when_to_use=when_to_use,
            template_id=template_id,
            entry_evidence=evidence or {},
            run_id=run_id,
        )
        self._append(skill)
        return skill

    def name_for_problem(self, problem: str) -> str:
        from issue_signature import normalize_text

        tokens = (normalize_text(problem) or "generic").split()
        base = "-".join(tokens[:3]) if tokens else "generic"
        return f"sol-{base}"[:48]

    def add_code_skill(
        self,
        problem: str,
        code: str,
        template_id: str,
        evidence: dict[str, Any] | None = None,
        run_id: str = "",
    ) -> Skill:
        name = self.name_for_problem(problem)
        description = _generate_code_description(problem, code, template_id)
        return self.add_skill(
            kind="code",
            name=name,
            description=description,
            content=code,
            when_to_use=problem,
            template_id=template_id,
            evidence=evidence,
            run_id=run_id or "",
        )

    def retrieve(self, query: str, top_k: int = 3, threshold: float = 0.05) -> list[Skill]:
        """Return up to top_k skills ranked by similarity to the query."""
        skills = self.load_all()
        if not skills:
            return []
        scored: list[tuple[float, Skill]] = []
        q = query or ""
        for s in skills:
            target = s.aggregate_text() or s.content
            sim = self.embedding.similarity(q, target)
            scored.append((sim, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for sim, s in scored if sim >= threshold][:top_k]

    def record_use(self, skill_id: str) -> None:
        if not skill_id:
            return
        skills = self.load_all()
        updated = False
        for s in skills:
            if s.skill_id == skill_id:
                s.use_count += 1
                updated = True
        if updated:
            self._rewrite_all(skills)

    def _rewrite_all(self, skills: list[Skill]) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            for s in skills:
                f.write(json.dumps(s.to_dict(), ensure_ascii=False) + "\n")