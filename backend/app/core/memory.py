"""多智能体记忆系统

基于 arXiv 文献的混合架构（Generative Agents + MemGPT + LbMAS Blackboard）：
- Working Memory（工作记忆 / 黑板）：当前任务的共享结构化状态，所有 Agent 读写
- Episodic Memory（情景记忆）：时间戳化的会话事件，带自动摘要压缩
- Lessons Learned（经验记忆）：跨任务持久化的可复用知识，随使用增长

参考：
- Generative Agents (arXiv:2304.03442) — 情景/语义/程序记忆 + 反思巩固
- MemGPT (arXiv:2310.08562) — L1/L2/L3 分层记忆 + LLM 自主提升/降级
- LbMAS (arXiv:2507.01701) — 黑板架构用于数学问题求解
- Intrinsic Memory Agents (arXiv:2508.08997) — 角色专属记忆 + 共享记忆混合
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ===== 存储路径 =====
_MEMORY_DIR: Optional[Path] = None


def _memory_dir() -> Path:
    global _MEMORY_DIR
    if _MEMORY_DIR is None:
        _MEMORY_DIR = Path(__file__).parent.parent.parent / "data" / "memory"
        _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    return _MEMORY_DIR


# ============================================================
# Working Memory（工作记忆 / 黑板）
# ============================================================

class WorkingMemory:
    """当前任务的共享黑板 — 结构化状态，所有 Agent 读写。

    设计灵感来自 LbMAS 的黑板架构和 MemGPT 的 L1 工作记忆。
    与当前 flat dict context 不同，这是一个有 schema 的共享状态对象。
    """

    def __init__(self, task_id: str = ""):
        self.task_id = task_id
        self.created_at = datetime.now().isoformat()

        # 黑板分区
        self.problem: Dict[str, Any] = {}          # 问题陈述、类型、难度
        self.constraints: List[str] = []            # 识别出的约束条件
        self.literature: List[Dict[str, Any]] = []  # 文献/资料摘要
        self.methods: List[Dict[str, Any]] = []     # 候选方法/模型
        self.decisions: List[Dict[str, Any]] = []   # 关键决策（采用/拒绝的方法及原因）
        self.results: Dict[str, Any] = {}           # 各 Agent 的求解结果
        self.data_insights: List[str] = []          # 数据分析洞察
        self.sub_problems: List[Dict[str, Any]] = []  # 子问题分解
        self.notes: List[Dict[str, Any]] = []       # 自由备注（Agent 之间的留言）

    def update_problem(self, **fields) -> None:
        self.problem.update(fields)

    def add_constraint(self, constraint: str, source: str = "") -> None:
        self.constraints.append({"text": constraint, "source": source})

    def add_literature(self, papers: List[Dict[str, Any]], source: str = "") -> None:
        for p in papers:
            p["_source"] = source
            self.literature.append(p)

    def add_method(self, method: Dict[str, Any]) -> None:
        self.methods.append(method)

    def add_decision(self, decision: str, reason: str, agent: str = "") -> None:
        self.decisions.append({
            "decision": decision,
            "reason": reason,
            "agent": agent,
            "timestamp": datetime.now().isoformat(),
        })

    def add_note(self, from_agent: str, content: str, to_agent: str = "") -> None:
        self.notes.append({
            "from": from_agent,
            "content": content,
            "to": to_agent,
            "timestamp": datetime.now().isoformat(),
        })

    def set_result(self, agent_name: str, result: Dict[str, Any]) -> None:
        self.results[agent_name] = result

    def get_context_for_agent(self, agent_name: str, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """为特定 Agent 构建上下文（根据角色过滤），可选按 token 预算裁剪。"""
        ctx = self._build_raw_context(agent_name)
        if max_tokens is None or max_tokens <= 0:
            return ctx

        # 按优先级排序字段
        priority = [
            "problem", "sub_problems", "constraints", "decisions",
            "methods", "literature", "data_insights", "notes", "agent_results",
            "previous_models", "previous_solutions",
        ]

        from ..core.token_budget import get_token_budget_manager
        budget_mgr = get_token_budget_manager("default")

        # 先全部序列化估算
        serialized = {}
        for key in priority:
            if key in ctx:
                serialized[key] = json.dumps(ctx[key], ensure_ascii=False)

        total = sum(budget_mgr.estimate_tokens(v) for v in serialized.values())
        if total <= max_tokens:
            return ctx

        # 按优先级保留内容，超出预算时裁剪低优先级字段
        remaining = max_tokens
        clipped = {}
        for key in priority:
            if key not in serialized:
                continue
            text = serialized[key]
            need = budget_mgr.estimate_tokens(text)
            if need <= remaining:
                clipped[key] = ctx[key]
                remaining -= need
            else:
                # 对低优先级字段做硬截断
                allowed_chars = int(remaining / budget_mgr.estimate_tokens(text) * len(text)) if budget_mgr.estimate_tokens(text) > 0 else 0
                if allowed_chars > 50:
                    truncated_text = text[:allowed_chars] + '..."}]'
                    try:
                        clipped[key] = json.loads(truncated_text)
                    except Exception:
                        clipped[key] = f"[已裁剪，原长度 {len(text)} 字符]"
                remaining = 0
            if remaining <= 0:
                break

        return clipped

    def _build_raw_context(self, agent_name: str) -> Dict[str, Any]:
        """原始未裁剪的 Agent 上下文。"""
        ctx = {
            "problem": self.problem,
            "sub_problems": self.sub_problems,
            "data_insights": self.data_insights,
        }

        if agent_name == "research_agent":
            ctx["literature"] = self.literature
            ctx["methods"] = self.methods
        elif agent_name == "analyzer_agent":
            ctx["literature"] = self.literature
            ctx["methods"] = self.methods
            ctx["constraints"] = self.constraints
        elif agent_name == "modeler_agent":
            ctx["literature"] = self.literature
            ctx["methods"] = self.methods
            ctx["constraints"] = self.constraints
            ctx["data_insights"] = self.data_insights
            ctx["previous_models"] = self.results.get("modeler_agent", {}).get("sub_problem_models", [])
        elif agent_name == "solver_agent":
            ctx["methods"] = self.methods
            ctx["constraints"] = self.constraints
            ctx["data_insights"] = self.data_insights
            ctx["previous_solutions"] = self.results.get("solver_agent", {}).get("sub_problem_solutions", [])
        elif agent_name == "writer_agent":
            ctx["literature"] = self.literature
            ctx["methods"] = self.methods
            ctx["decisions"] = self.decisions

        ctx["agent_results"] = {k: v for k, v in self.results.items() if k != agent_name}
        ctx["notes"] = [n for n in self.notes if n.get("to", "") in ("", agent_name)]
        return ctx

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "created_at": self.created_at,
            "problem": self.problem,
            "constraints": self.constraints,
            "literature": self.literature,
            "methods": self.methods,
            "decisions": self.decisions,
            "results": self.results,
            "data_insights": self.data_insights,
            "sub_problems": self.sub_problems,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkingMemory":
        wm = cls(task_id=data.get("task_id", ""))
        wm.created_at = data.get("created_at", wm.created_at)
        wm.problem = data.get("problem", {})
        wm.constraints = data.get("constraints", [])
        wm.literature = data.get("literature", [])
        wm.methods = data.get("methods", [])
        wm.decisions = data.get("decisions", [])
        wm.results = data.get("results", {})
        wm.data_insights = data.get("data_insights", [])
        wm.sub_problems = data.get("sub_problems", [])
        wm.notes = data.get("notes", [])
        return wm


# ============================================================
# Episodic Memory（情景记忆）
# ============================================================

class EpisodicMemory:
    """时间戳化的会话事件记录 — 带自动摘要压缩。

    灵感来自 Generative Agents 的情景记忆：原始事件太昂贵，
    需要周期性压缩为高层次摘要。
    """

    def __init__(self, task_id: str = "", max_entries: int = 50):
        self.task_id = task_id
        self.max_entries = max_entries
        self.entries: List[Dict[str, Any]] = []
        self.summary: str = ""  # 压缩后的摘要

    def record(self, agent: str, event_type: str, content: str, metadata: Optional[Dict] = None) -> None:
        self.entries.append({
            "agent": agent,
            "event_type": event_type,
            "content": content[:500],  # 截断过长内容
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        })
        # 滚动窗口
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

    def get_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        return self.entries[-n:]

    def get_by_agent(self, agent: str) -> List[Dict[str, Any]]:
        return [e for e in self.entries if e["agent"] == agent]

    def get_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        return [e for e in self.entries if e["event_type"] == event_type]

    def compress(self) -> str:
        """将原始条目压缩为高层次摘要。

        真实场景下应调用 LLM 进行摘要，这里做简单的规则压缩。
        Orchestrator 在阶段完成后可调用 LLM 做真正的压缩。
        """
        if not self.entries:
            return ""

        agent_events: Dict[str, List[str]] = {}
        for e in self.entries:
            agent_events.setdefault(e["agent"], []).append(
                f"- [{e['event_type']}] {e['content'][:100]}"
            )

        parts = [f"## {agent}\n" + "\n".join(events) for agent, events in agent_events.items()]
        self.summary = "\n\n".join(parts)
        return self.summary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "entries": self.entries,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EpisodicMemory":
        em = cls(task_id=data.get("task_id", ""))
        em.summary = data.get("summary", "")
        em.entries = data.get("entries", [])
        return em


# ============================================================
# Lessons Learned（经验记忆）
# ============================================================

class LessonsMemory:
    """跨任务持久化的可复用知识 — 随使用增长。

    灵感来自 A-MEM (arXiv:2502.12110) 的 Zettelkasten 动态记忆图
    和 Generative Agents 的反思-巩固机制。

    每次任务完成后，系统提取可复用的"教训"：
    - 什么方法对哪类问题有效
    - 什么方法被拒绝了，为什么
    - 数据处理的经验教训
    - 模型选择的启发式规则
    - 实验设计经验
    - 模板特定的写作经验
    """

    # 支持的分类体系
    CATEGORIES = {
        "method_selection", "data_processing", "modeling", "solving",
        "writing", "experiment_design", "template_specific",
    }

    def __init__(self):
        self.lessons: List[Dict[str, Any]] = []
        self._load()

    def add_lesson(
        self,
        category: str,
        content: str,
        problem_type: str = "",
        method: str = "",
        success: bool = True,
        source_task: str = "",
        subcategory: str = "",
        tags: Optional[List[str]] = None,
        impact_score: int = 5,
    ) -> None:
        self.lessons.append({
            "id": f"lesson_{len(self.lessons) + 1}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "category": category,       # "method_selection" / "data_processing" / "modeling" / "solving" / "writing" / "experiment_design" / "template_specific"
            "subcategory": subcategory,  # 细分分类（如模板名: "ieee_conference"）
            "content": content,
            "problem_type": problem_type,
            "method": method,
            "success": success,
            "source_task": source_task,
            "tags": tags or [],          # 标签用于精确检索
            "impact_score": impact_score,  # 1-10 影响力评分
            "created_at": datetime.now().isoformat(),
            "use_count": 0,            # 被引用次数（用于排序）
        })

    def query(self, problem_type: str = "", category: str = "", top_k: int = 5) -> List[Dict[str, Any]]:
        """查询相关经验教训"""
        results = self.lessons

        if problem_type:
            results = [
                l for l in results
                if problem_type.lower() in l.get("problem_type", "").lower()
                or problem_type.lower() in l.get("content", "").lower()
            ]

        if category:
            results = [l for l in results if l.get("category") == category]

        # 按使用次数降序（越常用的经验越有价值）
        results.sort(key=lambda l: l.get("use_count", 0), reverse=True)
        return results[:top_k]

    def increment_use(self, lesson_id: str) -> None:
        for l in self.lessons:
            if l["id"] == lesson_id:
                l["use_count"] = l.get("use_count", 0) + 1
                break

    def retrieve_relevant(
        self,
        problem_text: str = "",
        problem_type: str = "",
        category: str = "",
        top_k: int = 3,
        increment: bool = True,
    ) -> List[Dict[str, Any]]:
        """Phase 4：检索 + 自动 use_count +1 闭环。

        与 :meth:`query` 的区别：
        - 自动 ``increment_use``（使用越多的经验越有价值，排序时权重更高）
        - 接受 ``problem_text``（除 problem_type 外，用文本关键词兜底匹配）
        - 返回前自动 ``save()`` 持久化 use_count 变化

        默认 :class:`MemoryManager` 走 :meth:`query`（不触发递增）。
        orchestrator 调本方法让学习闭环真正转起来。
        """
        results = self.lessons

        if category:
            results = [l for l in results if l.get("category") == category]

        # 双重匹配：先按 problem_type，再按 problem_text 关键词
        if problem_type:
            typed = [
                l for l in results
                if problem_type.lower() in l.get("problem_type", "").lower()
            ]
            if typed:
                results = typed
        if problem_text and results == self.lessons:
            # 退化为文本关键词匹配
            text_lower = problem_text.lower()
            results = [
                l for l in results
                if any(kw in l.get("content", "").lower() or kw in l.get("problem_type", "").lower()
                       for kw in self._extract_keywords(text_lower))
            ]

        results.sort(key=lambda l: l.get("use_count", 0), reverse=True)
        top = results[:top_k]

        if increment and top:
            for l in top:
                l["use_count"] = l.get("use_count", 0) + 1
            self.save()  # 持久化
            logger.debug(
                f"retrieve_relevant: incremented use_count for {len(top)} lessons"
            )
        return top

    @staticmethod
    def _extract_keywords(text: str, top_n: int = 8) -> List[str]:
        """极简关键词提取：按空白/标点切分 + 长度过滤 + 滑动窗口。

        中文场景下没有空格分隔，额外使用 2-4 字符滑动窗口覆盖短语。
        """
        import re
        # 1) 显式分词
        tokens = re.split(r"[\s,。;；、!?？()()【】\[\]【】<>/\\|]+", text)
        seen: set = set()
        keywords: List[str] = []
        # 优先长 token
        for t in sorted(tokens, key=len, reverse=True):
            t = t.strip().lower()
            if len(t) >= 3 and t not in seen:
                seen.add(t)
                keywords.append(t)
            if len(keywords) >= top_n:
                break
        # 2) 中文滑动窗口（覆盖无空格文本）
        text_lower = text.lower()
        for n in (4, 3, 2):
            for i in range(0, len(text_lower) - n + 1):
                w = text_lower[i : i + n]
                if not re.search(r"[一-鿿]", w):
                    continue  # 跳过纯英文/数字
                if w not in seen:
                    seen.add(w)
                    keywords.append(w)
                if len(keywords) >= top_n * 2:
                    return keywords
        return keywords

    def query_by_tags(
        self,
        tags: Optional[List[str]] = None,
        category: str = "",
        subcategory: str = "",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """按标签、分类、子分类检索经验教训。"""
        results = self.lessons
        if category:
            results = [l for l in results if l.get("category") == category]
        if subcategory:
            results = [l for l in results if l.get("subcategory") == subcategory]
        if tags:
            tag_set = set(t.lower() for t in tags)
            results = [
                l for l in results
                if tag_set & set(t.lower() for t in l.get("tags", []))
            ]
        # 按 impact_score * (1 + use_count) 排序
        results.sort(
            key=lambda l: l.get("impact_score", 5) * (1 + l.get("use_count", 0)),
            reverse=True,
        )
        return results[:top_k]

    def get_context_text(self, problem_type: str = "", top_k: int = 5) -> str:
        """获取格式化的经验上下文（注入 Agent prompt）"""
        lessons = self.query(problem_type=problem_type, top_k=top_k)
        if not lessons:
            return ""

        parts = []
        for l in lessons:
            status = "有效" if l.get("success") else "无效"
            tags = l.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            impact = l.get("impact_score", 5)
            parts.append(f"- [{l['category']}] {l['content']} (来源: {l.get('source_task', '未知')}, {status}, 影响力:{impact}{tag_str})")

        return "\n## 历史经验参考\n" + "\n".join(parts) + "\n"

    def _load(self) -> None:
        filepath = _memory_dir() / "lessons.json"
        if filepath.exists():
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                self.lessons = data.get("lessons", [])
                logger.info(f"LessonsMemory loaded {len(self.lessons)} lessons")
            except Exception as e:
                logger.warning(f"Failed to load lessons: {e}")
                self.lessons = []

    def save(self) -> None:
        filepath = _memory_dir() / "lessons.json"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(
            json.dumps({"lessons": self.lessons, "count": len(self.lessons)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"lessons": self.lessons, "count": len(self.lessons)}


# ============================================================
# MemoryManager（记忆管理器）
# ============================================================

class MemoryManager:
    """统一管理三层记忆的入口。

    每个任务创建独立的 WorkingMemory + EpisodicMemory，
    LessonsMemory 全局共享。
    """

    def __init__(self):
        self._working: Dict[str, WorkingMemory] = {}    # task_id -> WorkingMemory
        self._episodic: Dict[str, EpisodicMemory] = {}  # task_id -> EpisodicMemory
        self._lessons = LessonsMemory()

    def create_task_memory(self, task_id: str) -> tuple:
        """为任务创建记忆容器"""
        wm = WorkingMemory(task_id=task_id)
        em = EpisodicMemory(task_id=task_id)
        self._working[task_id] = wm
        self._episodic[task_id] = em
        logger.info(f"MemoryManager created memory for task {task_id}")
        return wm, em

    def get_working(self, task_id: str) -> Optional[WorkingMemory]:
        return self._working.get(task_id)

    def get_episodic(self, task_id: str) -> Optional[EpisodicMemory]:
        return self._episodic.get(task_id)

    def get_lessons(self) -> LessonsMemory:
        return self._lessons

    def record_event(self, task_id: str, agent: str, event_type: str, content: str, metadata: Optional[Dict] = None) -> None:
        """快捷记录情景记忆"""
        em = self._episodic.get(task_id)
        if em:
            em.record(agent, event_type, content, metadata)

    def save_task_memory(self, task_id: str) -> None:
        """保存任务记忆到磁盘"""
        wm = self._working.get(task_id)
        em = self._episodic.get(task_id)
        if not wm or not em:
            return

        filepath = _memory_dir() / f"task_{task_id}.json"
        data = {
            "task_id": task_id,
            "working": wm.to_dict(),
            "episodic": em.to_dict(),
            "saved_at": datetime.now().isoformat(),
        }
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_task_memory(self, task_id: str) -> bool:
        """从磁盘加载任务记忆"""
        filepath = _memory_dir() / f"task_{task_id}.json"
        if not filepath.exists():
            return False

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            wm_data = data.get("working", {})
            em_data = data.get("episodic", {})
            self._working[task_id] = WorkingMemory.from_dict(wm_data)
            self._episodic[task_id] = EpisodicMemory.from_dict(em_data)
            logger.info(f"MemoryManager loaded memory for task {task_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load task memory {task_id}: {e}")
            return False

    def save_lessons(self) -> None:
        self._lessons.save()

    def extract_lessons_from_result(self, task_id: str, result: Dict[str, Any]) -> None:
        """从任务结果中自动提取经验教训（简单规则版）。

        生产环境中应调用 LLM 做智能提取。
        这里基于结果结构做简单提取。
        """
        # 从 analyzer 结果提取问题类型和方法
        analyzer = result.get("analyzer_agent", {})
        if analyzer:
            problem_type = analyzer.get("problem_type", "")
            approach = analyzer.get("overall_approach", "")
            if problem_type and approach:
                self._lessons.add_lesson(
                    category="method_selection",
                    content=f"对于{problem_type}问题，采用方案：{approach}",
                    problem_type=problem_type,
                    method=approach,
                    success=True,
                    source_task=task_id,
                )

        # 从 modeler 结果提取模型选择
        modeler = result.get("modeler_agent", {})
        if modeler:
            models = modeler.get("sub_problem_models", [])
            for m in models:
                model_name = m.get("model_name", "")
                model_type = m.get("model_type", "")
                if model_name:
                    self._lessons.add_lesson(
                        category="modeling",
                        content=f"模型选择：{model_name}（{model_type}）",
                        method=model_type,
                        success=True,
                        source_task=task_id,
                    )

        # 从 solver 结果提取求解经验
        solver = result.get("solver_agent", {})
        if solver:
            solutions = solver.get("sub_problem_solutions", [])
            for s in solutions:
                findings = s.get("results", {}).get("key_findings", [])
                if findings:
                    finding_text = "; ".join(str(f) for f in findings[:2])
                    self._lessons.add_lesson(
                        category="solving",
                        content=f"求解发现：{finding_text}",
                        success=True,
                        source_task=task_id,
                    )

        self._lessons.save()
        logger.info(f"MemoryManager extracted lessons from task {task_id}")

    def extract_literature_lessons(self, task_id: str, result: Dict[str, Any]) -> None:
        """从研究结果中提取文献、方法、算法经验，持久化到记忆系统。

        提取内容：
        1. research_agent 发现的论文和方法
        2. solver_agent 使用的算法和代码模板
        3. writer_agent 的写作模式
        """
        # 从 research_agent 提取文献和方法
        research = result.get("research_agent", {})
        if research:
            papers = research.get("papers", [])
            methods = research.get("methods", [])
            for paper in papers[:10]:  # 最多提取 10 篇
                title = paper.get("title", "")
                authors = paper.get("authors", "")
                year = paper.get("year", "")
                contribution = paper.get("contribution", "") or paper.get("abstract", "")[:200]
                if title:
                    self._lessons.add_lesson(
                        category="literature",
                        content=f"论文: {title} ({authors}, {year}). 贡献: {contribution[:150]}",
                        problem_type="literature",
                        method=title,
                        success=True,
                        source_task=task_id,
                    )
            for method in methods[:5]:  # 最多提取 5 个方法
                method_name = method.get("name", "") or method.get("method_name", "")
                description = method.get("description", "") or method.get("approach", "")
                if method_name:
                    self._lessons.add_lesson(
                        category="method_discovery",
                        content=f"发现方法: {method_name}. {description[:200]}",
                        problem_type="method",
                        method=method_name,
                        success=True,
                        source_task=task_id,
                    )

        # 从 solver_agent 提取算法和代码经验
        solver = result.get("solver_agent", {})
        if solver:
            # 提取使用的算法
            algorithms = solver.get("algorithms_used", [])
            for algo in algorithms[:5]:
                if isinstance(algo, str) and algo:
                    self._lessons.add_lesson(
                        category="algorithm",
                        content=f"算法实践: {algo}",
                        problem_type="algorithm",
                        method=algo,
                        success=True,
                        source_task=task_id,
                    )
            # 提取代码模板
            code_manifest = solver.get("code_manifest", {})
            if code_manifest:
                files = code_manifest.get("files", [])
                for f in files[:3]:
                    fname = f.get("name", "") if isinstance(f, dict) else str(f)
                    if fname:
                        self._lessons.add_lesson(
                            category="code_pattern",
                            content=f"代码文件: {fname}",
                            problem_type="code",
                            method=fname,
                            success=True,
                            source_task=task_id,
                        )

        # 从 writer_agent 提取写作模式
        writer = result.get("writer_agent", {})
        if writer:
            template = writer.get("template", "")
            citations = writer.get("citations", [])
            if template:
                self._lessons.add_lesson(
                    category="writing_pattern",
                    content=f"论文模板: {template}, 引用数量: {len(citations)}",
                    problem_type="writing",
                    method=template,
                    success=True,
                    source_task=task_id,
                )

        self._lessons.save()
        logger.info(f"MemoryManager extracted literature/method lessons from task {task_id}")


# ============================================================
# 全局实例
# ============================================================

_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


def reset_memory_manager() -> None:
    global _memory_manager
    _memory_manager = None
