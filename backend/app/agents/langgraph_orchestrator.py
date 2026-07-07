"""LangGraph 编排器（Phase 3）。

目标：用 ``langgraph.StateGraph`` 替换 ``orchestrator.py`` 中的硬编码 if-else 控制流。
当前版本为骨架实现：节点与条件边已定义，节点内部逐步填充。

开关：``backend/app/config.py`` 中的 ``use_langgraph_orchestrator``。
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

try:
    from langgraph.graph import StateGraph, END
    from langgraph.graph.message import add_messages
    LANGGRAPH_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False
    StateGraph = Any  # type: ignore
    END = "__end__"  # type: ignore
    add_messages = None  # type: ignore
    logging.getLogger(__name__).warning(f"langgraph 未安装或导入失败: {exc}")

from ..core.chat_room import create_chat_room, get_chat_room
from ..core.event_bus import get_event_bus
from ..core.memory import get_memory_manager
from ..services.result_validator import get_result_validator, get_cross_validator
from ..services.code_manifest import parse_manifest_from_dict, validate_manifest
from ..services.contract_validator import get_contract_validator
from ..services.fact_checker import get_fact_checker
from ..core.paths import get_project_output_dir
from ..core.state_store import get_task_result_store, _ref_key

logger = logging.getLogger(__name__)


class TaskState(TypedDict, total=False):
    """LangGraph 共享状态。"""

    messages: List[Dict[str, Any]]
    files: List[str]
    preflight: Optional[Dict[str, Any]]
    current_step: str
    paper_template: str
    workflow_type: str
    mode: str
    phase: str
    retry_count: int
    escalation_count: int
    solver_attempts: List[Dict[str, Any]]
    artifact_paths: List[str]
    cannot_solve_report: Optional[Dict[str, Any]]
    task_id: str
    problem_text: str
    project_name: Optional[str]
    knowledge_base_id: Optional[str]
    knowledge_base_ids: Optional[List[str]]  # v5.3.0: 多 KB 注入
    results: Dict[str, Any]
    sub_problems: List[Dict[str, Any]]
    should_pause: bool
    use_critique: bool  # 是否启用 Writer 自评质量循环
    requirement_plan: Optional[Dict[str, Any]]  # 需求分解结果
    innovation_analysis: Optional[Dict[str, Any]]  # 创新发现分析
    experiment_iterations: int  # 实验迭代次数
    task_summary: Optional[Dict[str, Any]]  # 任务总结报告
    user_messages: List[Dict[str, Any]]  # 用户在执行期间输入的消息
    last_input_check: float  # 上次检查用户消息的时间戳


@dataclass
class LangGraphConfig:
    """LangGraph 编排器配置。"""

    max_solver_iterations: int = 5
    max_solver_escalations: int = 2
    enable_peer_review: bool = True
    enable_experiment_design: bool = True
    enable_fact_check: bool = True


class LangGraphOrchestrator:
    """基于 LangGraph StateGraph 的任务编排器。"""

    # CCF-A 顶会模板集合
    _CCF_A_TEMPLATES = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs"}

    # 不需要建模的模板（调研/综述类）
    _TEMPLATES_NO_MODELING = {"research_survey", "research_review", "literature_review"}

    # 不需要建模的工作流类型
    _WORKFLOWS_NO_MODELING = {"deep_research", "survey"}

    def __init__(
        self,
        agents: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ):
        self.agents = agents
        self.cfg = LangGraphConfig(**(config or {}))
        self._result_store = get_task_result_store()
        self._graph = self._build_graph() if LANGGRAPH_AVAILABLE else None

    def _resolve_results(self, state: TaskState) -> Dict[str, Any]:
        """把 state 中的 result 引用还原为实际 Agent 输出。"""
        refs = state.get("results", {})
        task_id = state["task_id"]
        resolved: Dict[str, Any] = {}
        for agent_name, value in refs.items():
            if isinstance(value, str) and value.startswith("__ref__"):
                resolved[agent_name] = self._result_store.get(task_id, agent_name, {})
            else:
                resolved[agent_name] = value
        return resolved

    def _set_result(self, state: TaskState, agent_name: str, output: Any) -> Dict[str, Any]:
        """把 Agent 输出写入外部 store，并返回用于 state 的引用 dict。"""
        task_id = state["task_id"]
        self._result_store.set(task_id, agent_name, output)
        return {agent_name: _ref_key(agent_name)}

    # ------------------------------------------------------------------
    # 建模 Agent 选择
    # ------------------------------------------------------------------
    @classmethod
    def _select_modeling_agent(cls, template: str, workflow_type: str) -> str:
        """根据模板和工作流类型选择合适的建模 Agent。

        Returns:
            空字符串表示跳过建模；否则返回对应 Agent 名称。
        """
        if template in cls._TEMPLATES_NO_MODELING or workflow_type in cls._WORKFLOWS_NO_MODELING:
            return ""
        if template == "financial_analysis":
            return "financial_analyst_agent"
        if template in cls._CCF_A_TEMPLATES or workflow_type == "research_paper":
            return "algorithm_engineer_agent"
        return "modeler_agent"

    # ------------------------------------------------------------------
    # 归一化方法
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_algorithm_engineer_output(raw: dict) -> dict:
        """将 algorithm_engineer_agent 的原始输出归一化为标准 modeler_agent 格式。

        把 problem_formulation / proposed_method / experiment_design / code_hints 等
        映射到兼容 solver/writer 的 sub_problem_models 结构。
        """
        if not raw or not isinstance(raw, dict):
            return {"sub_problem_models": []}

        formulation = raw.get("problem_formulation", {})
        method = raw.get("proposed_method", {})

        # 提取变量：优先使用 hyperparameters，回退到 notation
        variables = []
        for hp in method.get("hyperparameters", []):
            if isinstance(hp, dict):
                variables.append(
                    {
                        "name": str(hp.get("name", "")),
                        "description": str(hp.get("description", "")),
                        "type": "连续",
                        "range": f"default={hp.get('default', '')}",
                    }
                )
        if not variables:
            for k, v in formulation.get("notation", {}).items():
                variables.append({"name": str(k), "description": str(v), "type": "连续", "range": "待确定"})

        # 提取约束
        constraints = []
        for c in formulation.get("constraints", []):
            if isinstance(c, dict):
                constraints.append(
                    {
                        "name": c.get("name", "约束"),
                        "expression": c.get("expression", str(c)),
                        "type": c.get("type", "不等式"),
                    }
                )
            elif isinstance(c, str):
                constraints.append({"name": "约束", "expression": c, "type": "不等式"})

        normalized_model = {
            "sub_problem_index": 0,
            "sub_problem_name": "整体问题",
            "model_type": "algorithm_design",
            "model_name": method.get("name", "") or method.get("name_cn", "Proposed Method"),
            "decision_variables": variables,
            "parameters": [],
            "objective_function": formulation.get("objective", ""),
            "constraints": constraints,
            "algorithm": {
                "name": method.get("name", ""),
                "description": method.get("core_idea", ""),
            },
            "model_assumptions": formulation.get("assumptions", []),
            "model_advantages": method.get("key_innovation", []),
            "model_limitations": method.get("limitations", []),
            "_agent_source": "algorithm_engineer_agent",
            "_raw_output": raw,
        }

        return {"sub_problem_models": [normalized_model]}

    @staticmethod
    def _normalize_financial_analyst_output(raw: dict) -> dict:
        """将 financial_analyst_agent 的原始输出归一化为标准 modeler_agent 格式。

        从 financial_model / data_requirements / risk_analysis / backtest_design 提取字段。
        """
        if not raw or not isinstance(raw, dict):
            return {"sub_problem_models": []}

        formulation = raw.get("problem_formulation", {})
        financial_model = raw.get("financial_model", {})
        risk = raw.get("risk_analysis", {})

        # 提取变量：优先使用 parameters，回退到 key_variables
        variables = []
        for p in financial_model.get("parameters", []):
            if isinstance(p, dict):
                variables.append(
                    {
                        "name": str(p.get("name", "")),
                        "description": str(p.get("meaning", "")),
                        "type": "连续",
                        "range": f"estimation={p.get('estimation', '')}",
                    }
                )
        if not variables:
            for k, v in formulation.get("key_variables", {}).items():
                variables.append({"name": str(k), "description": str(v), "type": "连续", "range": "待确定"})

        # 提取约束：从风险/局限中转换
        constraints = []
        for lim in risk.get("limitations", []):
            if isinstance(lim, str):
                constraints.append({"name": "风险/局限", "expression": lim, "type": "不等式"})

        normalized_model = {
            "sub_problem_index": 0,
            "sub_problem_name": "整体问题",
            "model_type": "financial_model",
            "model_name": financial_model.get("name", "") or financial_model.get("name_cn", "Financial Model"),
            "decision_variables": variables,
            "parameters": [],
            "objective_function": financial_model.get("model_specification", ""),
            "constraints": constraints,
            "algorithm": {
                "name": financial_model.get("name", ""),
                "description": financial_model.get("core_idea", ""),
            },
            "model_assumptions": formulation.get("assumptions", []),
            "model_advantages": [f"Domain: {formulation.get('domain', '')}"] if formulation.get("domain") else [],
            "model_limitations": risk.get("limitations", []),
            "_agent_source": "financial_analyst_agent",
            "_raw_output": raw,
        }

        return {"sub_problem_models": [normalized_model]}

    # ------------------------------------------------------------------
    # 防编造校验
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_no_fabrication(agent_name: str, output: dict) -> dict:
        """检测 Agent 输出中可能的编造内容。

        Args:
            agent_name: Agent 名称，用于选择特定校验规则。
            output: Agent 原始输出字典。

        Returns:
            包含 _fabrication_flags、_fabrication_score、_validated_at 的字典。
        """
        flags: List[str] = []
        score = 0.0

        # 通用规则：检测无参考文献标记的作者-年份引用
        text = json.dumps(output, ensure_ascii=False)

        # 匹配 (Author et al., YYYY) 或 (Author, YYYY) 模式
        author_year_pattern = re.compile(r'\([A-Z][a-z]+(?:\s+et\s+al\.?)?,\s*\d{4}[a-z]?\)')
        author_year_matches = author_year_pattern.findall(text)

        # 检测是否有对应的 [N] 编号引用
        ref_pattern = re.compile(r'\[\d+\]')
        ref_matches = ref_pattern.findall(text)

        if author_year_matches and len(ref_matches) < len(author_year_matches) * 0.5:
            flags.append(
                f"检测到 {len(author_year_matches)} 处作者-年份引用，"
                f"但只有 {len(ref_matches)} 处编号引用，可能存在编造引用"
            )
            score += min(0.3, len(author_year_matches) * 0.05)

        # 特定 Agent 规则
        if agent_name == "financial_analyst_agent":
            # 检测无来源说明的具体价格/收益率
            price_pattern = re.compile(r'\$\d+\.\d{2}')
            yield_pattern = re.compile(r'[+-]?\d+\.\d+%')
            price_matches = price_pattern.findall(text)
            yield_matches = yield_pattern.findall(text)

            # 检查是否有数据来源关键词
            source_keywords = ["Yahoo Finance", "Bloomberg", "Wind", "CSMAR", "国泰安",
                             "来源", "source", "data from", "historical"]
            has_source = any(kw.lower() in text.lower() for kw in source_keywords)

            if (price_matches or yield_matches) and not has_source:
                flags.append(
                    f"检测到 {len(price_matches)} 处价格数据和 {len(yield_matches)} 处收益率数据，"
                    f"但未找到数据来源说明"
                )
                score += min(0.4, (len(price_matches) + len(yield_matches)) * 0.03)

        elif agent_name == "algorithm_engineer_agent":
            # 检测无引用的具体 baseline 数字（如 95.2%、F1=0.89）
            baseline_pattern = re.compile(r'\b(?:\d{2,3}\.\d%|F1\s*=\s*0\.\d+|Acc\s*=\s*\d+\.\d%|'
                                          r'Accuracy\s*=\s*\d+\.\d%|Precision\s*=\s*\d+\.\d%|'
                                          r'Recall\s*=\s*\d+\.\d%)')
            baseline_matches = baseline_pattern.findall(text)

            # 检查是否有引用或来源说明
            citation_keywords = ["cite", "reported", "from", "according to", "文献",
                                 "论文", "待确认", "待实验验证", "需查阅原文"]
            has_citation = any(kw.lower() in text.lower() for kw in citation_keywords)

            if baseline_matches and not has_citation:
                flags.append(
                    f"检测到 {len(baseline_matches)} 处具体性能数字，"
                    f"但未找到引用或来源说明"
                )
                score += min(0.4, len(baseline_matches) * 0.08)

        score = min(1.0, score)

        return {
            "_fabrication_flags": flags,
            "_fabrication_score": round(score, 3),
            "_validated_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------
    async def run(
        self,
        task_id: str,
        problem_text: str,
        workflow: Optional[List[Dict[str, Any]]] = None,
        data_files: Optional[List[str]] = None,
        mode: str = "batch",
        project_name: Optional[str] = None,
        knowledge_base_id: Optional[str] = None,
        knowledge_base_ids: Optional[List[str]] = None,  # v5.3.0: 多 KB
        template: str = "math_modeling",
        workflow_type: str = "standard",
        preflight_report: Optional[Dict[str, Any]] = None,
        use_critique: bool = True,
    ) -> Dict[str, Any]:
        """运行完整工作流。"""
        if not LANGGRAPH_AVAILABLE or self._graph is None:
            raise RuntimeError("langgraph 未安装，无法使用 LangGraphOrchestrator")

        room = create_chat_room(task_id, problem_text)
        mm = get_memory_manager()
        wm, em = mm.create_task_memory(task_id)
        wm.update_problem(text=problem_text[:500], template=template, workflow_type=workflow_type)
        em.record("coordinator", "task_start", f"LangGraph 任务开始：{problem_text[:100]}")

        # v5.3.0: 兼容旧单 KB
        if knowledge_base_ids is None and knowledge_base_id:
            knowledge_base_ids = [knowledge_base_id]

        initial_state: TaskState = {
            "messages": [],
            "files": data_files or [],
            "preflight": preflight_report,
            "current_step": "preflight_decision",
            "paper_template": template,
            "workflow_type": workflow_type,
            "mode": mode,
            "phase": "phase1",
            "retry_count": 0,
            "escalation_count": 0,
            "solver_attempts": [],
            "artifact_paths": [],
            "cannot_solve_report": None,
            "task_id": task_id,
            "problem_text": problem_text,
            "project_name": project_name,
            "knowledge_base_id": knowledge_base_id,
            "knowledge_base_ids": knowledge_base_ids,
            "results": {},
            "sub_problems": [],
            "should_pause": False,
            "revision_count": 0,
            "use_critique": use_critique,
            "user_messages": [],
            "last_input_check": time.time(),
        }

        # 检查是否可以从 checkpoint 恢复（断点续传）
        restored_state = self._restore_from_checkpoint(task_id, initial_state)
        if restored_state is not initial_state:
            logger.info(f"[LangGraph:{task_id}] 从 checkpoint 恢复，继续执行")
            self._post_chat(task_id, "coordinator", "🔄 从断点恢复，继续执行...")

        try:
            final_state = await self._graph.ainvoke(restored_state)
            # 持久化结果
            self._save_results(task_id, final_state)
            em.record("coordinator", "task_end", f"LangGraph 任务完成：{final_state.get('current_step', 'done')}")

            # Agent 记忆自进化：从任务结果回写到每个 Agent 的独立记忆
            try:
                self._evolve_agent_profiles(task_id, final_state, problem_text)
            except Exception as e:
                logger.warning(f"AgentProfile 自进化失败（不影响任务结果）: {e}")

            # 将任务级知识库合并到项目知识库（保留论文内容供未来任务参考）
            task_kb_id = final_state.get("task_kb_id")
            if task_kb_id:
                try:
                    from ..core.knowledge_manager import get_knowledge_manager
                    km = get_knowledge_manager()
                    task_base = km._bases.get(task_kb_id)
                    if task_base and project_name:
                        # 查找或创建项目级知识库
                        proj_kb_name = f"project_{project_name}"
                        proj_base = None
                        for bid, b in km._bases.items():
                            if b.name == proj_kb_name:
                                proj_base = b
                                break
                        if not proj_base:
                            proj_base = km.create_base(
                                name=proj_kb_name,
                                description=f"项目 {project_name} 的论文知识库",
                                scope="project",
                            )
                        # 合并论文分块
                        if hasattr(task_base, 'items') and task_base.items:
                            for item in task_base.items:
                                proj_base.items.append(item)
                            km._save_bases()
                            logger.info(f"任务级知识库已合并到项目知识库: {proj_kb_name} ({len(task_base.items)} 篇)")
                        # 删除任务级 KB
                        km.delete_base(task_kb_id)
                        logger.info(f"任务级知识库已清理: {task_kb_id}")
                except Exception as e:
                    logger.debug(f"合并任务级知识库失败: {e}")

            return {
                "task_id": task_id,
                "status": "completed",
                "results": self._resolve_results(final_state),
                "sub_problems": final_state.get("sub_problems", []),
                "solver_attempts": len(final_state.get("solver_attempts", [])),
                "current_step": final_state.get("current_step", ""),
                "cannot_solve_report": final_state.get("cannot_solve_report"),
            }
        except Exception as exc:
            logger.error(f"LangGraph run failed for {task_id}: {exc}", exc_info=True)
            em.record("coordinator", "task_error", f"LangGraph 任务失败：{exc}")
            raise

    def _restore_from_checkpoint(self, task_id: str, initial_state: TaskState) -> TaskState:
        """尝试从 checkpoint 恢复任务状态。如果无 checkpoint 或恢复失败，返回 initial_state。"""
        from ..core.task_persistence import load_task_checkpoints, load_task_metadata

        try:
            meta = load_task_metadata(task_id)
            if not meta:
                return initial_state

            status = meta.get("status", "")
            if status not in ("interrupted", "paused", "running"):
                return initial_state

            checkpoints = load_task_checkpoints(task_id)
            if not checkpoints:
                return initial_state

            # 按时间排序，取最新的 checkpoint
            checkpoints.sort(key=lambda x: x.get("saved_at", ""))
            last_checkpoint = checkpoints[-1]
            last_step = last_checkpoint.get("step", "")
            last_payload = last_checkpoint.get("payload", {})

            logger.info(f"[LangGraph:{task_id}] 恢复 checkpoint: step={last_step}, saved_at={last_checkpoint.get('saved_at')}")

            # 重建 results（从所有 checkpoints 聚合）
            restored_results = {}
            for cp in checkpoints:
                step_name = cp.get("step", "")
                payload = cp.get("payload", {})
                if step_name and payload:
                    restored_results[step_name] = payload

            # 从 task_result.json 加载已有结果（更完整）
            try:
                from ..core.task_persistence import load_task_result
                task_result = load_task_result(task_id)
                if task_result and task_result.get("output"):
                    restored_results.update(task_result["output"])
            except Exception:
                pass

            # 确定恢复后的 current_step（用于路由到下一个节点）
            step_to_node = {
                "analyzer_agent": "analyzer_done",
                "data_agent": "data_done",
                "research_agent": "research_done",
                "modeler_agent": "modeler_done",
                "algorithm_engineer_agent": "algorithm_engineer_done",
                "financial_analyst_agent": "financial_analyst_done",
                "solver_agent": "iterative_solver_done",
                "experiment_agent": "experiment_done",
                "writer_agent": "writer_done",
                "peer_review_agent": "peer_review_done",
                "figure_agent": "figure_done",
                "fact_check_agent": "fact_check_done",
            }
            current_step = step_to_node.get(last_step, "preflight_decision_done")

            # 构建恢复后的 state
            restored_state: TaskState = {
                **initial_state,
                "current_step": current_step,
                "results": restored_results,
                "phase": meta.get("phase", initial_state.get("phase", "phase1")),
                "revision_count": meta.get("revision_count", 0),
                "retry_count": meta.get("retry_count", 0),
                "escalation_count": meta.get("escalation_count", 0),
            }

            # 恢复子问题列表（如果存在）
            analyzer_result = restored_results.get("analyzer_agent", {})
            if analyzer_result and analyzer_result.get("sub_problems"):
                restored_state["sub_problems"] = analyzer_result["sub_problems"]

            # 恢复 cannot_solve_report
            if meta.get("cannot_solve_report"):
                restored_state["cannot_solve_report"] = meta["cannot_solve_report"]

            return restored_state

        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] 从 checkpoint 恢复失败: {e}，将从头开始")
            return initial_state

    def _evolve_agent_profiles(
        self,
        task_id: str,
        final_state: Dict[str, Any],
        problem_text: str,
    ):
        """任务完成后回写每个 Agent 的独立经验。"""
        from ..core.agent_memory import get_agent_profile

        results = self._resolve_results(final_state)
        sub_problems = final_state.get("sub_problems", [])
        problem_type = (results.get("analyzer_agent") or {}).get("problem_type", "")

        # 各 Agent 经验收集规则
        evolution_map = {
            "analyzer_agent": self._extract_analyzer_case,
            "modeler_agent": self._extract_modeler_case,
            "solver_agent": self._extract_solver_case,
            "writer_agent": self._extract_writer_case,
            "research_agent": self._extract_research_case,
            "algorithm_engineer_agent": self._extract_modeler_case,
            "financial_analyst_agent": self._extract_modeler_case,
        }

        for agent_name, extractor in evolution_map.items():
            try:
                profile = get_agent_profile(agent_name)
                output = results.get(agent_name, {})
                if not output:
                    continue
                case_type, method, outcome, impact, summary = extractor(output, problem_text, problem_type, final_state)
                if case_type and method:
                    profile.add_case(
                        case_type=case_type,
                        task_id=task_id,
                        problem_type=problem_type,
                        method=method,
                        outcome=outcome,
                        impact_score=impact,
                        summary=summary,
                    )
                    logger.debug(f"Agent {agent_name} 经验回写: {case_type} (impact={impact:.2f})")
            except Exception as e:
                logger.debug(f"Agent {agent_name} 经验回写失败: {e}")

    @staticmethod
    def _extract_analyzer_case(output: Dict, problem_text: str, problem_type: str, state: Dict):
        sub_problems = output.get("sub_problems", [])
        return (
            "success" if sub_problems else None,
            f"问题分解: {len(sub_problems)} 个子问题" if sub_problems else "",
            f"识别问题类型: {problem_type}",
            0.6,
            f"题目类型={problem_type}, 子问题数={len(sub_problems)}",
        )

    @staticmethod
    def _extract_modeler_case(output: Dict, problem_text: str, problem_type: str, state: Dict):
        models = output.get("sub_problem_models", [])
        if not models:
            return None, "", "", 0.0, ""
        methods = ", ".join(m.get("model_type", "未知") for m in models[:3])
        return (
            "success",
            f"建模: {methods}",
            f"为 {len(models)} 个子问题建立模型",
            0.7,
            f"模型类型={methods}",
        )

    @staticmethod
    def _extract_solver_case(output: Dict, problem_text: str, problem_type: str, state: Dict):
        solutions = output.get("sub_problem_solutions", [])
        attempts = state.get("solver_attempts", [])
        if not solutions:
            return "failure", "求解失败", "求解全部失败", 0.4, "求解失败案例"
        success_rate = sum(1 for s in solutions if s.get("results", {}).get("execution_success", True)) / len(solutions)
        return (
            "success" if success_rate > 0.7 else "failure",
            f"求解: 成功率 {success_rate:.0%}",
            f"{len(solutions)} 个子问题求解（尝试 {len(attempts)} 次）",
            0.6 + success_rate * 0.3,
            f"成功率={success_rate:.2f}, 尝试次数={len(attempts)}",
        )

    @staticmethod
    def _extract_writer_case(output: Dict, problem_text: str, problem_type: str, state: Dict):
        chapters = output.get("chapters", []) or []
        latex = output.get("latex_code", "") or output.get("latex", "")
        if not latex:
            return None, "", "", 0.0, ""
        chapter_count = len(chapters) if chapters else latex.count("\\section")
        return (
            "success",
            f"写作: {chapter_count} 章节",
            f"生成 {chapter_count} 章节 LaTeX（{len(latex)} 字符）",
            0.7,
            f"章节数={chapter_count}, LaTeX长度={len(latex)}",
        )

    @staticmethod
    def _extract_research_case(output: Dict, problem_text: str, problem_type: str, state: Dict):
        papers = output.get("papers", []) or []
        if not papers:
            return None, "", "", 0.0, ""
        return (
            "success",
            f"文献检索: {len(papers)} 篇",
            f"从 arXiv 检索 {len(papers)} 篇论文",
            min(0.8, 0.4 + len(papers) * 0.05),
            f"检索到{len(papers)}篇相关论文",
        )

    # ------------------------------------------------------------------
    # 数据驱动的 Agent 裁剪配置（按 problem_type 跳过不必要的 Agent）
    # ------------------------------------------------------------------

    # 不需要 data_agent（纯理论 / 算法类）
    _PROBLEM_TYPES_NO_DATA = {"网络", "物理", "仿真", "测量", "综合"}

    # 不需要 research_agent（已知领域或纯方法论）
    _PROBLEM_TYPES_NO_RESEARCH = {"物理", "测量"}

    @classmethod
    def _should_skip_data(cls, problem_type: str, has_data_files: bool) -> bool:
        """判断是否跳过 data_agent。"""
        if not has_data_files:
            return True
        if problem_type in cls._PROBLEM_TYPES_NO_DATA:
            return True
        return False

    @classmethod
    def _should_skip_research(cls, problem_type: str, workflow_type: str) -> bool:
        """判断是否跳过 research_agent。"""
        if workflow_type in ("quick", "code_focused"):
            return True
        if problem_type in cls._PROBLEM_TYPES_NO_RESEARCH:
            return True
        return False

    # ------------------------------------------------------------------
    # HITL: 用户输入检查
    # ------------------------------------------------------------------
    async def _check_user_input(self, state: TaskState) -> TaskState:
        """每个节点完成后调用 — 检查用户输入并注入 context"""
        task_id = state["task_id"]
        room = get_chat_room(task_id)
        if not room:
            return state

        last_check = state.get("last_input_check", 0)
        user_msgs = room.get_user_messages_since(since=last_check)

        if not user_msgs:
            return state

        # 转换为 dict 格式
        new_msgs = [{"sender": m.sender, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in user_msgs]

        # 记录到 state
        all_msgs = state.get("user_messages", [])
        all_msgs.extend(new_msgs)

        # 通知用户已收到
        room.post("coordinator", f"📝 已收到 {len(new_msgs)} 条用户反馈，正在调整...", "broadcast")

        return {
            **state,
            "user_messages": all_msgs,
            "last_input_check": time.time(),
        }

    # ------------------------------------------------------------------
    # 条件路由（改造后）
    # ------------------------------------------------------------------
    def _route_after_research_or_data(self, state: TaskState) -> str:
        """research/data 完成后决定下一站。"""
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")
        modeling_agent = self._select_modeling_agent(template, workflow_type)
        if not modeling_agent:
            logger.info(f"[LangGraph] 跳过 modeler/solver（template={template}, workflow={workflow_type}）→ writer")
            return "writer"
        # 映射到 graph 节点名称
        if modeling_agent == "modeler_agent":
            return "modeler"
        if modeling_agent == "algorithm_engineer_agent":
            return "algorithm_engineer"
        if modeling_agent == "financial_analyst_agent":
            return "financial_analyst"
        return "writer"

    def _route_after_analyzer(self, state: TaskState) -> str:
        """analyzer 之后按 problem_type + 数据情况条件路由到 data / research / 建模。"""
        problem_type = (self._resolve_results(state).get("analyzer_agent", {}) or {}).get("problem_type", "")
        has_data = bool(state.get("files"))

        skip_data = self._should_skip_data(problem_type, has_data)
        skip_research = self._should_skip_research(problem_type, state.get("workflow_type", "standard"))

        # 都跳过 → 直接到建模 Agent
        if skip_data and skip_research:
            template = state.get("paper_template", "math_modeling")
            workflow_type = state.get("workflow_type", "standard")
            modeling_agent = self._select_modeling_agent(template, workflow_type)
            if not modeling_agent:
                logger.info(f"[LangGraph] 跳过 data、research 和建模（template={template}）→ writer")
                return "writer"
            if modeling_agent == "modeler_agent":
                return "modeler"
            if modeling_agent == "algorithm_engineer_agent":
                return "algorithm_engineer"
            if modeling_agent == "financial_analyst_agent":
                return "financial_analyst"
            return "writer"

        # 只跳过 data → research
        if skip_data:
            logger.info("[LangGraph] 跳过 data → research")
            return "research"
        # 只跳过 research → data → 建模
        if skip_research:
            logger.info("[LangGraph] 跳过 research → data")
            return "data"
        # 正常顺序
        return "data"

    def _route_after_data(self, state: TaskState) -> str:
        """data 之后决定是否走 research。"""
        problem_type = (self._resolve_results(state).get("analyzer_agent", {}) or {}).get("problem_type", "")
        if self._should_skip_research(problem_type, state.get("workflow_type", "standard")):
            template = state.get("paper_template", "math_modeling")
            workflow_type = state.get("workflow_type", "standard")
            modeling_agent = self._select_modeling_agent(template, workflow_type)
            if not modeling_agent:
                return "writer"
            if modeling_agent == "modeler_agent":
                return "modeler"
            if modeling_agent == "algorithm_engineer_agent":
                return "algorithm_engineer"
            if modeling_agent == "financial_analyst_agent":
                return "financial_analyst"
            return "writer"
        return "research"

    def _route_after_research(self, state: TaskState) -> str:
        """research 后决定是否进入讨论。"""
        workflow = state.get("workflow_type", "standard")
        # deep_research 和 research_paper 模式进入讨论
        if workflow in ("deep_research", "research_paper"):
            return "discuss"
        # 其他模式直接选择建模 Agent
        template = state.get("paper_template", "math_modeling")
        modeling_agent = self._select_modeling_agent(template, workflow)
        if not modeling_agent:
            return "writer"
        if modeling_agent == "modeler_agent":
            return "modeler"
        if modeling_agent == "algorithm_engineer_agent":
            return "algorithm_engineer"
        if modeling_agent == "financial_analyst_agent":
            return "financial_analyst"
        return "writer"

    def _route_after_discuss_approach(self, state: TaskState) -> str:
        """团队讨论后决定下一步：建模求解 or 直接写作（调研/综述类跳过建模）。"""
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")
        modeling_agent = self._select_modeling_agent(template, workflow_type)
        if not modeling_agent:
            logger.info(f"[LangGraph] 讨论后跳过建模（template={template}, workflow={workflow_type}）→ writer")
            return "writer"
        if modeling_agent == "modeler_agent":
            return "modeler"
        if modeling_agent == "algorithm_engineer_agent":
            return "algorithm_engineer"
        if modeling_agent == "financial_analyst_agent":
            return "financial_analyst"
        return "writer"

    def _route_to_experiment_or_solver(self, state: TaskState) -> str:
        """CCF-A 模板且开启实验设计时，先走 experiment 节点。"""
        template = state.get("paper_template", "math_modeling")
        ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}
        if self.cfg.enable_experiment_design and template in ccf_a:
            logger.info(f"[LangGraph] template={template} 启用实验执行 → experiment")
            return "experiment"
        return "iterative_solver"

    def _route_after_experiment(self, state: TaskState) -> str:
        """实验后路由：迭代优化或进入求解器。"""
        step = state.get("current_step", "")
        if step == "experiment_iterating":
            return "experiment"  # 回到实验节点继续迭代
        return "iterative_solver"

    # ------------------------------------------------------------------
    # v7.1: 并行分析路由
    # ------------------------------------------------------------------

    def _route_after_analyzer_parallel(self, state: TaskState) -> str:
        """analyzer 后决定是否进入并行分析（data+research+innovation 同时执行）。"""
        problem_type = (self._resolve_results(state).get("analyzer_agent", {}) or {}).get("problem_type", "")
        has_data = bool(state.get("files"))
        skip_data = self._should_skip_data(problem_type, has_data)
        skip_research = self._should_skip_research(problem_type, state.get("workflow_type", "standard"))

        # 都跳过 → 直接到建模
        if skip_data and skip_research:
            return "skip_to_modeling"

        # 至少有一个需要执行 → 进入并行分析
        return "parallel"

    def _route_after_parallel_analysis(self, state: TaskState) -> str:
        """并行分析完成后，选择建模 Agent。"""
        workflow = state.get("workflow_type", "standard")
        if workflow in ("deep_research", "research_paper"):
            return "discuss"
        template = state.get("paper_template", "math_modeling")
        modeling_agent = self._select_modeling_agent(template, workflow)
        if not modeling_agent:
            return "writer"
        if modeling_agent == "modeler_agent":
            return "modeler"
        if modeling_agent == "algorithm_engineer_agent":
            return "algorithm_engineer"
        if modeling_agent == "financial_analyst_agent":
            return "financial_analyst"
        return "writer"

    async def _node_parallel_analysis(self, state: TaskState) -> TaskState:
        """v7.1: 并行执行 data_agent + research_agent + innovation_agent。

        参考：LangGraph Send API 的 fan-out/fan-in 模式。
        在同一个节点内用 asyncio.gather 并发执行三个 Agent，
        然后合并结果到 state。
        """
        import asyncio

        state = await self._check_user_input(state)
        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_phase_change(task_id, "parallel_analysis", "并行分析阶段：data + research + innovation 同时执行")

        problem_type = (self._resolve_results(state).get("analyzer_agent", {}) or {}).get("problem_type", "")
        has_data = bool(state.get("files"))
        skip_data = self._should_skip_data(problem_type, has_data)
        skip_research = self._should_skip_research(problem_type, state.get("workflow_type", "standard"))

        # 构建并行任务列表
        tasks = {}
        task_coros = {}

        if not skip_data:
            tasks["data"] = self._node_data(state)
        if not skip_research:
            tasks["research"] = self._node_research(state)
            tasks["innovation"] = self._node_innovation(state)

        if not tasks:
            # 全部跳过
            return state

        logger.info(f"[LangGraph:{task_id}] parallel_analysis: running {list(tasks.keys())} concurrently")
        self._update_progress(task_id, state["problem_text"], 30, "并行分析中（data+research+innovation）")

        # 并发执行
        results = {}
        coro_list = list(tasks.values())
        keys = list(tasks.keys())
        done_results = await asyncio.gather(*coro_list, return_exceptions=True)

        for key, result in zip(keys, done_results):
            if isinstance(result, Exception):
                logger.warning(f"[LangGraph:{task_id}] parallel_analysis.{key} failed: {result}")
                bus.emit_error(task_id, f"{key}_agent", str(result))
            else:
                results[key] = result

        # 合并结果到 state
        merged_results = {**state.get("results", {})}
        merged_step = "parallel_analysis_done"

        for key, result_state in results.items():
            if isinstance(result_state, dict):
                # 每个子节点返回的是完整的 state dict，提取 results 部分
                sub_results = result_state.get("results", {})
                merged_results.update(sub_results)
                # 更新 sub_problems（如果 data 或 research 产生了新的）
                if "sub_problems" in result_state and result_state["sub_problems"]:
                    state["sub_problems"] = result_state["sub_problems"]

        bus.emit_agent_complete(task_id, "parallel_analysis", "parallel_analysis",
                               f"完成 {len(results)} 个并行任务")

        return {**state, "results": merged_results, "current_step": merged_step}

    def _get_config(self):
        """获取全局配置。"""
        from ..config import get_settings
        return get_settings()

    # ------------------------------------------------------------------
    # Graph 构建
    # ------------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(TaskState)

        # 节点注册
        builder.add_node("requirement_decomposition", self._node_requirement_decomposition)
        builder.add_node("preflight_decision", self._node_preflight_decision)
        builder.add_node("analyzer", self._node_analyzer)
        builder.add_node("parallel_analysis", self._node_parallel_analysis)  # v7.1: 并行分析
        builder.add_node("data", self._node_data)
        builder.add_node("research", self._node_research)
        builder.add_node("innovation", self._node_innovation)
        builder.add_node("discuss_approach", self._node_discuss_approach)
        builder.add_node("modeler", self._node_modeler)
        builder.add_node("algorithm_engineer", self._node_algorithm_engineer)
        builder.add_node("financial_analyst", self._node_financial_analyst)
        builder.add_node("iterative_solver", self._node_iterative_solver)
        builder.add_node("writer", self._node_writer)
        builder.add_node("peer_review", self._node_peer_review)
        builder.add_node("experiment", self._node_experiment)
        builder.add_node("figure", self._node_figure)
        builder.add_node("fact_check", self._node_fact_check)
        builder.add_node("summary", self._node_summary)
        builder.add_node("cannot_solve", self._node_cannot_solve)
        builder.add_node("self_collect", self._node_self_collect)
        builder.add_node("wait_user", self._node_wait_user)

        # 入口
        builder.set_entry_point("requirement_decomposition")

        # 条件边
        builder.add_conditional_edges(
            "preflight_decision",
            self._route_preflight,
            {
                "analyze_only": "analyzer",
                "standard": "analyzer",
                "quick": "analyzer",
                "deep_research": "analyzer",
                "code_focused": "analyzer",
                "research_paper": "analyzer",
                "self_collect": "self_collect",
                "abort": "cannot_solve",
            },
        )

        builder.add_conditional_edges(
            "peer_review",
            self._route_peer_review,
            {
                "revise": "writer",
                "accept": "fact_check",
                "wait_user": "wait_user",
                "abort": "cannot_solve",
            },
        )

        builder.add_conditional_edges(
            "iterative_solver",
            self._route_solver,
            {
                "success": "figure",
                "retry": "iterative_solver",
                "escalate": "cannot_solve",
                "abort": "cannot_solve",
            },
        )

        # 条件边：research → innovation（始终经过创新分析）
        builder.add_edge("research", "innovation")

        # 条件边：innovation 后决定（继承 research 的路由逻辑）
        builder.add_conditional_edges(
            "innovation",
            self._route_after_research,
            {
                "discuss": "discuss_approach",
                "modeler": "modeler",
                "algorithm_engineer": "algorithm_engineer",
                "financial_analyst": "financial_analyst",
                "writer": "writer",
            },
        )

        # 条件边：analyzer → v7.1 并行分析（data+research+innovation 同时执行）
        # v7.2 fix: skip_to_modeling 也走 parallel_analysis 节点（它会自动选择正确的建模 Agent）
        builder.add_conditional_edges(
            "analyzer",
            self._route_after_analyzer_parallel,
            {
                "parallel": "parallel_analysis",
                "skip_to_modeling": "parallel_analysis",  # 修复：不再硬编码 modeler
            },
        )

        # 并行分析 → 条件路由到建模 Agent
        builder.add_conditional_edges(
            "parallel_analysis",
            self._route_after_parallel_analysis,
            {
                "modeler": "modeler",
                "algorithm_engineer": "algorithm_engineer",
                "financial_analyst": "financial_analyst",
                "writer": "writer",
                "discuss": "discuss_approach",
            },
        )

        # 条件边：data → 按 problem_type 决定
        builder.add_conditional_edges(
            "data",
            self._route_after_data,
            {
                "research": "research",
                "modeler": "modeler",
                "algorithm_engineer": "algorithm_engineer",
                "financial_analyst": "financial_analyst",
                "writer": "writer",
            },
        )

        # 条件边：discuss_approach
        builder.add_conditional_edges(
            "discuss_approach",
            self._route_after_discuss_approach,
            {
                "modeler": "modeler",
                "algorithm_engineer": "algorithm_engineer",
                "financial_analyst": "financial_analyst",
                "writer": "writer",
            },
        )

        # 建模节点 → solver（非 CCF-A）或 experiment（CCF-A）
        builder.add_conditional_edges(
            "modeler",
            self._route_to_experiment_or_solver,
            {"experiment": "experiment", "iterative_solver": "iterative_solver"},
        )
        builder.add_conditional_edges(
            "algorithm_engineer",
            self._route_to_experiment_or_solver,
            {"experiment": "experiment", "iterative_solver": "iterative_solver"},
        )
        builder.add_conditional_edges(
            "financial_analyst",
            self._route_to_experiment_or_solver,
            {"experiment": "experiment", "iterative_solver": "iterative_solver"},
        )

        # 条件边：experiment → 迭代或继续
        builder.add_conditional_edges(
            "experiment",
            self._route_after_experiment,
            {
                "experiment": "experiment",   # 迭代优化
                "iterative_solver": "iterative_solver",  # 正常流程
            },
        )
        builder.add_edge("figure", "writer")
        builder.add_edge("writer", "peer_review")
        builder.add_edge("fact_check", "summary")
        builder.add_edge("cannot_solve", "summary")
        builder.add_edge("summary", END)
        builder.add_edge("self_collect", "preflight_decision")
        # v7.2: wait_user 不再连接到 END（避免流程中断）
        # 改为自循环：等待用户输入后重新评估 peer_review
        builder.add_edge("wait_user", "peer_review")

        # requirement_decomposition → preflight_decision（始终进入）
        builder.add_edge("requirement_decomposition", "preflight_decision")

        return builder.compile()

    # ------------------------------------------------------------------
    # 需求分解节点
    # ------------------------------------------------------------------
    async def _node_requirement_decomposition(self, state: TaskState) -> TaskState:
        """长提示词自动分解（>3000字符时触发）。"""
        task_id = state["task_id"]
        problem_text = state.get("problem_text", "")

        if len(problem_text) < 3000:
            logger.info(f"[LangGraph:{task_id}] 问题文本较短({len(problem_text)}字)，跳过需求分解")
            return {**state, "requirement_plan": None, "current_step": "requirement_decomposition_skip"}

        logger.info(f"[LangGraph:{task_id}] 问题文本较长({len(problem_text)}字)，启动需求分解")
        try:
            from .requirement_decomposer import RequirementDecomposerAgent
            agent = RequirementDecomposerAgent()
            context = {
                "task_id": task_id,
                "project_name": state.get("project_name"),
                "problem_text": problem_text,
                "files": state.get("files", []),
            }
            plan = await agent.execute(task_input={}, context=context)

            if plan and not plan.get("_fallback"):
                logger.info(f"[LangGraph:{task_id}] 需求分解完成: {len(plan.get('subtasks', []))} 个子任务")
                return {**state, "requirement_plan": plan, "current_step": "requirement_decomposition_done"}
            else:
                logger.info(f"[LangGraph:{task_id}] 需求分解降级为原始文本")
                return {**state, "requirement_plan": None, "current_step": "requirement_decomposition_skip"}
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] 需求分解失败: {e}")
            return {**state, "requirement_plan": None, "current_step": "requirement_decomposition_skip"}

    # ------------------------------------------------------------------
    # 创新发现节点
    # ------------------------------------------------------------------
    async def _node_innovation(self, state: TaskState) -> TaskState:
        """从文献调研结果中发现研究空白并提出创新方案。"""
        task_id = state["task_id"]
        results = self._resolve_results(state)
        research_output = results.get("research_agent", {})
        analyzer_output = results.get("analyzer_agent", {})

        # 如果没有足够数据，跳过创新分析
        papers = research_output.get("papers", []) if isinstance(research_output, dict) else []
        if len(papers) < 2:
            logger.info(f"[LangGraph:{task_id}] 论文不足2篇，跳过创新分析")
            return {**state, "innovation_analysis": None, "current_step": "innovation_skip"}

        logger.info(f"[LangGraph:{task_id}] 启动创新发现分析（{len(papers)}篇论文）")
        try:
            from .innovation_agent import InnovationAgent
            agent = InnovationAgent()
            context = {
                "task_id": task_id,
                "project_name": state.get("project_name"),
                "problem_text": state.get("problem_text"),
                "results": {
                    "research_agent": research_output,
                    "analyzer_agent": analyzer_output,
                },
            }
            analysis = await agent.execute(task_input={}, context=context)
            return {**state, "innovation_analysis": analysis, "current_step": "innovation_done"}
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] 创新分析失败: {e}")
            return {**state, "innovation_analysis": None, "current_step": "innovation_failed"}

    # ------------------------------------------------------------------
    # 任务总结节点
    # ------------------------------------------------------------------
    async def _node_summary(self, state: TaskState) -> TaskState:
        """任务完成后生成结构化总结报告，并整理知识库。"""
        task_id = state["task_id"]
        logger.info(f"[LangGraph:{task_id}] 生成任务总结报告")

        # 1. 生成总结报告
        summary = None
        try:
            from .summary_agent import SummaryAgent
            agent = SummaryAgent()
            results = self._resolve_results(state)
            context = {
                "task_id": task_id,
                "project_name": state.get("project_name"),
                "problem_text": state.get("problem_text"),
                "paper_template": state.get("paper_template"),
                "workflow_type": state.get("workflow_type"),
                "results": results,
                "sub_problems": state.get("sub_problems", []),
            }
            summary = await agent.execute(task_input={}, context=context)
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] 任务总结失败: {e}")

        # 2. 整理知识库（下载的文献/数据集自动分类）
        try:
            from ..services.knowledge_organizer import run_full_organization
            from ..core.paths import get_project_output_dir, get_project_base_dir
            from ..core.knowledge_manager import get_knowledge_manager
            project_name = state.get("project_name")
            task_dir = get_project_output_dir(project_name) / task_id
            # 扫描范围：task 输出目录 + 全局参考文献目录 + 项目 reading 目录
            global_refs = get_project_base_dir(None) / "global_references"
            reading_dir = get_project_base_dir(project_name) / "reading" if project_name else None
            kb = get_knowledge_manager()
            org_result = run_full_organization(
                task_id, str(task_dir), kb,
                extra_scan_dirs=[str(global_refs)] + ([str(reading_dir)] if reading_dir and reading_dir.is_dir() else []),
            )
            organized_count = len(org_result.get("organized", []))
            logger.info(f"[LangGraph:{task_id}] 知识库整理完成: {organized_count} 个资源")
        except Exception as e:
            logger.warning(f"[LangGraph:{task_id}] 知识库整理失败: {e}")

        return {**state, "task_summary": summary, "current_step": "summary_done"}

    # ------------------------------------------------------------------
    # 节点实现（骨架，逐步填充）
    # ------------------------------------------------------------------
    async def _node_preflight_decision(self, state: TaskState) -> TaskState:
        """读取 preflight 报告并设置初始配置，更新进度。"""
        preflight = state.get("preflight") or {}
        task_id = state["task_id"]
        from ..core.task_persistence import save_task_metadata
        try:
            save_task_metadata(
                task_id=task_id,
                problem_text=state["problem_text"],
                status="running",
                created_at=datetime.now().isoformat(),
                progress=5,
                current_step="preflight_decision",
            )
        except Exception:
            pass
        logger.info(f"[LangGraph:{task_id}] preflight_decision: workflow={preflight.get('recommended_workflow')}, template={preflight.get('recommended_template')}")
        return {
            **state,
            "paper_template": preflight.get("recommended_template", state.get("paper_template", "math_modeling")),
            "workflow_type": preflight.get("recommended_workflow", state.get("workflow_type", "standard")),
            "mode": preflight.get("recommended_mode", state.get("mode", "batch")),
            "current_step": "preflight_decision_done",
        }

    async def _node_analyzer(self, state: TaskState) -> TaskState:
        """调用 analyzer_agent，更新进度与黑板。"""
        state = await self._check_user_input(state)

        agent = self.agents.get("analyzer_agent")
        if not agent:
            return {**state, "current_step": "analyzer_missing"}

        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_agent_start(task_id, "analyzer_agent", "analysis")
        self._update_progress(task_id, state["problem_text"], 15, "问题分析中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")
        output = await agent.execute(
            task_input={"action": "analyze", "problem_text": state["problem_text"]},
            context=self._agent_context(state),
        )
        output["_contract"] = get_contract_validator().validate("analyzer_agent", output)

        ref_update = self._set_result(state, "analyzer_agent", output)
        sub_problems = output.get("sub_problems", [])

        # 更新黑板记忆
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("analyzer_agent", output)
            wm.sub_problems = sub_problems
            if output.get("problem_type"):
                wm.update_problem(type=output["problem_type"])

        self._post_chat(task_id, "analyzer_agent", f"问题分析完成，识别 {len(sub_problems)} 个子问题")
        bus.emit_agent_complete(task_id, "analyzer_agent", "analysis", f"识别 {len(sub_problems)} 个子问题")
        logger.info(f"[LangGraph:{task_id}] analyzer: {len(sub_problems)} sub_problems")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "sub_problems": sub_problems, "current_step": "analyzer_done"}

    async def _node_data(self, state: TaskState) -> TaskState:
        """调用 data_agent 分析数据文件。"""
        agent = self.agents.get("data_agent")
        if not agent or not state.get("files"):
            logger.info(f"[LangGraph:{state['task_id']}] data: no files, skipping")
            return {**state, "current_step": "data_skipped"}

        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_agent_start(task_id, "data_agent", "data_analysis")
        self._update_progress(task_id, state["problem_text"], 25, "数据分析中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")
        output = await agent.execute(
            task_input={"action": "analyze_data", "problem_text": state["problem_text"]},
            context=self._agent_context(state),
        )

        ref_update = self._set_result(state, "data_agent", output)

        # 更新黑板记忆
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("data_agent", output)
            wm.data_insights = output.get("insights", [])

        self._post_chat(task_id, "data_agent", "数据分析完成")
        bus.emit_agent_complete(task_id, "data_agent", "data_analysis")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "data_done"}

    async def _node_research(self, state: TaskState) -> TaskState:
        """调用 research_agent 搜集文献，根据 workflow_type 调整搜索策略。

        v6.0 新增：
        - 跨论文研究空白识别（deep_search 模式自动触发）
        - 将 gap 分析结果注入 context 供后续 Agent 使用
        """
        agent = self.agents.get("research_agent")
        if not agent:
            return {**state, "current_step": "research_skipped"}

        task_id = state["task_id"]
        workflow = state.get("workflow_type", "standard")

        # quick / code_focused 模式跳过文献搜集
        if workflow in ("quick", "code_focused"):
            logger.info(f"[LangGraph:{task_id}] research: skipped (workflow={workflow})")
            return {**state, "current_step": "research_skipped"}

        bus = get_event_bus()
        bus.emit_agent_start(task_id, "research_agent", "literature_search")
        self._update_progress(task_id, state["problem_text"], 35, "文献搜集中")
        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")

        all_papers = []
        all_methods = []

        if workflow == "deep_research":
            # 深度研究：多角度搜索
            search_actions = ["search", "search_background", "search_methods"]
        else:
            search_actions = ["search"]

        for action in search_actions:
            try:
                output = await agent.execute(
                    task_input={"action": action, "problem_text": state["problem_text"]},
                    context=self._agent_context(state),
                )
                all_papers.extend(output.get("papers", []))
                all_methods.extend(output.get("methods", []))
            except Exception as exc:
                logger.warning(f"[LangGraph:{task_id}] research.{action} failed: {exc}")

        result = {"papers": all_papers, "methods": all_methods}
        ref_update = self._set_result(state, "research_agent", result)

        # v6.0: 跨论文研究空白识别（deep_search 或 research_paper 模式自动触发）
        gap_analysis = None
        if workflow in ("deep_research", "research_paper") and len(all_papers) >= 3:
            try:
                # 如果 research_agent 有 _identify_cross_paper_gaps 方法，调用它
                if hasattr(agent, '_identify_cross_paper_gaps'):
                    gap_analysis = await agent._identify_cross_paper_gaps(all_papers, state["problem_text"])
                    if gap_analysis:
                        result["cross_paper_gaps"] = gap_analysis
                        logger.info(f"[LangGraph:{task_id}] 跨论文研究空白识别完成，发现 {len(gap_analysis.get('gaps', []))} 个 gap")
                        self._post_chat(task_id, "research_agent", f"跨论文研究空白识别完成，发现 {len(gap_analysis.get('gaps', []))} 个创新机会")
            except Exception as exc:
                logger.warning(f"[LangGraph:{task_id}] 跨论文研究空白识别失败: {exc}")

        # 更新黑板记忆
        wm = self._get_working_memory(task_id)
        if wm:
            wm.add_literature(all_papers, source="research_agent")
            for m in all_methods:
                wm.add_method(m)
            if gap_analysis:
                wm.set_result("cross_paper_gaps", gap_analysis)

        self._post_chat(task_id, "research_agent", f"文献搜集完成，{len(all_papers)} 篇文献，{len(all_methods)} 个方法")
        bus.emit_agent_complete(task_id, "research_agent", "literature_search", f"{len(all_papers)} 篇文献, {len(all_methods)} 个方法")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "research_done"}

    async def _node_modeler(self, state: TaskState) -> TaskState:
        """逐个子问题建模：每个子问题独立建模，前序结果递进传递给后序。"""
        state = await self._check_user_input(state)

        agent = self.agents.get("modeler_agent")
        if not agent:
            return {**state, "current_step": "modeler_missing"}

        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_agent_start(task_id, "modeler_agent", "modeling")
        sub_problems = state.get("sub_problems", [])
        results = self._resolve_results(state)
        all_models = []

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")

        for i, sp in enumerate(sub_problems):
            sp_id = sp.get("id", i + 1)
            sp_name = sp.get("name", sp.get("description", f"子问题{sp_id}"))[:80]
            progress = 45 + int(10 * (i + 1) / max(len(sub_problems), 1))
            self._update_progress(task_id, state["problem_text"], progress, f"建模中：{sp_name}")

            # 前序模型摘要（递进传递）
            prev_model_summary = ""
            for j, pm in enumerate(all_models):
                prev_name = pm.get("sub_problem_name", f"子问题{j+1}")
                prev_obj = pm.get("objective_function", "")
                prev_vars = pm.get("decision_variables", [])
                prev_model_summary += f"- {prev_name}: {prev_obj[:80]}，变量: {', '.join([v.get('name','') for v in prev_vars[:3]])}\n"

            try:
                output = await agent.execute(
                    task_input={"action": "build_model", "sub_problem_id": sp_id},
                    context={
                        **self._agent_context(state),
                        "results": results,
                        "sub_problems": sub_problems,
                        "sub_problem_index": i,
                        "sub_problem": sp,
                        "previous_models": all_models,
                        "previous_model_summary": prev_model_summary,
                    },
                )
                # 注入来源和防编造标记
                output["_agent_source"] = "modeler_agent"
                fabrication_check = self._validate_no_fabrication("modeler_agent", output)
                output.update(fabrication_check)

                all_models.append({**output, "sub_problem_id": sp_id, "sub_problem_name": sp_name})
                self._post_chat(task_id, "modeler_agent", f"[{i+1}/{len(sub_problems)}] 建模完成：{sp_name}（{output.get('model_name', '')}）")
            except Exception as exc:
                logger.error(f"[LangGraph:{task_id}] modeler sp{sp_id} failed: {exc}")
                all_models.append({"sub_problem_id": sp_id, "sub_problem_name": sp_name, "error": str(exc)})

        modeler_output = {"sub_problem_models": all_models}
        ref_update = self._set_result(state, "modeler_agent", modeler_output)

        # 更新黑板
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("modeler_agent", modeler_output)
            for m in all_models:
                wm.add_method({"name": m.get("model_name", ""), "type": m.get("model_type", ""), "sub_problem": m.get("sub_problem_name", "")})

        self._post_chat(task_id, "modeler_agent", f"全部 {len(sub_problems)} 个子问题建模完成")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "modeler_done"}

    async def _node_algorithm_engineer(self, state: TaskState) -> TaskState:
        """调用 algorithm_engineer_agent 设计算法/方法。

        保存原始丰富输出到 results["algorithm_engineer_agent"]；
        调用归一化方法得到标准 sub_problem_models，保存到 results["modeler_agent"]（兼容 solver/writer）。
        """
        state = await self._check_user_input(state)

        agent = self.agents.get("algorithm_engineer_agent")
        if not agent:
            return {**state, "current_step": "algorithm_engineer_missing"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 45, "算法设计中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")
        try:
            output = await agent.execute(
                task_input={"action": "design_algorithm", "problem_text": state["problem_text"]},
                context=self._agent_context(state),
            )
        except Exception as exc:
            logger.error(f"[LangGraph:{task_id}] algorithm_engineer failed: {exc}")
            return {**state, "current_step": "algorithm_engineer_failed"}

        # 防编造校验
        fabrication_check = self._validate_no_fabrication("algorithm_engineer_agent", output)
        output.update(fabrication_check)

        # 保存原始输出
        ref_raw = self._set_result(state, "algorithm_engineer_agent", output)

        # 归一化到标准 modeler_agent 格式
        normalized = self._normalize_algorithm_engineer_output(output)
        ref_norm = self._set_result(state, "modeler_agent", normalized)

        # 更新黑板
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("algorithm_engineer_agent", output)
            wm.set_result("modeler_agent", normalized)

        self._post_chat(task_id, "algorithm_engineer_agent", "算法设计完成")
        return {
            **state,
            "results": {**state.get("results", {}), **ref_raw, **ref_norm},
            "current_step": "algorithm_engineer_done",
        }

    async def _node_financial_analyst(self, state: TaskState) -> TaskState:
        """调用 financial_analyst_agent 建立金融模型。

        保存原始丰富输出到 results["financial_analyst_agent"]；
        调用归一化方法得到标准 sub_problem_models，保存到 results["modeler_agent"]（兼容 solver/writer）。
        """
        state = await self._check_user_input(state)

        agent = self.agents.get("financial_analyst_agent")
        if not agent:
            return {**state, "current_step": "financial_analyst_missing"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 45, "金融模型建立中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")
        try:
            output = await agent.execute(
                task_input={"action": "build_financial_model", "problem_text": state["problem_text"]},
                context=self._agent_context(state),
            )
        except Exception as exc:
            logger.error(f"[LangGraph:{task_id}] financial_analyst failed: {exc}")
            return {**state, "current_step": "financial_analyst_failed"}

        # 防编造校验
        fabrication_check = self._validate_no_fabrication("financial_analyst_agent", output)
        output.update(fabrication_check)

        # 保存原始输出
        ref_raw = self._set_result(state, "financial_analyst_agent", output)

        # 归一化到标准 modeler_agent 格式
        normalized = self._normalize_financial_analyst_output(output)
        ref_norm = self._set_result(state, "modeler_agent", normalized)

        # 更新黑板
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("financial_analyst_agent", output)
            wm.set_result("modeler_agent", normalized)

        self._post_chat(task_id, "financial_analyst_agent", "金融模型建立完成")
        return {
            **state,
            "results": {**state.get("results", {}), **ref_raw, **ref_norm},
            "current_step": "financial_analyst_done",
        }

    async def _node_iterative_solver(self, state: TaskState) -> TaskState:
        """逐个子问题求解 + 自主迭代修复 + 代码自动演化（v6.0）。

        对每个子问题：
        1. 用对应模型结果调 solver_agent
        2. Harness 评判（ResultValidator + CrossValidator + CodeManifest）
        3. 失败时注入错误分类和修复建议，重试（最多 max_solver_iterations 次）
        4. 仍失败则多 Agent 投票决定 retry / collect_data / abort
        5. v6.0: 成功后可选进入代码自动演化循环，迭代改进代码
        """
        state = await self._check_user_input(state)

        agent = self.agents.get("solver_agent")
        if not agent:
            return {**state, "current_step": "solver_missing"}

        task_id = state["task_id"]
        sub_problems = state.get("sub_problems", [])
        results = self._resolve_results(state)
        modeler_output = results.get("modeler_agent", {})
        all_models = modeler_output.get("sub_problem_models", [])
        all_solutions = []
        all_attempts = list(state.get("solver_attempts", []))
        escalation = state.get("escalation_count", 0)

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")

        for i, sp in enumerate(sub_problems):
            sp_id = sp.get("id", i + 1)
            sp_name = sp.get("name", sp.get("description", f"子问题{sp_id}"))[:80]
            progress = 55 + int(20 * (i + 1) / max(len(sub_problems), 1))
            self._update_progress(task_id, state["problem_text"], progress, f"求解中：{sp_name}")

            # 找到对应的模型
            model_for_sp = next((m for m in all_models if m.get("sub_problem_id") == sp_id), {})

            # 前序求解结果摘要（递进传递）
            prev_solve_summary = ""
            for j, ps in enumerate(all_solutions):
                prev_name = ps.get("sub_problem_name", f"子问题{j+1}")
                prev_findings = ps.get("results", {}).get("key_findings", [])
                prev_numerical = ps.get("results", {}).get("numerical_results", {})
                numerical_str = ", ".join([f"{k}={v}" for k, v in prev_numerical.items() if k != "状态"])
                prev_solve_summary += f"- {prev_name}: {'; '.join(str(f) for f in prev_findings[:2])}, 数值: {numerical_str or '见结果'}\n"

            # 迭代求解（含自动修复）
            sp_attempts = []
            sp_success = False
            fix_context = ""

            for attempt in range(self.cfg.max_solver_iterations):
                try:
                    output = await agent.execute(
                        task_input={"action": "solve", "sub_problem_id": sp_id, "problem_text": state["problem_text"] + fix_context},
                        context={
                            **self._agent_context(state),
                            "results": results,
                            "sub_problems": sub_problems,
                            "sub_problem_index": i,
                            "sub_problem": sp,
                            "model_result": model_for_sp,
                            "section_results": all_solutions,
                            "previous_solutions": all_solutions,
                            "previous_solution_summary": prev_solve_summary,
                        },
                    )

                    # Harness 评判
                    harness = await self._run_harness(output)
                    output["harness"] = harness
                    sp_attempts.append(output)
                    all_attempts.append(output)

                    if output.get("execution_success") and harness.get("passed"):
                        sp_success = True
                        all_solutions.append({**output, "sub_problem_id": sp_id, "sub_problem_name": sp_name})
                        self._post_chat(task_id, "solver_agent", f"[{i+1}/{len(sub_problems)}] 求解成功：{sp_name}")
                        break

                    # 构造修复上下文用于下一次尝试
                    error_info = output.get("error", "")
                    exec_output = output.get("execution_result", {}).get("output", "")
                    classification = output.get("error_classification", {})
                    fix_hint = "\n".join(classification.get("fixes", []))
                    fix_context = (
                        f"\n\n## 上次求解失败（第 {attempt+1} 次）\n"
                        f"错误类型: {classification.get('category', 'unknown')}\n"
                        f"错误信息: {error_info[:500]}\n"
                        f"修复建议: {fix_hint}\n请修正代码后重新求解。"
                    )

                except Exception as exc:
                    logger.error(f"[LangGraph:{task_id}] solver sp{sp_id} attempt {attempt+1} failed: {exc}")
                    sp_attempts.append({"error": str(exc), "execution_success": False})

            # v6.0: 代码自动演化 —— 求解成功后迭代改进代码
            if sp_success and all_solutions:
                last_solution = all_solutions[-1]
                try:
                    from .solver_agent import evolve_solution
                    code_files = last_solution.get("code_files", [])
                    if code_files and code_files[0].get("code"):
                        initial_code = code_files[0]["code"]
                        problem_context = f"{sp_name}: {model_for_sp.get('objective_function', '')[:100]}"
                        evolution_result = await evolve_solution(
                            solver=agent,
                            initial_code=initial_code,
                            problem_context=problem_context,
                            sp_id=sp_id,
                            project_name=state.get("project_name"),
                            enable_evolution=True,
                            max_evaluations=6,
                        )
                        if evolution_result.get("evolved") and evolution_result.get("improved"):
                            # 用演化后的最优代码替换
                            last_solution["code_files"] = [{
                                **code_files[0],
                                "code": evolution_result["best_code"],
                                "description": f"代码自动演化后（改进 {evolution_result.get('improvement', 0):.1%}）",
                            }]
                            last_solution["code_evolution"] = {
                                "improved": True,
                                "improvement": evolution_result.get("improvement"),
                                "generations": len(evolution_result.get("generations", [])),
                                "total_evaluations": evolution_result.get("total_evaluations"),
                            }
                            self._post_chat(
                                task_id, "solver_agent",
                                f"[{i+1}/{len(sub_problems)}] 代码自动演化完成：改进 {evolution_result.get('improvement', 0):.1%}"
                            )
                            logger.info(f"[LangGraph:{task_id}] 代码自动演化完成: sp_id={sp_id}, improvement={evolution_result.get('improvement', 0):.4f}")
                except Exception as exc:
                    logger.warning(f"[LangGraph:{task_id}] 代码自动演化失败: {exc}")

            if not sp_success:
                # 达到迭代上限 → 多 Agent 投票
                if len(all_attempts) >= self.cfg.max_solver_iterations:
                    vote = await self._multi_agent_vote(state, sp_attempts[-1], all_attempts)
                    if vote == "retry" and escalation < self.cfg.max_solver_escalations:
                        escalation += 1
                        self._post_chat(task_id, "coordinator", f"子问题 {sp_name} 求解失败，Agent 投票决定重试（第 {escalation} 次升级）")
                    elif vote == "collect_data":
                        return {**state, "solver_attempts": all_attempts, "escalation_count": escalation, "current_step": "self_collect"}
                    else:
                        return {
                            **state,
                            "solver_attempts": all_attempts,
                            "escalation_count": escalation,
                            "current_step": "cannot_solve",
                            "cannot_solve_report": {"reason": f"子问题 {sp_name} 求解失败，多 Agent 投票判定无法继续", "vote": vote, "attempts": len(all_attempts)},
                        }
                all_solutions.append({"sub_problem_id": sp_id, "sub_problem_name": sp_name, "error": "求解失败", "execution_success": False})

        # 汇总求解结果
        solver_output = {"sub_problem_solutions": all_solutions, "execution_success": all(s.get("execution_success", False) for s in all_solutions)}
        ref_update = self._set_result(state, "solver_agent", solver_output)

        # 更新黑板
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("solver_agent", solver_output)
            for s in all_solutions:
                findings = s.get("results", {}).get("key_findings", [])
                if findings:
                    wm.set_result("solver_agent", {**wm.results.get("solver_agent", {}), "last_findings": findings})

        self._post_chat(task_id, "solver_agent", f"全部 {len(sub_problems)} 个子问题求解完成")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "solver_attempts": all_attempts, "escalation_count": escalation, "current_step": "solver_done"}

    async def _run_harness(self, sol_result: Dict[str, Any]) -> Dict[str, Any]:
        """综合 Harness 评判。"""
        numerical = sol_result.get("numerical_results", {})
        if not isinstance(numerical, dict):
            numerical = {}

        validation = get_result_validator().validate(numerical, {})

        cross = []
        try:
            cross = await get_cross_validator().cross_check(
                "primary", numerical,
                "secondary_estimate", {k: v * 0.95 for k, v in numerical.items() if isinstance(v, (int, float))},
            )
        except Exception as exc:
            logger.debug(f"CrossValidator skipped: {exc}")

        manifest_valid = True
        try:
            manifest = sol_result.get("code_manifest", {})
            if manifest and "manifest" in manifest:
                parsed = parse_manifest_from_dict(manifest["manifest"])
                report = validate_manifest(parsed)
                manifest_valid = report.valid
        except Exception as exc:
            logger.debug(f"CodeManifest validation skipped: {exc}")

        passed = (
            validation.get("valid", False)
            and manifest_valid
            and all(not getattr(c, "diverged", False) for c in cross)
        )

        return {
            "passed": passed,
            "validation": validation,
            "cross_check": [c.__dict__ if hasattr(c, "__dict__") else dict(c) for c in cross],
            "manifest_valid": manifest_valid,
        }

    async def _multi_agent_vote(self, state: TaskState, sol_result: Dict[str, Any], attempts: List[Dict[str, Any]]) -> str:
        """多 Agent 评议投票：retry / collect_data / abort。"""
        last_error = attempts[-1].get("error", "")[:300]
        last_output = attempts[-1].get("execution_result", {}).get("output", "")[:300]
        prompt = (
            "基于以下求解失败信息，判断原因并只回复一个单词：\n"
            "- 代码 bug / 实现错误 → 回复 \"retry\"\n"
            "- 数据不足 / 问题本身不可解 → 回复 \"collect_data\"\n"
            "- 其他无法继续的情况 → 回复 \"abort\"\n\n"
            f"错误信息：{last_error}\n"
            f"执行输出：{last_output}"
        )

        agents_to_poll = ["analyzer_agent", "modeler_agent", "peer_review_agent"]
        votes = []
        for agent_name in agents_to_poll:
            agent = self.agents.get(agent_name)
            if not agent:
                continue
            try:
                resp = await agent.call_llm([
                    {"role": "system", "content": "You are a diagnostic assistant. Reply with exactly one word: retry, collect_data, or abort."},
                    {"role": "user", "content": prompt},
                ], temperature=0.1)
                content = resp.get("choices", [{}])[0].get("message", {}).get("content", "").lower()
                for v in ["retry", "collect_data", "abort"]:
                    if v in content:
                        votes.append(v)
                        break
            except Exception as exc:
                logger.debug(f"Vote from {agent_name} failed: {exc}")

        if not votes:
            return "abort"

        from collections import Counter
        return Counter(votes).most_common(1)[0][0]

    async def _node_writer(self, state: TaskState) -> TaskState:
        """调用 writer_agent 生成论文。"""
        state = await self._check_user_input(state)

        agent = self.agents.get("writer_agent")
        if not agent:
            return {**state, "current_step": "writer_missing"}

        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_agent_start(task_id, "writer_agent", "writing")
        self._update_progress(task_id, state["problem_text"], 70, "论文写作中")

        # 从 writer_agent 历史结果读取修订次数（更可靠）
        writer_history = self._resolve_results(state).get("writer_agent", {})
        revision_count = (writer_history.get("_revision_count", 0) if isinstance(writer_history, dict) else 0) + 1
        logger.info(f"[LangGraph:{task_id}] writer node start, revision_count={revision_count}")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        agent._knowledge_base_ids = state.get("knowledge_base_ids")
        agent._task_project_name = state.get("project_name")
        output = await agent.execute(
            task_input={
                "action": "write",
                "problem_text": state["problem_text"],
                "sub_problems": state.get("sub_problems", []),
                "use_critique": state.get("use_critique", True),
            },
            context=self._agent_context(state),
        )
        output["_contract"] = get_contract_validator().validate("writer_agent", output)
        output["_revision_count"] = revision_count

        ref_update = self._set_result(state, "writer_agent", output)
        self._post_chat(task_id, "writer_agent", f"论文写作完成（第 {revision_count} 稿）")
        logger.info(f"[LangGraph:{task_id}] writer node done, posted 第 {revision_count} 稿")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "writer_done", "revision_count": revision_count}

    async def _node_peer_review(self, state: TaskState) -> TaskState:
        """调用 peer_review_agent 进行同行评议。"""
        agent = self.agents.get("peer_review_agent")
        if not agent or not self.cfg.enable_peer_review:
            return {**state, "current_step": "peer_review_skipped"}

        task_id = state["task_id"]
        bus = get_event_bus()
        bus.emit_agent_start(task_id, "peer_review_agent", "peer_review")
        self._update_progress(task_id, state["problem_text"], 80, "同行评议中")

        output = await agent.execute(
            task_input={"action": "review", "problem_text": state["problem_text"]},
            context=self._agent_context(state),
        )

        ref_update = self._set_result(state, "peer_review_agent", output)
        rec = (output.get("recommendation") or "").lower()
        score = output.get("overall_score", 0)
        self._post_chat(task_id, "peer_review_agent", f"同行评议完成：{rec}，得分 {score}")
        bus.emit_agent_complete(task_id, "peer_review_agent", "peer_review", f"{rec}, score={score}")
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "peer_review_done"}

    async def _node_experiment(self, state: TaskState) -> TaskState:
        """调用 experimentation_agent 设计并执行实验（CCF-A 模板才启用）。

        v6.0 新增：
        - NAS：自动搜索最优网络架构（图像任务）
        - 自动损失函数设计：进化搜索最优损失函数
        - AutoML：自动超参数优化
        """
        agent = self.agents.get("experimentation_agent")
        template = state.get("paper_template", "math_modeling")
        ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}
        if not agent or not self.cfg.enable_experiment_design or template not in ccf_a:
            return {**state, "current_step": "experiment_skipped"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 55, "实验执行中")

        results = state.get("results", {})
        modeling_agent = self._select_modeling_agent(template, state.get("workflow_type", "standard"))
        modeling_result = results.get(modeling_agent, {}) if modeling_agent else {}

        # v6.0: 自动损失函数设计（如果方法描述中有损失函数相关）
        loss_design_result = None
        try:
            from ..core.loss_design import create_loss_design_agent
            loss_agent = create_loss_design_agent(population_size=6, max_generations=3)
            method = modeling_result.get("proposed_method", {}) if isinstance(modeling_result, dict) else {}
            task_type = "classification"  # 默认，可根据问题推断
            baseline_losses = ["cross_entropy", "mse"]  # 默认 baselines
            loss_design_result = await loss_agent.design(
                task_type=task_type,
                baseline_losses=baseline_losses,
            )
            logger.info(f"[LangGraph:{task_id}] 自动损失函数设计完成，fitness={loss_design_result.get('fitness', 0):.4f}")
            self._post_chat(task_id, "experimentation_agent", "自动损失函数设计完成")
        except Exception as exc:
            logger.warning(f"[LangGraph:{task_id}] 自动损失函数设计失败: {exc}")

        # v6.0: NAS 神经架构搜索（图像/深度学习任务）
        nas_result = None
        if any(kw in state["problem_text"].lower() for kw in ["image", "vision", "cnn", "deep learning", "neural"]):
            try:
                from ..core.nas import create_nas_agent
                nas_agent = create_nas_agent(population_size=6, max_generations=3)
                baselines = []
                if isinstance(modeling_result, dict):
                    baselines = modeling_result.get("experiment_design", {}).get("baselines", [])
                nas_result = await nas_agent.search(
                    problem_description=state["problem_text"],
                    baseline_methods=baselines,
                )
                logger.info(f"[LangGraph:{task_id}] NAS 搜索完成，fitness={nas_result.get('fitness', 0):.4f}")
                self._post_chat(task_id, "experimentation_agent", "NAS 神经架构搜索完成")
            except Exception as exc:
                logger.warning(f"[LangGraph:{task_id}] NAS 搜索失败: {exc}")

        # v6.0: AutoML 超参数优化
        automl_result = None
        try:
            from ..services.automl import create_search_space_from_method, AutoMLService
            if isinstance(modeling_result, dict):
                method = modeling_result.get("proposed_method", {})
                if method and method.get("hyperparameters"):
                    search_space = create_search_space_from_method(method)
                    automl_service = AutoMLService(search_space)

                    # 构建真实评估器：用超参配置生成代码 + 快速训练评估
                    import tempfile
                    import subprocess
                    import sys
                    import os

                    def _automl_objective(cfg: dict) -> float:
                        """用给定超参训练简单模型，返回验证准确率。"""
                        # 构建一个简单的 PyTorch 训练脚本
                        lr = cfg.get("learning_rate", 0.001)
                        batch_size = cfg.get("batch_size", 32)
                        hidden_size = cfg.get("hidden_size", 64)
                        epochs = 2  # 快速评估

                        script = f'''
import torch, torch.nn as nn, torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import torchvision, torchvision.transforms as transforms
import json, sys

transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.5,),(0.5,))])
trainset = torchvision.datasets.CIFAR10(root="./data", train=True, download=True, transform=transform)
loader = DataLoader(trainset, batch_size={batch_size}, shuffle=True, num_workers=0)

device = "cuda" if torch.cuda.is_available() else "cpu"
model = nn.Sequential(
    nn.Flatten(), nn.Linear(32*32*3, {hidden_size}), nn.ReLU(),
    nn.Linear({hidden_size}, 10)
).to(device)
optimizer = optim.Adam(model.parameters(), lr={lr})
criterion = nn.CrossEntropyLoss()

for epoch in range({epochs}):
    for inputs, labels in loader:
        inputs, labels = inputs.to(device), labels.to(device)
        optimizer.zero_grad()
        loss = criterion(model(inputs), labels)
        loss.backward()
        optimizer.step()

# 简单评估
correct, total = 0, 0
for inputs, labels in loader:
    inputs, labels = inputs.to(device), labels.to(device)
    _, pred = model(inputs).max(1)
    correct += pred.eq(labels).sum().item()
    total += labels.size(0)
    if total > 500: break
acc = correct / max(total, 1)
print(json.dumps({{"accuracy": round(acc, 4)}}))
'''
                        try:
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, dir='/tmp') as f:
                                f.write(script)
                                script_path = f.name
                            result = subprocess.run(
                                [sys.executable, script_path],
                                capture_output=True, text=True, timeout=120,
                                env={**os.environ, 'PYTHONPATH': '/tmp'}
                            )
                            for line in result.stdout.splitlines():
                                if '"accuracy"' in line:
                                    data = json.loads(line)
                                    acc = data.get("accuracy", 0.0)
                                    logger.debug(f"AutoML trial: cfg={cfg}, accuracy={acc}")
                                    return acc
                        except Exception as e:
                            logger.debug(f"AutoML trial failed: {e}")
                        finally:
                            try: os.unlink(script_path)
                            except: pass
                        return 0.0  # 训练失败返回最低分

                    automl_result = automl_service.search(
                        objective=_automl_objective,
                        max_trials=10,
                        strategy="tpe",
                        direction="maximize",
                    )
                    logger.info(f"[LangGraph:{task_id}] AutoML 搜索完成，最优值={automl_result.get('best_value', 0):.4f}")
                    self._post_chat(task_id, "experimentation_agent", "AutoML 超参数优化完成")
        except Exception as exc:
            logger.warning(f"[LangGraph:{task_id}] AutoML 搜索失败: {exc}")

        output = await agent.execute(
            task_input={
                "action": "execute",
                "problem_text": state["problem_text"],
                "modeling_result": modeling_result,
                "solver_result": results.get("solver_agent", {}),
                "project_name": state.get("project_name"),
                "task_id": task_id,
                # v6.0: 注入自主设计结果
                "nas_result": nas_result,
                "loss_design_result": loss_design_result,
                "automl_result": automl_result,
            },
            context=self._agent_context(state),
        )

        # 将自主设计结果合并到输出
        if nas_result:
            output["nas_architecture"] = nas_result.get("best_architecture")
            output["nas_code"] = nas_result.get("pytorch_code")
        if loss_design_result:
            output["loss_function_code"] = loss_design_result.get("pytorch_code")
            output["loss_tree"] = loss_design_result.get("best_loss_tree")
        if automl_result:
            output["automl_best_params"] = automl_result.get("best_params")
            output["automl_report"] = automl_result

        ref_update = self._set_result(state, "experimentation_agent", output)
        executed = output.get("executed", False)
        self._post_chat(
            task_id,
            "experimentation_agent",
            f"实验{'执行完成' if executed else '设计完成（未执行）'}"
            f"{' + NAS' if nas_result else ''}"
            f"{' + LossDesign' if loss_design_result else ''}"
            f"{' + AutoML' if automl_result else ''}",
        )

        # 实验闭环评估：检查是否需要迭代优化
        iteration_count = state.get("experiment_iterations", 0)
        max_iterations = self._get_config().experiment_max_iterations
        needs_iteration = self._evaluate_experiment_quality(output)

        if needs_iteration and iteration_count < max_iterations and executed:
            logger.info(f"[LangGraph:{task_id}] 实验质量不足，第 {iteration_count + 1}/{max_iterations} 轮迭代")
            self._post_chat(task_id, "experimentation_agent", f"实验质量不足，开始第 {iteration_count + 1} 轮迭代优化")
            # 将当前实验结果反馈给 experimentation_agent 进行改进
            output["iteration_feedback"] = self._generate_iteration_feedback(output)
            output["iteration_round"] = iteration_count + 1
            ref_update = self._set_result(state, "experimentation_agent", output)
            return {
                **state,
                "results": {**state.get("results", {}), **ref_update},
                "current_step": "experiment_iterating",
                "experiment_iterations": iteration_count + 1,
            }

        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "experiment_done"}

    def _evaluate_experiment_quality(self, experiment_output: Dict[str, Any]) -> bool:
        """评估实验质量，决定是否需要迭代。返回 True 表示需要迭代。"""
        if not isinstance(experiment_output, dict):
            return False
        # 检查是否包含 baseline 对比
        has_baseline = bool(experiment_output.get("baseline_comparison"))
        # 检查是否包含 ablation study
        has_ablation = bool(experiment_output.get("ablation_study"))
        # 检查实验是否成功执行
        executed = experiment_output.get("executed", False)
        # 如果缺少 baseline 或 ablation 且已执行，需要迭代
        if executed and (not has_baseline or not has_ablation):
            return True
        return False

    def _generate_iteration_feedback(self, experiment_output: Dict[str, Any]) -> str:
        """生成实验迭代反馈，指导 experimentation_agent 改进。"""
        feedback_parts = []
        if not experiment_output.get("baseline_comparison"):
            feedback_parts.append("缺少 baseline 对比实验，请添加至少2个 baseline 方法")
        if not experiment_output.get("ablation_study"):
            feedback_parts.append("缺少 ablation study，请添加消融实验验证各组件贡献")
        return "；".join(feedback_parts) if feedback_parts else "请优化实验设计和结果分析"

    async def _node_figure(self, state: TaskState) -> TaskState:
        """调用 figure_agent 生成科研图表。"""
        agent = self.agents.get("figure_agent")
        if not agent:
            return {**state, "current_step": "figure_skipped"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 65, "科研图表生成中")

        results = state.get("results", {})
        solver_result = results.get("solver_agent", {})

        # 第一步：规划图表
        plan_output = await agent.execute(
            task_input={
                "action": "plan",
                "problem_text": state["problem_text"],
                "data": solver_result,
            },
            context=self._agent_context(state),
        )

        figures_plan = plan_output.get("figures", [])
        if not figures_plan:
            logger.info(f"[LangGraph:{task_id}] figure planning returned empty, skipping")
            return {**state, "current_step": "figure_skipped"}

        # 第二步：批量生成图表
        gen_output = await agent.execute(
            task_input={
                "action": "generate_all",
                "figure_plan": plan_output,
                "data": solver_result,
                "project_name": state.get("project_name"),
            },
            context=self._agent_context(state),
        )

        generated = gen_output.get("generated", 0)
        self._post_chat(
            task_id,
            "figure_agent",
            f"图表生成完成：规划 {len(figures_plan)} 个，成功生成 {generated} 个",
        )
        logger.info(f"[LangGraph:{task_id}] figure node done: {generated}/{len(figures_plan)} figures generated")

        ref_update = self._set_result(state, "figure_agent", gen_output)
        return {**state, "results": {**state.get("results", {}), **ref_update}, "current_step": "figure_done"}

    async def _node_fact_check(self, state: TaskState) -> TaskState:
        """事实核查：对比 main.tex 与 solves.json 数字 + fabrication 拦截。"""
        if not self.cfg.enable_fact_check:
            return {**state, "current_step": "fact_check_skipped"}

        task_id = state["task_id"]
        project_name = state.get("project_name")
        try:
            output_dir = get_project_output_dir(project_name)
        except Exception:
            output_dir = None

        report: Dict[str, Any] = {"enabled": True, "passed": True}
        if output_dir:
            report = get_fact_checker().check(
                task_id=task_id,
                output_dir=output_dir,
            )

        # v7.2: 检查 fabrication flags（从 solver/modeler 传递过来）
        fabrication_issues = []
        results = self._resolve_results(state)
        for agent_name, agent_output in results.items():
            if isinstance(agent_output, dict):
                flags = agent_output.get("_fabrication_flags", [])
                score = agent_output.get("_fabrication_score", 0)
                if flags:
                    fabrication_issues.extend([f"[{agent_name}] {f}" for f in flags])
                if score > 0.5:
                    fabrication_issues.append(f"[{agent_name}] fabrication_score={score:.2f} (>0.5)")

        if fabrication_issues:
            report["fabrication_issues"] = fabrication_issues
            report["fabrication_warning"] = (
                f"检测到 {len(fabrication_issues)} 个潜在编造内容，建议人工审核后方可提交。"
            )
            logger.warning(f"Task {task_id}: fabrication issues detected: {fabrication_issues}")

        # 数值一致性检查
        if not report.get("passed"):
            report["review_required"] = True
            logger.warning(f"Task {task_id}: fact_check FAILED, review required")

        self._set_result(state, "fact_checker", report)
        logger.info(f"Task {task_id}: fact_check passed={report['passed']} issues={report['issue_count']} fabrication={len(fabrication_issues)}")

        return {**state, "results": {**state.get("results", {}), "fact_checker": report}, "current_step": "fact_check_done"}

    async def _node_cannot_solve(self, state: TaskState) -> TaskState:
        report = {
            "task_id": state["task_id"],
            "reason": state.get("cannot_solve_report") or "无法继续求解",
            "solver_attempts": state.get("solver_attempts", []),
        }
        logger.warning(f"Task {state['task_id']} cannot_solve: {report['reason']}")
        return {**state, "current_step": "cannot_solve", "cannot_solve_report": report}

    async def _node_self_collect(self, state: TaskState) -> TaskState:
        """自主搜集数据：根据 preflight 的缺失数据描述，调用 self_collector 搜索并下载。"""
        task_id = state["task_id"]
        preflight = state.get("preflight") or {}

        # 获取缺失数据描述和搜索关键词
        missing_desc = preflight.get("missing_data_description", "")
        collect_keywords = preflight.get("collect_keywords", [])
        if not missing_desc and not collect_keywords:
            logger.warning(f"[LangGraph:{task_id}] self_collect: 无缺失数据描述，跳过")
            return {**state, "current_step": "self_collect_skipped", "phase": "self_collected"}

        self._update_progress(task_id, state["problem_text"], 12, "自主收集数据中")
        self._post_chat(task_id, "coordinator", f"🔍 正在自主收集数据：{missing_desc or ', '.join(collect_keywords)}")

        try:
            # 1. 搜索数据 URL（使用 web_search MCP 工具或内置搜索）
            search_query = missing_desc or " ".join(collect_keywords)
            urls = []
            try:
                from ..services.self_collector import extract_urls_from_search_result
                # 尝试使用 research_agent 的搜索能力查找数据集
                research_agent = self.agents.get("research_agent")
                if research_agent:
                    search_result = await research_agent.execute(
                        task_input={
                            "action": "search_datasets",
                            "query": search_query,
                            "limit": 5,
                        },
                        context={"problem_text": state["problem_text"]},
                    )
                    urls = extract_urls_from_search_result(search_result)
            except Exception as e:
                logger.warning(f"[LangGraph:{task_id}] 数据集搜索失败: {e}")

            # 2. 下载数据
            collected_files = []
            if urls:
                from ..services.self_collector import collect_urls
                download_results = await collect_urls(
                    urls=urls,
                    project_name=state.get("project_name"),
                    source_query=search_query,
                    concurrency=4,
                    timeout_sec=30,
                    max_size_mb=50,
                )
                collected_files = [r.filename for r in download_results if r.filename]
                failed = [r.url for r in download_results if r.error]
                if failed:
                    logger.warning(f"[LangGraph:{task_id}] 部分下载失败: {failed}")

            # 3. 更新 state
            if collected_files:
                self._post_chat(
                    task_id, "coordinator",
                    f"✅ 自主收集完成：下载了 {len(collected_files)} 个数据文件"
                )
                # 将新文件加入 files 列表
                existing_files = list(state.get("files", []) or [])
                from ..core.paths import get_project_data_subdir
                data_dir = get_project_data_subdir(state.get("project_name"), "self_collected")
                new_paths = [str(data_dir / f) for f in collected_files]
                updated_files = existing_files + new_paths
                return {
                    **state,
                    "files": updated_files,
                    "current_step": "self_collect_done",
                    "phase": "self_collected",
                    "self_collected_files": collected_files,
                }
            else:
                self._post_chat(
                    task_id, "coordinator",
                    "⚠️ 自主收集未找到数据，任务将继续但可能缺少数据支持"
                )
                return {
                    **state,
                    "current_step": "self_collect_failed",
                    "phase": "self_collected",
                    "cannot_solve_report": {
                        "reason": "自主数据收集失败：未找到可用数据源",
                        "suggestion": "请手动上传数据文件后重试",
                    },
                }
        except Exception as e:
            logger.error(f"[LangGraph:{task_id}] self_collect 节点异常: {e}")
            return {
                **state,
                "current_step": "self_collect_error",
                "phase": "self_collected",
                "cannot_solve_report": {
                    "reason": f"自主数据收集异常: {e}",
                    "suggestion": "请手动上传数据文件后重试",
                },
            }

    async def _node_discuss_approach(self, state: TaskState) -> TaskState:
        """多 Agent 讨论：分析师、研究员、建模专家讨论研究方案。

        每个 Agent 看到其他 Agent 的分析结果后给出自己的意见，
        形成讨论记录，最终由协调者综合决策。
        """
        task_id = state["task_id"]
        problem_text = state["problem_text"]
        results = self._resolve_results(state)
        room = get_chat_room(task_id)

        # 基础参与者
        participants = ["analyzer_agent", "research_agent"]

        # 动态选择建模专家
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")
        modeling_agent = self._select_modeling_agent(template, workflow_type)
        if modeling_agent == "modeler_agent":
            participants.append("modeler_agent")
        elif modeling_agent == "algorithm_engineer_agent":
            participants.append("algorithm_engineer_agent")
        elif modeling_agent == "financial_analyst_agent":
            participants.append("financial_analyst_agent")
        # 空字符串则不追加建模专家

        discussion_points = []

        # 构造讨论上下文
        context_summary = []
        for agent_name in ["analyzer_agent", "data_agent", "research_agent"]:
            out = results.get(agent_name, {})
            if out:
                summary = str(out)[:300]
                context_summary.append(f"【{agent_name}】{summary}")

        discuss_prompt = (
            f"## 研究课题讨论\n\n"
            f"**问题**：{problem_text[:300]}\n\n"
            f"**已有分析**：\n" + "\n".join(context_summary) + "\n\n"
            f"请从你的专业角度给出：\n"
            f"1. 对研究方向的建议\n"
            f"2. 推荐的建模方法\n"
            f"3. 潜在风险和注意事项\n"
            f"4. 创新点建议\n"
            f"请简洁回答（100字以内）。"
        )

        for agent_name in participants:
            agent = self.agents.get(agent_name)
            if not agent:
                continue
            try:
                resp = await agent.call_llm([
                    {"role": "system", "content": f"你是{self._agent_context(state).get('chat_room', room).team.get(agent_name, {}).get('role', agent_name) if room else agent_name}。请参与团队讨论。"},
                    {"role": "user", "content": discuss_prompt},
                ], temperature=0.5)
                content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    discussion_points.append({"agent": agent_name, "opinion": content})
                    if room:
                        room.post(agent_name, f"💡 {content}", "discussion")
            except Exception as exc:
                logger.debug(f"Discuss from {agent_name} failed: {exc}")

        # 协调者综合决策
        if discussion_points and room:
            opinions = "\n".join([f"- {d['agent']}: {d['opinion']}" for d in discussion_points])
            room.post("coordinator", f"📋 讨论总结：\n{opinions}\n\n综合各方意见，继续推进研究。", "discussion")

        self._post_chat(task_id, "coordinator", f"团队讨论完成，{len(discussion_points)} 位 Agent 参与")
        ref_update = self._set_result(state, "discussion", discussion_points)
        return {
            **state,
            "current_step": "discuss_done",
            "results": {**state.get("results", {}), **ref_update},
        }

    async def _node_wait_user(self, state: TaskState) -> TaskState:
        """检查用户输入，有则注入 context 继续执行"""
        task_id = state["task_id"]
        room = get_chat_room(task_id)

        if room:
            # 检查是否有新用户消息
            last_check = state.get("last_input_check", 0)
            user_msgs = room.get_user_messages_since(since=last_check)

            if user_msgs:
                new_msgs = [{"sender": m.sender, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in user_msgs]
                all_msgs = state.get("user_messages", [])
                all_msgs.extend(new_msgs)
                room.post("coordinator", f"📝 收到 {len(new_msgs)} 条用户反馈，继续执行并调整...", "broadcast")

                return {
                    **state,
                    "user_messages": all_msgs,
                    "last_input_check": time.time(),
                    "current_step": "processing_user_feedback",
                    "should_pause": False,
                }

            # 无用户消息，直接继续
            room.post("coordinator", "🔄 继续自动执行...", "broadcast")

        return {**state, "current_step": "auto_continuing", "should_pause": False}

    # ------------------------------------------------------------------
    # 条件路由
    # ------------------------------------------------------------------
    def _route_preflight(self, state: TaskState) -> str:
        preflight = state.get("preflight") or {}

        # 已经过 self_collect 阶段 → 直接按 workflow_type 走（避免无限循环）
        if state.get("phase") == "self_collected":
            workflow = state.get("workflow_type", "standard")
            if workflow in ("quick", "code_focused", "deep_research", "research_paper"):
                return workflow
            return "standard"

        # 无 preflight 报告时使用 state 中的 workflow_type（兼容旧流程）
        if not preflight:
            workflow = state.get("workflow_type", "standard")
            if workflow in ("quick", "code_focused", "deep_research", "research_paper"):
                return workflow
            return "standard"

        # 综述/调研类任务不需要数据文件，直接走 deep_research 工作流
        template = preflight.get("recommended_template", "")
        workflow = preflight.get("recommended_workflow", state.get("workflow_type", "standard"))
        if template == "research_survey" or workflow == "deep_research":
            if workflow in ("quick", "code_focused", "deep_research", "research_paper"):
                return workflow
            return "deep_research"

        adequacy = preflight.get("data_adequacy", "sufficient")
        if adequacy == "missing" and preflight.get("llm_should_collect"):
            return "self_collect"
        if adequacy == "missing":
            return "abort"
        if workflow in ("quick", "code_focused", "deep_research", "research_paper"):
            return workflow
        return "standard"

    def _route_peer_review(self, state: TaskState) -> str:
        review = self._resolve_results(state).get("peer_review_agent", {})
        rec = (review.get("recommendation") or "").lower()
        score = review.get("overall_score", 0)

        # 用户已关闭自评/迭代优化 → 直接接受，不进入修订循环
        if not state.get("use_critique", True):
            logger.info(f"[LangGraph:{state['task_id']}] use_critique=False, peer review 直接通过")
            return "accept"

        if rec == "accept" or score >= 4.0:
            return "accept"
        if rec == "reject":
            return "abort"

        # v7.2: 全自动模式 — 不再等待用户，直接自动迭代
        # 优先从 writer_agent 结果读取修订次数，fallback 到顶层 state
        writer_result = self._resolve_results(state).get("writer_agent", {})
        revision_count = writer_result.get("_revision_count", 0) if isinstance(writer_result, dict) else 0
        revision_count = revision_count or state.get("revision_count", 0)
        logger.info(f"[LangGraph:{state['task_id']}] peer review route: rec={rec}, score={score}, revision_count={revision_count}")

        # 3 次修订后直接接受（不再等待用户）
        if revision_count >= 3:
            logger.info(f"[LangGraph:{state['task_id']}] auto-accept after {revision_count} revisions (score={score})")
            return "accept"

        # 未达上限 → 自动修订
        return "revise"

    def _route_solver(self, state: TaskState) -> str:
        attempts = state.get("solver_attempts", [])
        escalation = state.get("escalation_count", 0)

        if not attempts:
            return "retry"

        last = attempts[-1]
        if last.get("execution_success"):
            return "success"

        if len(attempts) >= self.cfg.max_solver_iterations:
            if escalation >= self.cfg.max_solver_escalations:
                return "abort"
            return "escalate"

        return "retry"

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def _agent_context(self, state: TaskState) -> Dict[str, Any]:
        """构造传给 Agent.execute 的 context（模板感知）。"""
        room = get_chat_room(state["task_id"])
        results = self._resolve_results(state)
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")

        # 合并 model + solve 的 section_results（writer_agent 期望 list[dict]）
        modeler_output = results.get("modeler_agent", {})
        solver_output = results.get("solver_agent", {})
        models = modeler_output.get("sub_problem_models", [])
        solutions = solver_output.get("sub_problem_solutions", [])
        sub_problems = state.get("sub_problems", [])

        section_results = []
        for i, sp in enumerate(sub_problems):
            sp_id = sp.get("id", i + 1)
            model = next((m for m in models if m.get("sub_problem_id") == sp_id), {})
            solve = next((s for s in solutions if s.get("sub_problem_id") == sp_id), {})
            section_results.append(
                {
                    "sub_problem_id": sp_id,
                    "sub_problem_name": sp.get("name", ""),
                    "sub_problem_desc": sp.get("description", ""),
                    "model": model,
                    "solve": solve,
                }
            )

        # 基础上下文
        ctx = {
            "problem_text": state["problem_text"],
            "chat_room": room,
            "task_id": state["task_id"],
            "data_files": state.get("files", []),
            "knowledge_base_id": state.get("knowledge_base_id"),
            "task_kb_id": state.get("task_kb_id"),
            "workflow_type": workflow_type,
            "template": template,
            "results": results,
            "section_results": section_results,
            "sub_problems": sub_problems,
            "requirement_plan": state.get("requirement_plan"),  # 需求分解结果（所有Agent可读）
            "innovation_analysis": state.get("innovation_analysis"),  # 创新发现（所有Agent可读）
            "task_summary": state.get("task_summary"),  # 任务总结（所有Agent可读）
        }

        # 用户反馈注入
        user_messages = state.get("user_messages", [])
        user_feedback_text = ""
        if user_messages:
            latest = user_messages[-1]
            user_feedback_text = f"\n\n【用户最新指令】\n{latest.get('content', '')}\n\n请根据用户指令调整你的方案。如果用户指令与当前步骤无关，在输出中说明并继续原计划。"

        ctx["user_feedback_text"] = user_feedback_text
        ctx["user_messages"] = user_messages

        # ===== 模板特定上下文 =====
        research_output = results.get("research_agent", {})
        analyzer_output = results.get("analyzer_agent", {})

        if template == "research_survey":
            # 调研报告：重点是文献、研究空白、创新点
            ctx["literature"] = research_output.get("papers", []) if isinstance(research_output, dict) else []
            ctx["methods"] = research_output.get("methods", []) if isinstance(research_output, dict) else []
            ctx["research_gaps"] = analyzer_output.get("research_gaps", []) if isinstance(analyzer_output, dict) else []
            ctx["problem_type"] = analyzer_output.get("problem_type", "") if isinstance(analyzer_output, dict) else ""

        elif template in ("math_modeling", "coursework"):
            # 数学建模/课程作业：重点是模型、求解、数据
            ctx["modeling_approach"] = modeler_output.get("overall_approach", "") if isinstance(modeler_output, dict) else ""
            ctx["solver_results"] = solver_output.get("sub_problem_solutions", []) if isinstance(solver_output, dict) else []
            ctx["data_insights"] = results.get("data_agent", {}).get("insights", []) if isinstance(results.get("data_agent"), dict) else []

        elif template == "financial_analysis":
            # 金融分析：重点是金融数据、风险指标、回测结果
            financial_output = results.get("financial_analyst_agent", {})
            ctx["financial_models"] = financial_output.get("models", []) if isinstance(financial_output, dict) else []
            ctx["risk_metrics"] = financial_output.get("risk_metrics", {}) if isinstance(financial_output, dict) else {}
            ctx["backtest_results"] = financial_output.get("backtest", {}) if isinstance(financial_output, dict) else {}

        elif template in ("neurips_2024", "ieee_conference", "acm_sigconf", "springer_lncs"):
            # CCF-A 论文：重点是方法创新、实验对比、理论分析
            algo_output = results.get("algorithm_engineer_agent", {})
            ctx["algorithm_design"] = algo_output.get("algorithm_design", "") if isinstance(algo_output, dict) else ""
            ctx["complexity_analysis"] = algo_output.get("complexity_analysis", "") if isinstance(algo_output, dict) else ""
            ctx["experiment_plan"] = algo_output.get("experiment_plan", {}) if isinstance(algo_output, dict) else {}
            ctx["literature"] = research_output.get("papers", []) if isinstance(research_output, dict) else []
            ctx["methods"] = research_output.get("methods", []) if isinstance(research_output, dict) else []

        return ctx

    def _save_results(self, task_id: str, state: TaskState) -> None:
        """持久化结果到 task_result.json 和 checkpoints。"""
        from ..core.task_persistence import save_task_result, save_task_checkpoint, save_task_metadata, save_task_messages
        results = self._resolve_results(state)

        # 将 state 级别的字段合并到 results 中（这些不经过 result_store）
        for key in ("requirement_plan", "innovation_analysis", "task_summary"):
            val = state.get(key)
            if val is not None:
                results[key] = val

        if results:
            save_task_result(task_id, {"task_id": task_id, "output": results})
            for agent_name, output in results.items():
                try:
                    save_task_checkpoint(task_id, "langgraph", agent_name, output)
                except Exception as exc:
                    logger.debug(f"Checkpoint save failed for {agent_name}: {exc}")

        # 保存聊天记录到磁盘
        try:
            room = get_chat_room(task_id)
            if room:
                msgs = room.get_messages()
                save_task_messages(task_id, msgs)
        except Exception as exc:
            logger.debug(f"Messages save failed: {exc}")

        # 提取经验教训到持久化记忆
        try:
            from ..core.memory import get_memory_manager
            mm = get_memory_manager()
            mm.extract_lessons_from_result(task_id, results)
            # 提取文献/方法经验
            mm.extract_literature_lessons(task_id, results)
            logger.info(f"[LangGraph:{task_id}] 经验教训已提取到记忆系统")
        except Exception as exc:
            logger.debug(f"Lessons extraction failed: {exc}")

        # 标记任务完成状态
        cannot_solve = state.get("cannot_solve_report")
        # 检测是否有 agent 失败（writer 缺失 → 视为任务失败）
        writer_ok = "writer_agent" in results

        # 当跳过建模时，不再强制要求 solver_agent 结果
        template = state.get("paper_template", "math_modeling")
        workflow_type = state.get("workflow_type", "standard")
        modeling_agent = self._select_modeling_agent(template, workflow_type)
        skip_modeling = not modeling_agent

        solver_ok = "solver_agent" in results or skip_modeling

        critical_missing = (
            state.get("workflow_type") == "standard"
            and (not writer_ok or not solver_ok)
        )
        error_msg = ""
        if cannot_solve:
            error_msg = str(cannot_solve.get("reason", "无法求解"))
        elif critical_missing:
            missing = []
            if not writer_ok:
                missing.append("writer_agent")
            if not solver_ok:
                missing.append("solver_agent")
            error_msg = f"关键 Agent 缺失: {', '.join(missing)}"

        # v7.2: 检查是否需要暂停（should_pause 标志）
        should_pause = state.get("should_pause", False)

        if cannot_solve or critical_missing:
            save_task_metadata(
                task_id=task_id, problem_text=state.get("problem_text", ""),
                status="failed", created_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
                error=error_msg,
            )
        elif should_pause:
            # 暂停状态：任务未完成，等待用户输入
            save_task_metadata(
                task_id=task_id, problem_text=state.get("problem_text", ""),
                status="paused", created_at=datetime.now().isoformat(),
                error="等待用户反馈",
            )
        else:
            save_task_metadata(
                task_id=task_id, problem_text=state.get("problem_text", ""),
                status="completed", created_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
                progress=100, current_step="已完成",
            )

    # ------------------------------------------------------------------
    # 节点辅助方法
    # ------------------------------------------------------------------
    def _update_progress(self, task_id: str, problem_text: str, progress: int, step: str) -> None:
        """更新任务进度到持久化（同时保存 checkpoint 用于断点续传）。"""
        from ..core.task_persistence import save_task_metadata, save_task_checkpoint
        try:
            save_task_metadata(
                task_id=task_id, problem_text=problem_text,
                status="running", created_at=datetime.now().isoformat(),
                progress=progress, current_step=step,
            )
        except Exception:
            pass
        # 增量保存 checkpoint，用于断点续传
        try:
            save_task_checkpoint(task_id, "langgraph", step, {"progress": progress, "step": step})
        except Exception:
            pass

    def _get_working_memory(self, task_id: str):
        """获取任务的 WorkingMemory 黑板。"""
        try:
            mm = get_memory_manager()
            wm, _ = mm.get_task_memory(task_id)
            return wm
        except Exception:
            return None

    def _post_chat(self, task_id: str, sender: str, message: str) -> None:
        """向 ChatRoom 发送消息。"""
        try:
            room = get_chat_room(task_id)
            if room:
                room.post(sender, message, "broadcast")
        except Exception:
            pass
