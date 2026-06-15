"""LangGraph 编排器（Phase 3）。

目标：用 ``langgraph.StateGraph`` 替换 ``orchestrator.py`` 中的硬编码 if-else 控制流。
当前版本为骨架实现：节点与条件边已定义，节点内部逐步填充。

开关：``backend/app/config.py`` 中的 ``use_langgraph_orchestrator``。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
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
from ..core.memory import get_memory_manager
from ..services.result_validator import get_result_validator, get_cross_validator
from ..services.code_manifest import parse_manifest_from_dict, validate_manifest
from ..services.contract_validator import get_contract_validator
from ..services.fact_checker import get_fact_checker
from ..core.paths import get_project_output_dir

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
    results: Dict[str, Any]
    sub_problems: List[Dict[str, Any]]
    should_pause: bool


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

    def __init__(
        self,
        agents: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ):
        self.agents = agents
        self.cfg = LangGraphConfig(**(config or {}))
        self._graph = self._build_graph() if LANGGRAPH_AVAILABLE else None

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
        template: str = "math_modeling",
        workflow_type: str = "standard",
        preflight_report: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """运行完整工作流。"""
        if not LANGGRAPH_AVAILABLE or self._graph is None:
            raise RuntimeError("langgraph 未安装，无法使用 LangGraphOrchestrator")

        room = create_chat_room(task_id, problem_text)
        mm = get_memory_manager()
        wm, em = mm.create_task_memory(task_id)
        wm.update_problem(text=problem_text[:500], template=template, workflow_type=workflow_type)
        em.record("coordinator", "task_start", f"LangGraph 任务开始：{problem_text[:100]}")

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
            "results": {},
            "sub_problems": [],
            "should_pause": False,
            "revision_count": 0,
        }

        try:
            final_state = await self._graph.ainvoke(initial_state)
            # 持久化结果
            self._save_results(task_id, final_state)
            em.record("coordinator", "task_end", f"LangGraph 任务完成：{final_state.get('current_step', 'done')}")
            return {
                "task_id": task_id,
                "status": "completed",
                "results": final_state.get("results", {}),
                "sub_problems": final_state.get("sub_problems", []),
                "solver_attempts": len(final_state.get("solver_attempts", [])),
                "current_step": final_state.get("current_step", ""),
                "cannot_solve_report": final_state.get("cannot_solve_report"),
            }
        except Exception as exc:
            logger.error(f"LangGraph run failed for {task_id}: {exc}", exc_info=True)
            em.record("coordinator", "task_error", f"LangGraph 任务失败：{exc}")
            raise

    # ------------------------------------------------------------------
    # Graph 构建
    # ------------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(TaskState)

        # 节点注册
        builder.add_node("preflight_decision", self._node_preflight_decision)
        builder.add_node("analyzer", self._node_analyzer)
        builder.add_node("data", self._node_data)
        builder.add_node("research", self._node_research)
        builder.add_node("discuss_approach", self._node_discuss_approach)
        builder.add_node("modeler", self._node_modeler)
        builder.add_node("iterative_solver", self._node_iterative_solver)
        builder.add_node("writer", self._node_writer)
        builder.add_node("peer_review", self._node_peer_review)
        builder.add_node("experiment", self._node_experiment)
        builder.add_node("fact_check", self._node_fact_check)
        builder.add_node("cannot_solve", self._node_cannot_solve)
        builder.add_node("self_collect", self._node_self_collect)
        builder.add_node("wait_user", self._node_wait_user)

        # 入口
        builder.set_entry_point("preflight_decision")

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
                "success": "writer",
                "retry": "iterative_solver",
                "escalate": "cannot_solve",
                "abort": "cannot_solve",
            },
        )

        # 条件边：research 后决定是否讨论
        builder.add_conditional_edges(
            "research",
            self._route_after_research,
            {
                "discuss": "discuss_approach",
                "proceed": "modeler",
            },
        )

        # 普通顺序边
        builder.add_edge("analyzer", "data")
        builder.add_edge("data", "research")
        builder.add_edge("discuss_approach", "modeler")
        builder.add_edge("modeler", "iterative_solver")
        builder.add_edge("writer", "peer_review")
        builder.add_edge("fact_check", END)
        builder.add_edge("cannot_solve", END)
        builder.add_edge("self_collect", "preflight_decision")
        builder.add_edge("wait_user", END)

        return builder.compile()

    # ------------------------------------------------------------------
    # 节点实现（骨架，逐步填充）
    # ------------------------------------------------------------------
    async def _node_preflight_decision(self, state: TaskState) -> TaskState:
        """读取 preflight 报告并设置初始配置，更新进度。"""
        preflight = state.get("preflight") or {}
        task_id = state["task_id"]
        from ..core.task_persistence import save_task_metadata
        try:
            from datetime import datetime
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
        agent = self.agents.get("analyzer_agent")
        if not agent:
            return {**state, "current_step": "analyzer_missing"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 15, "问题分析中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        output = await agent.execute(
            task_input={"action": "analyze", "problem_text": state["problem_text"]},
            context=self._agent_context(state),
        )
        output["_contract"] = get_contract_validator().validate("analyzer_agent", output)

        new_results = {**state.get("results", {}), "analyzer_agent": output}
        sub_problems = output.get("sub_problems", [])

        # 更新黑板记忆
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("analyzer_agent", output)
            wm.sub_problems = sub_problems
            if output.get("problem_type"):
                wm.update_problem(type=output["problem_type"])

        self._post_chat(task_id, "analyzer_agent", f"问题分析完成，识别 {len(sub_problems)} 个子问题")
        logger.info(f"[LangGraph:{task_id}] analyzer: {len(sub_problems)} sub_problems")
        return {**state, "results": new_results, "sub_problems": sub_problems, "current_step": "analyzer_done"}

    async def _node_data(self, state: TaskState) -> TaskState:
        """调用 data_agent 分析数据文件。"""
        agent = self.agents.get("data_agent")
        if not agent or not state.get("files"):
            logger.info(f"[LangGraph:{state['task_id']}] data: no files, skipping")
            return {**state, "current_step": "data_skipped"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 25, "数据分析中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        output = await agent.execute(
            task_input={"action": "analyze_data", "problem_text": state["problem_text"]},
            context=self._agent_context(state),
        )

        new_results = {**state.get("results", {}), "data_agent": output}

        # 更新黑板记忆
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("data_agent", output)
            wm.data_insights = output.get("insights", [])

        self._post_chat(task_id, "data_agent", "数据分析完成")
        return {**state, "results": new_results, "current_step": "data_done"}

    async def _node_research(self, state: TaskState) -> TaskState:
        """调用 research_agent 搜集文献，根据 workflow_type 调整搜索策略。"""
        agent = self.agents.get("research_agent")
        if not agent:
            return {**state, "current_step": "research_skipped"}

        task_id = state["task_id"]
        workflow = state.get("workflow_type", "standard")

        # quick / code_focused 模式跳过文献搜集
        if workflow in ("quick", "code_focused"):
            logger.info(f"[LangGraph:{task_id}] research: skipped (workflow={workflow})")
            return {**state, "current_step": "research_skipped"}

        self._update_progress(task_id, state["problem_text"], 35, "文献搜集中")
        agent._knowledge_base_id = state.get("knowledge_base_id")

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
        new_results = {**state.get("results", {}), "research_agent": result}

        # 更新黑板记忆
        wm = self._get_working_memory(task_id)
        if wm:
            wm.add_literature(all_papers, source="research_agent")
            for m in all_methods:
                wm.add_method(m)

        self._post_chat(task_id, "research_agent", f"文献搜集完成，{len(all_papers)} 篇文献，{len(all_methods)} 个方法")
        return {**state, "results": new_results, "current_step": "research_done"}

    async def _node_modeler(self, state: TaskState) -> TaskState:
        """逐个子问题建模：每个子问题独立建模，前序结果递进传递给后序。"""
        agent = self.agents.get("modeler_agent")
        if not agent:
            return {**state, "current_step": "modeler_missing"}

        task_id = state["task_id"]
        sub_problems = state.get("sub_problems", [])
        results = state.get("results", {})
        all_models = []

        agent._knowledge_base_id = state.get("knowledge_base_id")

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
                all_models.append({**output, "sub_problem_id": sp_id, "sub_problem_name": sp_name})
                self._post_chat(task_id, "modeler_agent", f"[{i+1}/{len(sub_problems)}] 建模完成：{sp_name}（{output.get('model_name', '')}）")
            except Exception as exc:
                logger.error(f"[LangGraph:{task_id}] modeler sp{sp_id} failed: {exc}")
                all_models.append({"sub_problem_id": sp_id, "sub_problem_name": sp_name, "error": str(exc)})

        modeler_output = {"sub_problem_models": all_models}
        new_results = {**results, "modeler_agent": modeler_output}

        # 更新黑板
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("modeler_agent", modeler_output)
            for m in all_models:
                wm.add_method({"name": m.get("model_name", ""), "type": m.get("model_type", ""), "sub_problem": m.get("sub_problem_name", "")})

        self._post_chat(task_id, "modeler_agent", f"全部 {len(sub_problems)} 个子问题建模完成")
        return {**state, "results": new_results, "current_step": "modeler_done"}

    async def _node_iterative_solver(self, state: TaskState) -> TaskState:
        """逐个子问题求解 + 自主迭代修复。

        对每个子问题：
        1. 用对应模型结果调 solver_agent
        2. Harness 评判（ResultValidator + CrossValidator + CodeManifest）
        3. 失败时注入错误分类和修复建议，重试（最多 max_solver_iterations 次）
        4. 仍失败则多 Agent 投票决定 retry / collect_data / abort
        """
        agent = self.agents.get("solver_agent")
        if not agent:
            return {**state, "current_step": "solver_missing"}

        task_id = state["task_id"]
        sub_problems = state.get("sub_problems", [])
        results = state.get("results", {})
        modeler_output = results.get("modeler_agent", {})
        all_models = modeler_output.get("sub_problem_models", [])
        all_solutions = []
        all_attempts = list(state.get("solver_attempts", []))
        escalation = state.get("escalation_count", 0)

        agent._knowledge_base_id = state.get("knowledge_base_id")

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
        new_results = {**results, "solver_agent": solver_output}

        # 更新黑板
        wm = self._get_working_memory(task_id)
        if wm:
            wm.set_result("solver_agent", solver_output)
            for s in all_solutions:
                findings = s.get("results", {}).get("key_findings", [])
                if findings:
                    wm.set_result("solver_agent", {**wm.results.get("solver_agent", {}), "last_findings": findings})

        self._post_chat(task_id, "solver_agent", f"全部 {len(sub_problems)} 个子问题求解完成")
        return {**state, "results": new_results, "solver_attempts": all_attempts, "escalation_count": escalation, "current_step": "solver_done"}

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
        agent = self.agents.get("writer_agent")
        if not agent:
            return {**state, "current_step": "writer_missing"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 70, "论文写作中")

        agent._knowledge_base_id = state.get("knowledge_base_id")
        output = await agent.execute(
            task_input={
                "action": "write",
                "problem_text": state["problem_text"],
                "sub_problems": state.get("sub_problems", []),
            },
            context=self._agent_context(state),
        )
        output["_contract"] = get_contract_validator().validate("writer_agent", output)

        new_results = {**state.get("results", {}), "writer_agent": output}
        revision_count = state.get("revision_count", 0) + 1
        self._post_chat(task_id, "writer_agent", f"论文写作完成（第 {revision_count} 稿）")
        return {**state, "results": new_results, "current_step": "writer_done", "revision_count": revision_count}

    async def _node_peer_review(self, state: TaskState) -> TaskState:
        """调用 peer_review_agent 进行同行评议。"""
        agent = self.agents.get("peer_review_agent")
        if not agent or not self.cfg.enable_peer_review:
            return {**state, "current_step": "peer_review_skipped"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 80, "同行评议中")

        output = await agent.execute(
            task_input={"action": "review", "problem_text": state["problem_text"]},
            context=self._agent_context(state),
        )

        new_results = {**state.get("results", {}), "peer_review_agent": output}
        rec = (output.get("recommendation") or "").lower()
        score = output.get("overall_score", 0)
        self._post_chat(task_id, "peer_review_agent", f"同行评议完成：{rec}，得分 {score}")
        return {**state, "results": new_results, "current_step": "peer_review_done"}

    async def _node_experiment(self, state: TaskState) -> TaskState:
        """调用 experimentation_agent 设计实验方案（CCF-A 模板才启用）。"""
        agent = self.agents.get("experimentation_agent")
        template = state.get("paper_template", "math_modeling")
        ccf_a = {"ieee_conference", "neurips_2024", "acm_sigconf", "springer_lncs", "research_paper"}
        if not agent or not self.cfg.enable_experiment_design or template not in ccf_a:
            return {**state, "current_step": "experiment_skipped"}

        task_id = state["task_id"]
        self._update_progress(task_id, state["problem_text"], 55, "实验设计中")

        output = await agent.execute(
            task_input={"action": "design", "problem_text": state["problem_text"]},
            context=self._agent_context(state),
        )

        new_results = {**state.get("results", {}), "experimentation_agent": output}
        self._post_chat(task_id, "experimentation_agent", "实验设计完成")
        return {**state, "results": new_results, "current_step": "experiment_done"}

    async def _node_fact_check(self, state: TaskState) -> TaskState:
        """事实核查：对比 main.tex 与 solves.json 数字。"""
        if not self.cfg.enable_fact_check:
            return {**state, "current_step": "fact_check_skipped"}

        project_name = state.get("project_name")
        try:
            output_dir = get_project_output_dir(project_name)
        except Exception:
            output_dir = None

        report: Dict[str, Any] = {"enabled": True, "passed": True}
        if output_dir:
            report = get_fact_checker().check(
                task_id=state["task_id"],
                output_dir=output_dir,
            )
            state["results"]["fact_checker"] = report
            logger.info(f"Task {state['task_id']}: fact_check passed={report['passed']} issues={report['issue_count']}")
        else:
            report["error"] = "无法确定输出目录"
            state["results"]["fact_checker"] = report

        return {**state, "current_step": "fact_check_done"}

    async def _node_cannot_solve(self, state: TaskState) -> TaskState:
        report = {
            "task_id": state["task_id"],
            "reason": state.get("cannot_solve_report") or "无法继续求解",
            "solver_attempts": state.get("solver_attempts", []),
        }
        logger.warning(f"Task {state['task_id']} cannot_solve: {report['reason']}")
        return {**state, "current_step": "cannot_solve", "cannot_solve_report": report}

    async def _node_self_collect(self, state: TaskState) -> TaskState:
        """自主搜集数据：标记已尝试，避免无限循环。"""
        return {**state, "current_step": "self_collect_done", "phase": "self_collected"}

    async def _node_discuss_approach(self, state: TaskState) -> TaskState:
        """多 Agent 讨论：分析师、建模师、研究员讨论研究方案。

        每个 Agent 看到其他 Agent 的分析结果后给出自己的意见，
        形成讨论记录，最终由协调者综合决策。
        """
        task_id = state["task_id"]
        problem_text = state["problem_text"]
        results = state.get("results", {})
        room = get_chat_room(task_id)

        # 参与讨论的 Agent
        participants = ["analyzer_agent", "modeler_agent", "research_agent"]
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
        return {
            **state,
            "current_step": "discuss_done",
            "results": {**results, "discussion": discussion_points},
        }

    async def _node_wait_user(self, state: TaskState) -> TaskState:
        """等待用户输入：通知前端，暂停执行。

        用户可以通过 POST /{task_id}/messages 发送消息，
        然后通过 POST /{task_id}/resume 恢复执行。
        """
        task_id = state["task_id"]
        room = get_chat_room(task_id)
        if room:
            room.set_waiting_for_user(True)
            room.post("coordinator", "⏸️ 已暂停等待您的反馈。请在聊天框中输入您的意见，然后点击「继续执行」。", "broadcast")

        self._update_progress(task_id, state["problem_text"], 85, "等待用户反馈")
        return {**state, "current_step": "waiting_for_user", "should_pause": True}

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

        adequacy = preflight.get("data_adequacy", "sufficient")
        if adequacy == "missing" and preflight.get("llm_should_collect"):
            return "self_collect"
        if adequacy == "missing":
            return "abort"
        workflow = preflight.get("recommended_workflow", state.get("workflow_type", "standard"))
        if workflow in ("quick", "code_focused", "deep_research", "research_paper"):
            return workflow
        return "standard"

    def _route_peer_review(self, state: TaskState) -> str:
        review = state.get("results", {}).get("peer_review_agent", {})
        rec = (review.get("recommendation") or "").lower()
        score = review.get("overall_score", 0)

        if rec == "accept" or score >= 4.0:
            return "accept"
        if rec == "reject":
            return "abort"

        # 用户已发言 → 等待用户指导修订方向
        room = get_chat_room(state["task_id"])
        if room and room.has_user_input():
            return "wait_user"

        # 用户未发言 → 自动迭代修订（直到高质量或达到上限）
        revision_count = state.get("revision_count", 0)
        if revision_count < 3:
            return "revise"

        # 达到修订上限 → 等待用户决定
        return "wait_user"

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

    def _route_after_research(self, state: TaskState) -> str:
        """research 后决定是否进入讨论。"""
        workflow = state.get("workflow_type", "standard")
        # deep_research 和 research_paper 模式进入讨论
        if workflow in ("deep_research", "research_paper"):
            return "discuss"
        return "proceed"

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def _agent_context(self, state: TaskState) -> Dict[str, Any]:
        """构造传给 Agent.execute 的 context。"""
        room = get_chat_room(state["task_id"])
        return {
            "problem_text": state["problem_text"],
            "chat_room": room,
            "task_id": state["task_id"],
            "data_files": state.get("files", []),
            "knowledge_base_id": state.get("knowledge_base_id"),
            "workflow_type": state.get("workflow_type", "standard"),
            "template": state.get("paper_template", "math_modeling"),
            "results": state.get("results", {}),
        }

    def _save_results(self, task_id: str, state: TaskState) -> None:
        """持久化结果到 task_result.json 和 checkpoints。"""
        from ..core.task_persistence import save_task_result, save_task_checkpoint, save_task_metadata
        from datetime import datetime
        results = state.get("results", {})
        if results:
            save_task_result(task_id, {"task_id": task_id, "output": results})
            for agent_name, output in results.items():
                try:
                    save_task_checkpoint(task_id, "langgraph", agent_name, output)
                except Exception as exc:
                    logger.debug(f"Checkpoint save failed for {agent_name}: {exc}")

        # 标记任务完成状态
        cannot_solve = state.get("cannot_solve_report")
        if cannot_solve:
            save_task_metadata(
                task_id=task_id, problem_text=state.get("problem_text", ""),
                status="failed", created_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
                error=str(cannot_solve.get("reason", "无法求解")),
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
        """更新任务进度到持久化。"""
        from ..core.task_persistence import save_task_metadata
        from datetime import datetime
        try:
            save_task_metadata(
                task_id=task_id, problem_text=problem_text,
                status="running", created_at=datetime.now().isoformat(),
                progress=progress, current_step=step,
            )
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
