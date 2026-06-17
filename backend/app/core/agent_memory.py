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
CASE_COMPACT_INTERVAL = 10  # 每追加 10 个案例后 compact 一次


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
    """单个 Agent 的独立记忆。

    存储拆分：
    - ``{agent_name}.json``：metadata（work_style / preferences / skills / collaboration_notes）
    - ``{agent_name}_cases.jsonl``：success/failure 案例，按行追加

    案例采用追加写（append-only），避免每次 add_case 都全量写盘。
    仅 metadata 变更时才会重写 ``.json``；案例数量达到阈值时触发 compact。
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.work_style: str = ""
        self.success_cases: List[AgentCase] = []
        self.failure_cases: List[AgentCase] = []
        self.preferences = AgentPreferences()
        self.skill_inventory: List[AgentSkill] = []
        self.collaboration_notes: List[str] = []
        self._path = AGENT_MEMORY_DIR / f"{agent_name}.json"
        self._cases_path = AGENT_MEMORY_DIR / f"{agent_name}_cases.jsonl"
        self._load()

    def _load(self):
        """加载 metadata 与案例；自动迁移旧格式（cases 内嵌在 .json 中）。"""
        # 1) 加载 metadata
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text("utf-8"))
                self.work_style = data.get("work_style", "")
                self.preferences = AgentPreferences.from_dict(data.get("preferences", {}))
                self.skill_inventory = [AgentSkill.from_dict(s) for s in data.get("skill_inventory", [])]
                self.collaboration_notes = data.get("collaboration_notes", [])
            except Exception as e:
                logger.warning(f"加载 Agent metadata 失败 {self.agent_name}: {e}")

        # 2) 迁移：旧格式把 cases 存在 .json 里，且没有 .jsonl
        if self._path.exists() and not self._cases_path.exists():
            try:
                data = json.loads(self._path.read_text("utf-8"))
                legacy_success = data.get("success_cases", [])
                legacy_failure = data.get("failure_cases", [])
                if legacy_success or legacy_failure:
                    self._cases_path.write_text("", encoding="utf-8")
                    for c in legacy_success:
                        self._append_case_line(c, "success")
                    for c in legacy_failure:
                        self._append_case_line(c, "failure")
                    logger.info(f"已迁移 {self.agent_name} 的旧案例到 jsonl")
                    # 重写 metadata 去掉旧 cases 字段
                    self.save()
            except Exception as e:
                logger.warning(f"迁移 Agent 案例失败 {self.agent_name}: {e}")

        # 3) 加载 jsonl 案例
        if self._cases_path.exists():
            try:
                for line in self._cases_path.read_text("utf-8").splitlines():
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    case_type = record.pop("_case_type", "success")
                    case = AgentCase.from_dict(record)
                    if case_type == "success":
                        self.success_cases.append(case)
                    else:
                        self.failure_cases.append(case)
                self._enforce_limit(self.success_cases, MAX_SUCCESS_CASES)
                self._enforce_limit(self.failure_cases, MAX_FAILURE_CASES)
            except Exception as e:
                logger.warning(f"加载 Agent 案例失败 {self.agent_name}: {e}")

    def save(self):
        """保存 metadata（不含 cases）；cases 通过 ``_append_case_line`` 增量追加。"""
        try:
            data = {
                "agent_name": self.agent_name,
                "work_style": self.work_style,
                "preferences": self.preferences.to_dict(),
                "skill_inventory": [s.to_dict() for s in self.skill_inventory],
                "collaboration_notes": self.collaboration_notes,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
            tmp.replace(self._path)
        except Exception as e:
            logger.warning(f"保存 Agent metadata 失败 {self.agent_name}: {e}")

    def _append_case_line(self, case_dict: Dict[str, Any], case_type: str):
        """向 jsonl 追加一条案例；失败不抛异常。"""
        try:
            record = dict(case_dict)
            record["_case_type"] = case_type
            line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
            with self._cases_path.open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.warning(f"追加 Agent 案例失败 {self.agent_name}: {e}")

    def _compact_cases(self):
        """按上限淘汰低分案例后重写 jsonl；控制文件无限增长。"""
        try:
            self._enforce_limit(self.success_cases, MAX_SUCCESS_CASES)
            self._enforce_limit(self.failure_cases, MAX_FAILURE_CASES)
            lines: List[str] = []
            for c in self.success_cases:
                record = c.to_dict()
                record["_case_type"] = "success"
                lines.append(json.dumps(record, ensure_ascii=False, default=str))
            for c in self.failure_cases:
                record = c.to_dict()
                record["_case_type"] = "failure"
                lines.append(json.dumps(record, ensure_ascii=False, default=str))
            tmp = self._cases_path.with_suffix(".tmp")
            tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
            tmp.replace(self._cases_path)
        except Exception as e:
            logger.warning(f"Compact Agent 案例失败 {self.agent_name}: {e}")

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
        """添加成功/失败案例；案例写入采用 append-only。"""
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

        # 追加写案例，metadata 不变则不重写
        self._append_case_line(case.to_dict(), case_type)

        # 定期 compact，避免 jsonl 无限增长
        total_cases = len(self.success_cases) + len(self.failure_cases)
        if total_cases % CASE_COMPACT_INTERVAL == 0:
            self._compact_cases()

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
        """返回所有有记忆文件的 Agent（兼容旧 .json 与新 .jsonl）。"""
        names: set = set()
        for p in AGENT_MEMORY_DIR.glob("*.json"):
            names.add(p.stem)
        for p in AGENT_MEMORY_DIR.glob("*_cases.jsonl"):
            names.add(p.stem.replace("_cases", ""))
        return sorted(names)


# 全局单例
_agent_profile_store: Optional[AgentProfileMemoryStore] = None


def get_agent_profile_store() -> AgentProfileMemoryStore:
    global _agent_profile_store
    if _agent_profile_store is None:
        _agent_profile_store = AgentProfileMemoryStore()
    return _agent_profile_store


def get_agent_profile(agent_name: str) -> AgentProfileMemory:
    return get_agent_profile_store().get(agent_name)
