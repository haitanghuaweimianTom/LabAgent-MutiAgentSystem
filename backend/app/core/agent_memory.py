"""Agent 独立记忆 — 每个 Agent 的工作风格、案例、偏好与技能。"""
import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AGENT_MEMORY_DIR = Path(__file__).parent.parent.parent / "data" / "memory" / "agents"
AGENT_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

MAX_SUCCESS_CASES = 100
MAX_FAILURE_CASES = 100
CASE_TTL_DAYS = 90
CASE_TTL_EXTENDED_DAYS = 180
SUMMARY_INTERVAL = 5  # 每 5 个新案例触发一次 LLM 摘要


@dataclass
class AgentPreferences:
    model_type: str = ""
    temperature: float = 0.7
    max_tokens: int = 8192
    tool_preferences: List[str] = field(default_factory=list)
    output_format: str = "json"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentPreferences":
        return cls(**data)


@dataclass
class AgentSkill:
    skill_name: str = ""
    proficiency: float = 0.5
    last_used: str = ""
    usage_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSkill":
        return cls(**data)


@dataclass
class AgentCase:
    case_id: str = ""
    task_id: str = ""
    problem_type: str = ""
    method: str = ""
    outcome: str = ""
    impact_score: float = 0.5
    recency_score: float = 1.0
    created_at: str = ""
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentCase":
        return cls(**data)

    def effective_score(self) -> float:
        """综合评分：重要性 × 时间衰减。"""
        return self.impact_score * self.recency_score


class AgentProfileMemory:
    """单个 Agent 的独立记忆。"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.work_style: str = ""
        self.success_cases: List[AgentCase] = []
        self.failure_cases: List[AgentCase] = []
        self.preferences = AgentPreferences()
        self.skill_inventory: List[AgentSkill] = []
        self.collaboration_notes: List[str] = []
        self._path = AGENT_MEMORY_DIR / f"{agent_name}.json"
        self._load()

    def _load(self):
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text("utf-8"))
            self.work_style = data.get("work_style", "")
            self.success_cases = [AgentCase.from_dict(c) for c in data.get("success_cases", [])]
            self.failure_cases = [AgentCase.from_dict(c) for c in data.get("failure_cases", [])]
            self.preferences = AgentPreferences.from_dict(data.get("preferences", {}))
            self.skill_inventory = [AgentSkill.from_dict(s) for s in data.get("skill_inventory", [])]
            self.collaboration_notes = data.get("collaboration_notes", [])
        except Exception as e:
            logger.warning(f"加载 Agent 记忆失败 {self.agent_name}: {e}")

    def save(self):
        try:
            data = {
                "agent_name": self.agent_name,
                "work_style": self.work_style,
                "preferences": self.preferences.to_dict(),
                "success_cases": [c.to_dict() for c in self.success_cases],
                "failure_cases": [c.to_dict() for c in self.failure_cases],
                "skill_inventory": [s.to_dict() for s in self.skill_inventory],
                "collaboration_notes": self.collaboration_notes,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
            tmp.replace(self._path)
        except Exception as e:
            logger.warning(f"保存 Agent 记忆失败 {self.agent_name}: {e}")

    def add_case(
        self,
        case_type: str,
        task_id: str,
        problem_type: str,
        method: str,
        outcome: str,
        impact_score: float = 0.5,
        summary: str = "",
    ):
        """添加成功/失败案例。"""
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        case = AgentCase(
            case_id=f"{self.agent_name}_{int(time.time() * 1000)}",
            task_id=task_id,
            problem_type=problem_type,
            method=method,
            outcome=outcome,
            impact_score=max(0.0, min(1.0, impact_score)),
            recency_score=1.0,
            created_at=now,
            summary=summary,
        )
        if case_type == "success":
            self.success_cases.append(case)
            self._enforce_limit(self.success_cases, MAX_SUCCESS_CASES)
        else:
            self.failure_cases.append(case)
            self._enforce_limit(self.failure_cases, MAX_FAILURE_CASES)
        self.save()

    def _enforce_limit(self, cases: List[AgentCase], limit: int):
        """超出上限时按 effective_score 淘汰最低分案例。"""
        if len(cases) <= limit:
            return
        self._update_recency_scores(cases)
        cases.sort(key=lambda c: c.effective_score(), reverse=True)
        del cases[limit:]

    def _update_recency_scores(self, cases: List[AgentCase]):
        now = time.time()
        for c in cases:
            try:
                t = time.mktime(time.strptime(c.created_at, "%Y-%m-%dT%H:%M:%S"))
                days = (now - t) / 86400.0
                c.recency_score = math.exp(-days / 30.0)
            except Exception:
                c.recency_score = 0.5

    def retrieve_relevant_cases(self, problem_type: str, top_k: int = 3) -> List[AgentCase]:
        """按问题类型关键词匹配 + 综合评分排序，返回最相关案例。"""
        all_cases = self.success_cases + self.failure_cases
        if not all_cases:
            return []
        self._update_recency_scores(all_cases)

        problem_lower = problem_type.lower()

        def score(c: AgentCase) -> float:
            # 问题类型匹配奖励
            type_match = 1.0 if problem_lower and problem_lower in c.problem_type.lower() else 0.0
            # 方法匹配奖励
            method_match = 0.5 if c.method and any(k in c.method.lower() for k in problem_lower.split()) else 0.0
            return c.effective_score() + type_match + method_match

        ranked = sorted(all_cases, key=score, reverse=True)
        return ranked[:top_k]

    def get_profile_prompt(self, problem_type: str = "", top_k: int = 3) -> str:
        """生成注入 prompt 的 Agent 个人经验文本。"""
        lines = [f"【{self.agent_name} 个人经验】"]
        if self.work_style:
            lines.append(f"工作风格：{self.work_style}")
        if self.preferences.model_type:
            lines.append(f"偏好配置：model={self.preferences.model_type}, temperature={self.preferences.temperature}")

        cases = self.retrieve_relevant_cases(problem_type, top_k)
        if cases:
            lines.append("相关案例：")
            for c in cases:
                tag = "成功" if c in self.success_cases else "失败"
                lines.append(f"  - [{tag}] {c.problem_type} | 方法：{c.method} | 结果：{c.outcome}")
                if c.summary:
                    lines.append(f"    教训：{c.summary}")

        if self.collaboration_notes:
            lines.append("协作备注：")
            for note in self.collaboration_notes[-3:]:
                lines.append(f"  - {note}")

        return "\n".join(lines)

    def update_skill(self, skill_name: str, proficiency: Optional[float] = None):
        for s in self.skill_inventory:
            if s.skill_name == skill_name:
                if proficiency is not None:
                    s.proficiency = max(0.0, min(1.0, proficiency))
                s.usage_count += 1
                s.last_used = time.strftime("%Y-%m-%dT%H:%M:%S")
                self.save()
                return
        self.skill_inventory.append(AgentSkill(
            skill_name=skill_name,
            proficiency=proficiency or 0.5,
            last_used=time.strftime("%Y-%m-%dT%H:%M:%S"),
            usage_count=1,
        ))
        self.save()

    def add_collaboration_note(self, note: str):
        self.collaboration_notes.append(note)
        if len(self.collaboration_notes) > 50:
            self.collaboration_notes = self.collaboration_notes[-50:]
        self.save()


class AgentProfileMemoryStore:
    """全局 Agent 独立记忆存储。"""

    def __init__(self):
        self._profiles: Dict[str, AgentProfileMemory] = {}

    def get(self, agent_name: str) -> AgentProfileMemory:
        if agent_name not in self._profiles:
            self._profiles[agent_name] = AgentProfileMemory(agent_name)
        return self._profiles[agent_name]

    def list_agents(self) -> List[str]:
        return sorted([p.stem for p in AGENT_MEMORY_DIR.glob("*.json")])


# 全局单例
_agent_profile_store: Optional[AgentProfileMemoryStore] = None


def get_agent_profile_store() -> AgentProfileMemoryStore:
    global _agent_profile_store
    if _agent_profile_store is None:
        _agent_profile_store = AgentProfileMemoryStore()
    return _agent_profile_store


def get_agent_profile(agent_name: str) -> AgentProfileMemory:
    return get_agent_profile_store().get(agent_name)
