"""主编排器 - 两阶段工作流

阶段1（分析阶段，可编辑）：
  analyzer → data → research → 暂停，等待用户确认子问题

阶段2（建模求解，用户确认后自动执行）：
  modeler+solver（一次性处理所有子问题）→ writer → 完成
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from .base import BaseAgent, AgentFactory
from ..config import get_settings
from ..schemas import TaskStatus, TaskStep, TaskStatusResponse
from ..core.chat_room import ChatRoom, create_chat_room, get_chat_room
from ..core.paths import get_project_output_dir
from ..core.memory import get_memory_manager, WorkingMemory

# Phase 2：导入新 Agent 以触发 @AgentFactory.register 装饰器。
# 不直接使用，仅保证 Orchestrator 加载时新 Agent 已注册。
from . import experimentation_agent  # noqa: F401
from . import peer_review_agent  # noqa: F401
from . import requirement_decomposer  # noqa: F401
from . import summary_agent  # noqa: F401
from . import innovation_agent  # noqa: F401

# Phase 3：LangGraph 编排器（按需导入，未安装也不阻断旧流程）
from .langgraph_orchestrator import LangGraphOrchestrator, LANGGRAPH_AVAILABLE

logger = logging.getLogger(__name__)


class Orchestrator:
    """主编排器 - 管理两阶段多Agent工作流"""

    def __init__(self, agents: Dict[str, BaseAgent], config: Optional[Dict[str, Any]] = None):
        self.agents = agents
        self.config = config or {}
        self.current_task_id: Optional[str] = None
        self.task_history: Dict[str, List[TaskStep]] = {}

        # 任务状态存储（支持暂停/恢复）
        self._task_phase: Dict[str, str] = {}      # "phase1" / "phase2"
        self._task_results: Dict[str, Dict] = {}   # 阶段1的结果
        self._task_sub_problems: Dict[str, List] = {}  # 用户确认后的子问题列表

        # 暂停/恢复状态
        self._task_paused: Dict[str, bool] = {}      # 暂停标志
        self._task_paused_at: Dict[str, str] = {}    # 暂停在哪个Agent
        self._task_pause_data: Dict[str, Dict] = {}  # 暂停时各Agent的输出（用户可编辑）

        # 任务模板类型
        self._task_templates: Dict[str, str] = {}    # task_id -> template (math_modeling/coursework/financial_analysis)

        # 工作流类型
        self._task_workflows: Dict[str, str] = {}    # task_id -> workflow_type (standard/quick/deep_research/code_focused)

        # Phase 3：LangGraph 编排器懒加载
        self._langgraph_orchestrator: Optional[LangGraphOrchestrator] = None
        self._use_langgraph = get_settings().use_langgraph_orchestrator and LANGGRAPH_AVAILABLE

    def _get_langgraph_orchestrator(self) -> Optional[LangGraphOrchestrator]:
        if self._langgraph_orchestrator is None and self._use_langgraph:
            self._langgraph_orchestrator = LangGraphOrchestrator(agents=self.agents)
        return self._langgraph_orchestrator

    def is_paused(self, task_id: str) -> bool:
        return self._task_paused.get(task_id, False)

    def resume_task(self, task_id: str) -> None:
        self._task_paused[task_id] = False

    def get_pause_data(self, task_id: str) -> Dict:
        return self._task_pause_data.get(task_id, {})

    def update_pause_data(self, task_id: str, key: str, value: Any) -> None:
        if task_id not in self._task_pause_data:
            self._task_pause_data[task_id] = {}
        self._task_pause_data[task_id][key] = value

    def _check_pause(self, task_id: str) -> bool:
        """检查是否需要暂停，是则抛出特殊异常让调用方处理"""
        if self._task_paused.get(task_id, False):
            from .base import PausedException
            raise PausedException(task_id, self._task_paused_at.get(task_id, ""))
        return False

    async def execute_phase1(
        self,
        task_id: str,
        problem_text: str,
        data_files: Optional[List[str]] = None,
        project_name: Optional[str] = None,
        knowledge_base_id: Optional[str] = None,
        template: str = "math_modeling",
        workflow_type: str = "standard",
    ) -> Dict[str, Any]:
        """阶段1：分析 + 数据 + 文献，结束后暂停等待用户确认"""
        logger.info(f"Orchestrator Phase1 for task {task_id} (project={project_name}, kb={knowledge_base_id}, workflow={workflow_type})")
        room = create_chat_room(task_id, problem_text)
        self.task_history[task_id] = []
        self._task_phase[task_id] = "phase1"
        self._task_paused[task_id] = False
        self._task_pause_data[task_id] = {}
        self._current_project_name = project_name
        self._task_templates[task_id] = template
        self._task_workflows[task_id] = workflow_type

        # ===== 初始化记忆系统 =====
        mm = get_memory_manager()
        wm, em = mm.create_task_memory(task_id)
        wm.update_problem(text=problem_text[:500], template=template, workflow_type=workflow_type)
        em.record("coordinator", "task_start", f"任务开始：{problem_text[:100]}")

        context_base = {
            "problem_text": problem_text,
            "chat_room": room,
            "task_id": task_id,
            "data_files": data_files or [],
            "has_data": bool(data_files),
            "knowledge_base_id": knowledge_base_id,
            "workflow_type": workflow_type,
            "template": template,
            "working_memory": wm,
        }
        all_results: Dict[str, Any] = {}

        # 根据工作流类型调整 phase1 步骤
        setup_steps = [
            ("analyzer_agent", "analyze", "问题分析"),
            ("data_agent", "analyze_data", "数据分析"),
        ]
        if workflow_type == "quick":
            # 快速模式：跳过文献搜集
            room.post("coordinator", "⚡ 快速模式：跳过文献搜集，直接进入分析...", "broadcast")
        elif workflow_type == "deep_research":
            # 深度研究模式：强化文献搜集（多角度搜索）
            setup_steps.extend([
                ("research_agent", "search", "综合文献搜集"),
                ("research_agent", "search_background", "背景与趋势搜索"),
                ("research_agent", "search_methods", "方法与模型搜索"),
            ])
            room.post("coordinator", "🔬 深度研究模式：启动多轮文献搜集...", "broadcast")
        elif workflow_type == "code_focused":
            # 代码聚焦模式：跳过文献搜集，重点在模型构建与求解
            room.post("coordinator", "💻 代码聚焦模式：跳过文献搜集，直接进入建模与编程...", "broadcast")
        else:
            # standard：常规文献搜集
            setup_steps.append(("research_agent", "search", "文献搜集"))

        for agent_name, action, label in setup_steps:
            self._check_pause(task_id)
            step_id = f"phase1_{agent_name}"
            task_step = TaskStep(
                step_id=step_id,
                agent_name=agent_name,
                status=TaskStatus.RUNNING,
                started_at=datetime.now(),
            )
            self.task_history[task_id].append(task_step)
            room.post("coordinator", f"开始 {label} ...", "broadcast")

            agent = self.agents.get(agent_name)
            if not agent:
                task_step.status = TaskStatus.FAILED
                task_step.error = f"Agent {agent_name} not found"
                continue

            agent._knowledge_base_id = context_base.get("knowledge_base_id")
            try:
                output = await agent.execute(
                    task_input={"action": action, "problem_text": problem_text},
                    context={**context_base, "results": all_results},
                )
                # 保存暂停数据供用户编辑
                self._task_pause_data[task_id][agent_name] = output
                task_step.output_data = {agent_name: output}
                task_step.status = TaskStatus.COMPLETED
                all_results[agent_name] = output

                # ===== 更新黑板记忆 =====
                wm.set_result(agent_name, output)
                if agent_name == "analyzer_agent":
                    wm.sub_problems = output.get("sub_problems", [])
                    if output.get("problem_type"):
                        wm.update_problem(type=output["problem_type"])
                    if output.get("difficulty"):
                        wm.update_problem(difficulty=output["difficulty"])
                    em.record(agent_name, "analysis_complete", f"问题分析完成，识别 {len(wm.sub_problems)} 个子问题")
                elif agent_name == "data_agent":
                    wm.data_insights = output.get("insights", [])
                    em.record(agent_name, "data_complete", f"数据分析完成，{len(wm.data_insights)} 个洞察")
                elif agent_name == "research_agent":
                    papers = output.get("papers", [])
                    methods = output.get("methods", [])
                    wm.add_literature(papers, source="research_agent")
                    for m in methods:
                        wm.add_method(m)
                    em.record(agent_name, "research_complete", f"文献搜集完成，{len(papers)} 篇文献，{len(methods)} 个方法")

                self._post_agent_result(room, agent_name, label, output)
                room.post(agent_name, f"{label} 完成！", "broadcast")
            except Exception as e:
                logger.error(f"{label} failed: {e}")
                task_step.status = TaskStatus.FAILED
                task_step.error = str(e)
            task_step.completed_at = datetime.now()

        # 阶段1完成，保存结果，通知前端等待确认
        self._task_results[task_id] = all_results
        sub_problems = all_results.get("analyzer_agent", {}).get("sub_problems", [])
        self._task_sub_problems[task_id] = sub_problems

        room.post("coordinator", f"📋 阶段1完成！已识别 {len(sub_problems)} 个子问题，请确认后继续。", "broadcast")

        return {
            "task_id": task_id,
            "phase": "phase1_completed",
            "sub_problems": sub_problems,
            "analysis_result": all_results.get("analyzer_agent", {}),
            "data_result": all_results.get("data_agent", {}),
            "research_result": all_results.get("research_agent", {}),
            "waiting_confirmation": True,
            "message": f"已识别 {len(sub_problems)} 个子问题，请在【子问题列表】中确认或修正后，点击「开始建模」继续",
        }

    async def execute_phase2(
        self,
        task_id: str,
        problem_text: str,
        sub_problems: List[Dict[str, Any]],
        data_files: Optional[List[str]] = None,
        mode: str = "batch",
        project_name: Optional[str] = None,
        knowledge_base_id: Optional[str] = None,
        template: str = "math_modeling",
        workflow_type: str = "standard",
        experimentation_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """阶段2：建模 + 求解 → 论文
        mode: "batch"       一次性建模/求解所有子问题（默认）
              "sequential"  逐个建模+求解交替，前序结果递进到后序（完整做完一问再做下一问）
        """
        logger.info(f"Orchestrator Phase2 for task {task_id}, {len(sub_problems)} sub-problems, mode={mode}, workflow={workflow_type}")
        room = get_chat_room(task_id) or create_chat_room(task_id, problem_text)
        self._task_phase[task_id] = "phase2"
        self._task_paused[task_id] = False
        if task_id not in self._task_pause_data:
            self._task_pause_data[task_id] = {}
        self._current_project_name = project_name
        self._task_templates[task_id] = template
        self._task_workflows[task_id] = workflow_type

        # ====== 逐个交替模式：建模+求解交替进行 ======
        if mode == "sequential":
            return await self._execute_phase2_sequential(
                task_id, problem_text, sub_problems, data_files,
                project_name=project_name, knowledge_base_id=knowledge_base_id,
                workflow_type=workflow_type, experimentation_plan=experimentation_plan,
            )

        # ====== 批量模式（原有逻辑）======
        return await self._execute_phase2_batch(
            task_id, problem_text, sub_problems, data_files,
            project_name=project_name, knowledge_base_id=knowledge_base_id,
            workflow_type=workflow_type, experimentation_plan=experimentation_plan,
        )

    async def _execute_phase2_batch(
        self,
        task_id: str,
        problem_text: str,
        sub_problems: List[Dict[str, Any]],
        data_files: Optional[List[str]],
        project_name: Optional[str] = None,
        knowledge_base_id: Optional[str] = None,
        workflow_type: str = "standard",
        experimentation_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """批量模式：先全部建模，再全部求解，最后写论文"""
        room = get_chat_room(task_id) or create_chat_room(task_id, problem_text)

        # ===== 加载/创建记忆 =====
        mm = get_memory_manager()
        if not mm.get_working(task_id):
            mm.create_task_memory(task_id)
        wm = mm.get_working(task_id)
        em = mm.get_episodic(task_id)
        wm.sub_problems = sub_problems
        wm.update_problem(text=problem_text[:500])

        phase1_results = self._task_pause_data.get(task_id, {}).get("phase1_edited", {})
        if not phase1_results:
            phase1_results = self._task_results.get(task_id, {})
        all_results = dict(phase1_results)
        all_results["sub_problems"] = sub_problems

        context_base = {
            "problem_text": problem_text,
            "chat_room": room,
            "task_id": task_id,
            "data_files": data_files or [],
            "has_data": bool(data_files),
            "knowledge_base_id": knowledge_base_id,
            "template": self._task_templates.get(task_id, "math_modeling"),
            "working_memory": wm,
            "experimentation_plan": experimentation_plan or {},
        }

        section_results: List[Dict[str, Any]] = []

        # 建模阶段
        room.post("coordinator", f"开始批量建模（{len(sub_problems)}个子问题）...", "broadcast")
        self._check_pause(task_id)

        step_id = "phase2_modeler"
        task_step = TaskStep(step_id=step_id, agent_name="modeler_agent", status=TaskStatus.RUNNING, started_at=datetime.now())
        self.task_history[task_id].append(task_step)

        agent = self.agents.get("modeler_agent")
        agent._knowledge_base_id = context_base.get("knowledge_base_id")
        try:
            model_output = await agent.execute(
                task_input={"action": "build_all_models", "problem_text": problem_text},
                context={
                    **context_base, "results": all_results, "sub_problems": sub_problems,
                    "total_sub_problems": len(sub_problems),
                    "analyzer_result": phase1_results.get("analyzer_agent", {}),
                    "data_result": phase1_results.get("data_agent", {}),
                    "research_result": phase1_results.get("research_agent", {}),
                },
            )
            self._task_pause_data[task_id]["modeler_agent"] = model_output
            self._task_pause_data[task_id]["section_results_template"] = self._build_section_results_template(model_output, sub_problems)

            # 更新黑板：模型结果
            wm.set_result("modeler_agent", model_output)
            for m in model_output.get("sub_problem_models", []):
                wm.add_method({
                    "name": m.get("model_name", ""),
                    "type": m.get("model_type", ""),
                    "sub_problem": m.get("sub_problem_name", ""),
                })
            em.record("modeler_agent", "modeling_complete", f"建模完成，{len(model_output.get('sub_problem_models', []))} 个模型")

            room.post("coordinator", "建模完成，进入求解阶段...", "broadcast")
            self._check_pause(task_id)

            task_step.output_data = {"modeler_agent": model_output}
            task_step.status = TaskStatus.COMPLETED
            all_results["modeler_agent"] = model_output

            models = model_output.get("sub_problem_models", [])
            for m in models:
                section_results.append({
                    "sub_problem_id": m.get("sub_problem_id"),
                    "sub_problem_name": m.get("sub_problem_name"),
                    "sub_problem_desc": m.get("sub_problem_desc"),
                    "model": m, "solve": {},
                })
            existing_ids = {sr.get("sub_problem_id") for sr in section_results}
            for i, sp in enumerate(sub_problems):
                sp_id = sp.get("id", i + 1)
                if sp_id not in existing_ids:
                    section_results.append({
                        "sub_problem_id": sp_id,
                        "sub_problem_name": sp.get("name", f"子问题{sp_id}"),
                        "sub_problem_desc": sp.get("description", ""),
                        "model": {"model_type": "optimization", "model_name": sp.get("suggested_method", "数学模型"), "objective_function": "待建模", "algorithm": {"name": "待确定"}},
                        "solve": {},
                    })
            room.post("modeler_agent", f"批量建模完成！共{len(section_results)}个模型", "broadcast")
        except Exception as e:
            logger.error(f"Batch modeler failed: {e}")
            task_step.status = TaskStatus.FAILED
            task_step.error = str(e)
            all_results["modeler_agent"] = {"error": str(e)}
        task_step.completed_at = datetime.now()

        self._check_pause(task_id)

        # 求解阶段
        room.post("coordinator", f"开始批量求解（{len(sub_problems)}个子问题）...", "broadcast")
        self._check_pause(task_id)

        step_id = "phase2_solver"
        task_step = TaskStep(step_id=step_id, agent_name="solver_agent", status=TaskStatus.RUNNING, started_at=datetime.now())
        self.task_history[task_id].append(task_step)

        edited_section = self._task_pause_data.get(task_id, {}).get("section_results_edited", section_results)

        agent = self.agents.get("solver_agent")
        agent._knowledge_base_id = context_base.get("knowledge_base_id")
        try:
            solve_output = await agent.execute(
                task_input={"action": "solve_all", "problem_text": problem_text},
                context={
                    **context_base, "results": all_results, "sub_problems": sub_problems,
                    "section_results": edited_section, "total_sub_problems": len(sub_problems),
                    "data_result": phase1_results.get("data_agent", {}),
                    "research_result": phase1_results.get("research_agent", {}),
                    "project_name": project_name,
                },
            )
            self._task_pause_data[task_id]["solver_agent"] = solve_output

            # 更新黑板：求解结果
            wm.set_result("solver_agent", solve_output)
            for s in solve_output.get("sub_problem_solutions", []):
                findings = s.get("results", {}).get("key_findings", [])
                if findings:
                    em.record("solver_agent", "solving_complete", f"{s.get('sub_problem_name', '')}: {'; '.join(str(f) for f in findings[:2])}")
            em.record("solver_agent", "solving_complete", f"求解完成，{len(solve_output.get('sub_problem_solutions', []))} 个子问题")

            self._check_pause(task_id)

            task_step.output_data = {"solver_agent": solve_output}
            task_step.status = TaskStatus.COMPLETED
            all_results["solver_agent"] = solve_output

            solves = solve_output.get("sub_problem_solutions", [])
            solve_map = {s.get("sub_problem_id"): s for s in solves}
            for sr in edited_section:
                sp_id = sr.get("sub_problem_id")
                if sp_id in solve_map:
                    sr["solve"] = solve_map[sp_id]

            room.post("solver_agent", "批量求解完成！", "broadcast")
        except Exception as e:
            logger.error(f"Batch solver failed: {e}")
            task_step.status = TaskStatus.FAILED
            task_step.error = str(e)
            all_results["solver_agent"] = {"error": str(e)}
        task_step.completed_at = datetime.now()

        return await self._write_paper_and_finish(task_id, problem_text, sub_problems, edited_section, all_results, phase1_results, context_base, project_name=project_name, workflow_type=workflow_type)

    async def _execute_phase2_sequential(
        self,
        task_id: str,
        problem_text: str,
        sub_problems: List[Dict[str, Any]],
        data_files: Optional[List[str]],
        project_name: Optional[str] = None,
        knowledge_base_id: Optional[str] = None,
        workflow_type: str = "standard",
        experimentation_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        逐个交替模式：对每个子问题，先建模，再求解，
        完成后才进入下一个子问题——完整做完一问再做下一问。
        前序建模和求解结果会递进传递给后序。
        """
        room = get_chat_room(task_id) or create_chat_room(task_id, problem_text)

        # ===== 加载/创建记忆 =====
        mm = get_memory_manager()
        if not mm.get_working(task_id):
            mm.create_task_memory(task_id)
        wm = mm.get_working(task_id)
        em = mm.get_episodic(task_id)
        wm.sub_problems = sub_problems
        wm.update_problem(text=problem_text[:500])

        phase1_results = self._task_pause_data.get(task_id, {}).get("phase1_edited", {})
        if not phase1_results:
            phase1_results = self._task_results.get(task_id, {})
        all_results = dict(phase1_results)
        all_results["sub_problems"] = sub_problems

        context_base = {
            "problem_text": problem_text,
            "chat_room": room,
            "task_id": task_id,
            "data_files": data_files or [],
            "has_data": bool(data_files),
            "knowledge_base_id": knowledge_base_id,
            "template": self._task_templates.get(task_id, "math_modeling"),
            "working_memory": wm,
            "experimentation_plan": experimentation_plan or {},
        }

        section_results: List[Dict[str, Any]] = []
        modeler_agent = self.agents.get("modeler_agent")
        solver_agent = self.agents.get("solver_agent")

        # 阶段总步骤：建模1+求解1 + 建模2+求解2 + ... + 写论文
        total_steps = len(sub_problems) * 2 + 1
        current_step_num = 0

        # 追踪已完成的建模/求解结果（用于递进传递）
        completed_models: List[Dict] = []   # 前序子问题的模型
        completed_solutions: List[Dict] = []  # 前序子问题的求解结果

        for i, sp in enumerate(sub_problems):
            sp_id = sp.get("id", i + 1)
            sp_name = sp.get("name", sp.get("description", f"子问题{sp_id}"))[:80]
            sp_desc = sp.get("description", "")
            suggested_method = sp.get("suggested_method", sp.get("approach", ""))

            # ====== 建模（当前子问题）======
            current_step_num += 1
            progress_percentage = int(current_step_num / total_steps * 100)
            room.post("coordinator", f"[{i+1}/{len(sub_problems)}] 开始建模：{sp_name}（进度 {progress_percentage}%）", "broadcast")

            # 前序模型摘要（用于递进）
            prev_model_summary = ""
            for j, pm in enumerate(completed_models):
                prev_sp_name = pm.get("sub_problem_name", f"子问题{j+1}")
                prev_obj = pm.get("objective_function", "")
                prev_vars = pm.get("decision_variables", [])
                prev_model_summary += f"- {prev_sp_name}: {prev_obj[:80]}，变量: {', '.join([v.get('name','') for v in prev_vars[:3]])}\n"

            step_id = f"phase2_modeler_sp{sp_id}"
            task_step = TaskStep(step_id=step_id, agent_name="modeler_agent", status=TaskStatus.RUNNING, started_at=datetime.now())
            self.task_history[task_id].append(task_step)

            try:
                model_output = await modeler_agent.execute(
                    task_input={"action": "build_model", "sub_problem_id": sp_id},
                    context={
                        **context_base,
                        "results": all_results,
                        "sub_problems": sub_problems,
                        "sub_problem_index": i,
                        "sub_problem": sp,
                        "total_sub_problems": len(sub_problems),
                        "analyzer_result": phase1_results.get("analyzer_agent", {}),
                        "data_result": phase1_results.get("data_agent", {}),
                        "research_result": phase1_results.get("research_agent", {}),
                        "previous_models": completed_models,
                        "previous_model_summary": prev_model_summary,
                    },
                )
                task_step.output_data = {"model": model_output}
                task_step.status = TaskStatus.COMPLETED

                # 更新黑板
                wm.set_result("modeler_agent", {**wm.results.get("modeler_agent", {}), "last_model": model_output})
                em.record("modeler_agent", "model_complete", f"[{i+1}] {sp_name}: {model_output.get('model_name', '')}")

                room.post("modeler_agent", f"[{i+1}/{len(sub_problems)}] 建模完成：{sp_name}（{model_output.get('model_name', '')}）", "broadcast")
            except Exception as e:
                logger.error(f"Sequential modeler sp{sp_id} failed: {e}")
                task_step.status = TaskStatus.FAILED
                task_step.error = str(e)
                model_output = {"error": str(e), "model_name": "建模失败", "model_type": "unknown"}
            task_step.completed_at = datetime.now()

            # 保存建模结果
            sr_entry = {
                "sub_problem_id": sp_id,
                "sub_problem_name": sp_name,
                "sub_problem_desc": sp_desc,
                "model": model_output,
                "solve": {},
            }
            section_results.append(sr_entry)

            # 递进：记录已完成模型
            completed_models.append({
                **model_output,
                "sub_problem_id": sp_id,
                "sub_problem_name": sp_name,
            })

            self._check_pause(task_id)

            # ====== 求解（当前子问题，用刚建的模型）======
            current_step_num += 1
            progress_percentage = int(current_step_num / total_steps * 100)
            room.post("coordinator", f"[{i+1}/{len(sub_problems)}] 开始求解：{sp_name}（进度 {progress_percentage}%）", "broadcast")

            # 前序求解摘要（用于递进）
            prev_solve_summary = ""
            for j, ps in enumerate(completed_solutions):
                prev_sp_name = ps.get("sub_problem_name", f"子问题{j+1}")
                prev_findings = ps.get("results", {}).get("key_findings", [])
                prev_numerical = ps.get("results", {}).get("numerical_results", {})
                numerical_str = ", ".join([f"{k}={v}" for k, v in prev_numerical.items() if k != "状态"])
                prev_solve_summary += f"- {prev_sp_name}: {'; '.join(str(f) for f in prev_findings[:2])}, 数值: {numerical_str or '见结果'}\n"

            step_id = f"phase2_solver_sp{sp_id}"
            task_step = TaskStep(step_id=step_id, agent_name="solver_agent", status=TaskStatus.RUNNING, started_at=datetime.now())
            self.task_history[task_id].append(task_step)

            try:
                solve_output = await solver_agent.execute(
                    task_input={"action": "solve", "sub_problem_id": sp_id},
                    context={
                        **context_base,
                        "results": all_results,
                        "sub_problems": sub_problems,
                        "sub_problem_index": i,
                        "sub_problem": sp,
                        "model_result": model_output,
                        "section_results": section_results,
                        "total_sub_problems": len(sub_problems),
                        "data_result": phase1_results.get("data_agent", {}),
                        "research_result": phase1_results.get("research_agent", {}),
                        "previous_solutions": completed_solutions,
                        "previous_solution_summary": prev_solve_summary,
                        "project_name": project_name,
                    },
                )
                task_step.output_data = {"solve": solve_output}
                task_step.status = TaskStatus.COMPLETED

                # 更新黑板
                wm.set_result("solver_agent", {**wm.results.get("solver_agent", {}), "last_solve": solve_output})
                findings = solve_output.get("results", {}).get("key_findings", [])
                em.record("solver_agent", "solve_complete", f"[{i+1}] {sp_name}: {'; '.join(str(f) for f in findings[:2]) if findings else '已求解'}")

                # 合并求解结果到 section_results
                for sr in section_results:
                    if sr.get("sub_problem_id") == sp_id:
                        sr["solve"] = solve_output
                        break

                findings = solve_output.get("results", {}).get("key_findings", [])
                room.post("solver_agent", f"[{i+1}/{len(sub_problems)}] 求解完成：{sp_name} → {'; '.join(str(f) for f in findings[:2])}", "broadcast")
            except Exception as e:
                logger.error(f"Sequential solver sp{sp_id} failed: {e}")
                task_step.status = TaskStatus.FAILED
                task_step.error = str(e)
                for sr in section_results:
                    if sr.get("sub_problem_id") == sp_id:
                        sr["solve"] = {"error": str(e)}
                        break
            task_step.completed_at = datetime.now()

            # 递进：记录已完成求解
            completed_solutions.append({
                **solve_output,
                "sub_problem_id": sp_id,
                "sub_problem_name": sp_name,
            })

            self._check_pause(task_id)

        # 全部子问题建模+求解完成，汇总通知
        room.post("coordinator", f"✅ 全部 {len(sub_problems)} 个子问题建模+求解完成！", "broadcast")

        # 写论文（使用完整的 section_results）
        return await self._write_paper_and_finish(task_id, problem_text, sub_problems, section_results, all_results, phase1_results, context_base, project_name=project_name, workflow_type=workflow_type)

    async def _write_paper_and_finish(
        self,
        task_id: str,
        problem_text: str,
        sub_problems: List[Dict[str, Any]],
        section_results: List[Dict[str, Any]],
        all_results: Dict[str, Any],
        phase1_results: Dict[str, Any],
        context_base: Dict[str, Any],
        project_name: Optional[str] = None,
        workflow_type: str = "standard",
        peer_review_feedback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """写论文并返回最终结果（batch和sequential共用）"""
        from ..core.task_persistence import save_task_metadata
        from ..core.memory import get_memory_manager
        mm = get_memory_manager()
        wm = mm.get_working(task_id)
        em = mm.get_episodic(task_id)
        room = context_base.get("chat_room")
        room.post("coordinator", "开始撰写完整论文...", "broadcast")

        step_id = "phase3_writer"
        task_step = TaskStep(step_id=step_id, agent_name="writer_agent", status=TaskStatus.RUNNING, started_at=datetime.now())
        self.task_history[task_id].append(task_step)

        agent = self.agents.get("writer_agent")
        agent._knowledge_base_id = context_base.get("knowledge_base_id")
        template = self._task_templates.get(task_id, "math_modeling")
        paper_output: Dict[str, Any] = {}
        writer_failed = False

        # v4.2: 轻量 checkpoint —— 若 writer 失败，优先使用已保存的 solver 结果重试，避免重复求解。
        checkpoint_path = get_project_output_dir(project_name) / f"writer_checkpoint_{task_id}.json"
        if checkpoint_path.exists():
            try:
                import json
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                section_results = checkpoint.get("section_results", section_results)
                all_results = {**all_results, **checkpoint.get("all_results", {})}
                logger.info(f"Loaded writer checkpoint for {task_id}")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to load writer checkpoint: {exc}")

        try:
            task_input = {"action": "write_paper", "problem_text": problem_text}
            if peer_review_feedback:
                task_input["review_feedback"] = peer_review_feedback
            # 传递 use_critique 参数（默认启用）
            task_input["use_critique"] = context_base.get("use_critique", True)
            paper_output = await agent.execute(
                task_input=task_input,
                context={
                    **context_base,
                    "results": all_results,
                    "section_results": section_results,
                    "sub_problems": sub_problems,
                    "analyzer_result": phase1_results.get("analyzer_agent", {}),
                    "data_result": phase1_results.get("data_agent", {}),
                    "research_result": phase1_results.get("research_agent", {}),
                    "template": template,
                    "workflow_type": workflow_type,
                },
            )

            task_step.output_data = {"writer_agent": paper_output}
            task_step.status = TaskStatus.COMPLETED
            all_results["writer_agent"] = paper_output
            self._post_agent_result(room, "writer_agent", "完整论文", paper_output)
        except Exception as e:
            logger.error(f"WriterAgent failed: {e}")
            task_step.status = TaskStatus.FAILED
            task_step.error = str(e)
            writer_failed = True
            # v5.3: CircuitOpenError（熔断器触发）必须立即通知用户 + 标记任务失败
            from ..core.circuit_breaker import CircuitOpenError
            if isinstance(e, CircuitOpenError):
                friendly_msg = (
                    f"⛔ 任务已暂停：API key 调用连续失败触发熔断\n"
                    f"原因：{e}\n"
                    f"建议：检查 API key 是否有效/欠费/限流，修复后点击「重新执行」"
                )
                task_step.error = friendly_msg
                room.post("coordinator", friendly_msg, "broadcast")
                logger.error(f"[Orchestrator] 任务 {task_id} 被 CircuitBreaker 暂停：{e}")
                # 立即把失败状态写入持久化（前端轮询能立刻看到）
                try:
                    from ..core.task_persistence import save_task_metadata
                    save_task_metadata(
                        task_id=task_id,
                        problem_text=problem_text or "",
                        status="failed",
                        created_at="",  # 空字符串保留 existing
                        completed_at=datetime.now().isoformat(),
                        error=friendly_msg,
                        current_step="已暂停（API key 异常）",
                    )
                except Exception as meta_exc:
                    logger.warning(f"持久化 CircuitOpenError 状态失败: {meta_exc}")
            # 保存 checkpoint 以便重试
            try:
                import json
                checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                checkpoint_path.write_text(
                    json.dumps({
                        "section_results": section_results,
                        "all_results": {k: v for k, v in all_results.items() if k != "writer_agent"},
                    }, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                logger.info(f"Saved writer checkpoint for {task_id}")
            except Exception as ckpt_exc:  # noqa: BLE001
                logger.warning(f"Failed to save writer checkpoint: {ckpt_exc}")
        task_step.completed_at = datetime.now()

        if self.task_history[task_id]:
            # v5.3: writer_failed 时保持 FAILED 状态，不要无条件设为 COMPLETED
            self.task_history[task_id][-1].status = (
                TaskStatus.FAILED if writer_failed else TaskStatus.COMPLETED
            )

        # 更新黑板：论文结果
        if wm:
            wm.set_result("writer_agent", paper_output)
            em.record("writer_agent", "paper_complete", f"论文完成：{paper_output.get('title', '未命名')}")
            # 压缩情景记忆
            if em:
                em.compress()
            # 保存任务记忆
            mm.save_task_memory(task_id)

        room.post("coordinator", f"完成！共 {len(sub_problems)} 个子问题，{len(section_results)} 个章节。", "broadcast")

        # ===== 保存代码和论文到 output 目录 =====
        try:
            saved_files = self._save_output_files(
                task_id, problem_text, section_results, all_results, project_name=project_name
            )
            room.post("coordinator", f"已保存 {len(saved_files)} 个文件到 output 目录", "broadcast")
        except Exception as e:
            logger.error(f"保存输出文件失败: {e}")

        # v4.2: 自动触发 camera-ready 打包（与 tasks.py 保持一致）
        if not writer_failed:
            try:
                from ..services.camera_ready import collect_artifacts, build
                task_output_dir = get_project_output_dir(project_name)
                template = self._task_templates.get(task_id, "math_modeling")
                artifact = collect_artifacts(task_id, task_output_dir, template_id=template)
                cr_result = build(task_id, artifact, task_output_dir, make_zip=True, max_zip_mb=50)
                room.post(
                    "coordinator",
                    f"📦 Camera-ready 打包完成：{cr_result.zip_path or 'N/A'}，"
                    f"编译验证={'通过' if cr_result.verification.get('success') else '未通过'}",
                    "broadcast",
                )
            except Exception as cr_exc:
                logger.exception(f"Auto camera-ready failed for {task_id}: {cr_exc}")

        # 提取经验教训（跨任务记忆）
        try:
            mm.extract_lessons_from_result(task_id, all_results)
        except Exception as e:
            logger.warning(f"Failed to extract lessons from task {task_id}: {e}")

        # 返回完整 all_results，包含 modeler_agent、solver_agent、writer_agent
        final_status = "failed" if writer_failed else "completed"
        result = {
            "task_id": task_id,
            "phase": final_status,
            "status": final_status,
            "sub_problems_count": len(sub_problems),
            "section_results": section_results,
            "writer_result": all_results.get("writer_agent", {}),
        }
        # 把所有 Agent 的结果都带上（modeler_agent/solver_agent 在此之前已被加入 all_results）
        for key in ("modeler_agent", "solver_agent"):
            if key in all_results:
                result[key] = all_results[key]
        return result

    def _build_section_results_template(self, model_output, sub_problems):
        """从modeler输出构建section_results模板"""
        section_results = []
        models = model_output.get("sub_problem_models", [])
        for m in models:
            section_results.append({
                "sub_problem_id": m.get("sub_problem_id"),
                "sub_problem_name": m.get("sub_problem_name"),
                "sub_problem_desc": m.get("sub_problem_desc"),
                "model": m,
                "solve": {},
            })
        existing_ids = {sr.get("sub_problem_id") for sr in section_results}
        for i, sp in enumerate(sub_problems):
            sp_id = sp.get("id", i + 1)
            if sp_id not in existing_ids:
                section_results.append({
                    "sub_problem_id": sp_id,
                    "sub_problem_name": sp.get("name", f"子问题{sp_id}"),
                    "sub_problem_desc": sp.get("description", ""),
                    "model": {"model_type": "optimization", "model_name": sp.get("suggested_method", "数学模型"), "objective_function": "待建模", "algorithm": {"name": "待确定", "description": "待建模"}},
                    "solve": {},
                })
        return section_results

    def _save_output_files(
        self,
        task_id: str,
        problem_text: str,
        section_results: List[Dict[str, Any]],
        all_results: Dict[str, Any],
        project_name: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """
        将求解器生成的代码和论文写入项目输出目录（支持项目隔离）。
        - <项目输出目录>/code/        → 各子问题的求解代码
        - <项目输出目录>/papers/     → LaTeX 论文
        - <项目输出目录>/models.json → 所有子问题的模型描述 JSON
        返回写入的文件路径列表。
        """
        import json
        output_dir = get_project_output_dir(project_name)
        code_dir = output_dir / "code"
        papers_dir = output_dir / "papers"
        code_dir.mkdir(parents=True, exist_ok=True)
        papers_dir.mkdir(parents=True, exist_ok=True)

        saved_files: List[str] = []

        # ===== 1. 保存代码文件 =====
        solver_output = all_results.get("solver_agent") or {}
        solves = solver_output.get("sub_problem_solutions", [])
        for sol in solves:
            sp_id = sol.get("sub_problem_id", "?")
            sp_name = sol.get("sub_problem_name", f"子问题{sp_id}")
            code_files = sol.get("code_files", [])
            for cf in code_files:
                filename = cf.get("filename", f"solver_sub{sp_id}.py")
                code_content = cf.get("code", "")
                if code_content:
                    filepath = code_dir / filename
                    filepath.write_text(code_content, encoding="utf-8")
                    saved_files.append(str(filepath))
                    logger.info(f"已保存代码: {filepath}")
                    # 保存对应的执行结果（如果有）
                    numerical = sol.get("numerical_results", {})
                    if numerical:
                        result_file = code_dir / f"{filepath.stem}_result.json"
                        result_file.write_text(
                            json.dumps(numerical, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        saved_files.append(str(result_file))

        # ===== 2. 保存论文（LaTeX）=====
        writer_output = all_results.get("writer_agent") or {}
        latex_code = writer_output.get("latex_code", "")
        if latex_code:
            # 用任务ID作为文件名
            paper_file = papers_dir / f"paper_{task_id}.tex"
            paper_file.write_text(latex_code, encoding="utf-8")
            saved_files.append(str(paper_file))
            logger.info(f"已保存论文: {paper_file}")
            # 同时保存 Markdown 版本（如果writer输出了markdown）
            md_code = writer_output.get("markdown_code", "") or writer_output.get("content", "")
            if md_code and len(md_code) > 100:
                md_file = papers_dir / f"paper_{task_id}.md"
                md_file.write_text(md_code, encoding="utf-8")
                saved_files.append(str(md_file))
            # v4.2: 同时复制到 final/main.tex，供 camera-ready collect_artifacts 读取
            final_dir = output_dir / "final"
            final_dir.mkdir(parents=True, exist_ok=True)
            final_tex = final_dir / "main.tex"
            final_tex.write_text(latex_code, encoding="utf-8")
            saved_files.append(str(final_tex))
            # 保存章节摘要/citations 供 bib 生成
            final_solution = final_dir / "solution.json"
            final_solution.write_text(
                json.dumps({
                    "title": writer_output.get("title", ""),
                    "abstract": writer_output.get("abstract", ""),
                    "keywords": writer_output.get("keywords", []),
                    "solver_agent": all_results.get("solver_agent", {}),
                    "writer_agent": writer_output,
                }, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            saved_files.append(str(final_solution))

        # ===== 3. 保存完整模型描述 JSON =====
        modeler_output = all_results.get("modeler_agent") or {}
        models = modeler_output.get("sub_problem_models", [])
        if models:
            models_file = output_dir / "models.json"
            models_file.write_text(
                json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            saved_files.append(str(models_file))

        # ===== 4. 保存完整求解结果 JSON =====
        if solves:
            solves_file = output_dir / "solves.json"
            solves_file.write_text(
                json.dumps(solves, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            saved_files.append(str(solves_file))

        logger.info(f"共保存 {len(saved_files)} 个输出文件到 output 目录")
        return saved_files

    # ====== 兼容旧的execute_workflow（直接进入完整流程，不暂停）======
    async def execute_workflow(
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
        use_critique: bool = True,
    ) -> Dict[str, Any]:
        """执行完整工作流（阶段1完成后直接继续，不等待用户确认）
        mode: "batch" 一次性建模/求解所有子问题
              "sequential" 逐个建模/求解，前序结果递进到后序
        """
        logger.info(f"Orchestrator starting full workflow for task {task_id} (mode={mode}, template={template}, workflow={workflow_type}, use_critique={use_critique})")

        # Phase 3：如果开启 LangGraph，委托给新编排器
        if self._use_langgraph:
            lg = self._get_langgraph_orchestrator()
            if lg:
                logger.info(f"Task {task_id}: delegating to LangGraphOrchestrator")
                return await lg.run(
                    task_id=task_id,
                    problem_text=problem_text,
                    workflow=workflow,
                    data_files=data_files,
                    mode=mode,
                    project_name=project_name,
                    knowledge_base_id=knowledge_base_id,
                    knowledge_base_ids=knowledge_base_ids,
                    template=template,
                    workflow_type=workflow_type,
                    use_critique=use_critique,
                )

        room = create_chat_room(task_id, problem_text)
        self.task_history[task_id] = []
        self._task_phase[task_id] = "full"
        self._current_project_name = project_name
        self._task_templates[task_id] = template
        self._task_workflows[task_id] = workflow_type

        # ===== 初始化记忆系统 =====
        mm = get_memory_manager()
        wm, em = mm.create_task_memory(task_id)
        wm.update_problem(text=problem_text[:500], template=template, workflow_type=workflow_type)
        em.record("coordinator", "task_start", f"任务开始（完整流程）：{problem_text[:100]}")

        context_base = {
            "problem_text": problem_text,
            "chat_room": room,
            "task_id": task_id,
            "data_files": data_files or [],
            "has_data": bool(data_files),
            "knowledge_base_id": knowledge_base_id,
            "workflow_type": workflow_type,
            "template": template,
            "working_memory": wm,
            "use_critique": use_critique,
        }
        all_results: Dict[str, Any] = {}

        # 初始化 _task_pause_data（batch 模式下需要，sequential 通过 confirm-subproblems 初始化）
        if task_id not in self._task_pause_data:
            self._task_pause_data[task_id] = {}

        # ====== 阶段1：根据工作流类型调整步骤 ======
        setup_steps = [
            ("analyzer_agent", "analyze", "问题分析"),
            ("data_agent", "analyze_data", "数据分析"),
        ]
        if workflow_type == "quick":
            room.post("coordinator", "⚡ 快速模式：跳过文献搜集，直接进入分析...", "broadcast")
        elif workflow_type == "deep_research":
            setup_steps.extend([
                ("research_agent", "search", "综合文献搜集"),
                ("research_agent", "search_background", "背景与趋势搜索"),
                ("research_agent", "search_methods", "方法与模型搜索"),
            ])
            room.post("coordinator", "🔬 深度研究模式：启动多轮文献搜集...", "broadcast")
        else:
            setup_steps.append(("research_agent", "search", "文献搜集"))
        for agent_name, action, label in setup_steps:
            step_id = f"phase1_{agent_name}"
            task_step = TaskStep(step_id=step_id, agent_name=agent_name, status=TaskStatus.RUNNING, started_at=datetime.now())
            self.task_history[task_id].append(task_step)
            room.post("coordinator", f"开始 {label} ...", "broadcast")
            agent = self.agents.get(agent_name)
            if not agent:
                task_step.status = TaskStatus.FAILED
                task_step.error = f"Agent {agent_name} not found"
                continue
            try:
                output = await agent.execute(
                    task_input={"action": action, "problem_text": problem_text},
                    context={**context_base, "results": all_results},
                )
                task_step.output_data = {agent_name: output}
                task_step.status = TaskStatus.COMPLETED
                all_results[agent_name] = output

                # 更新黑板
                wm.set_result(agent_name, output)
                if agent_name == "analyzer_agent":
                    wm.sub_problems = output.get("sub_problems", [])
                elif agent_name == "data_agent":
                    wm.data_insights = output.get("insights", [])
                elif agent_name == "research_agent":
                    wm.add_literature(output.get("papers", []), source="research_agent")
                    for m in output.get("methods", []):
                        wm.add_method(m)
                em.record(agent_name, f"{action}_complete", f"{label} 完成")

                self._post_agent_result(room, agent_name, label, output)
                room.post(agent_name, f"{label} 完成！", "broadcast")
            except Exception as e:
                logger.error(f"{label} failed: {e}")
                task_step.status = TaskStatus.FAILED
                task_step.error = str(e)
            task_step.completed_at = datetime.now()

        # ====== 阶段2：根据mode路由到对应的执行方法 ======
        sub_problems = all_results.get("analyzer_agent", {}).get("sub_problems", [])
        if not sub_problems:
            sub_problems = [{"id": 1, "name": "问题求解", "description": problem_text[:300]}]

        if mode == "sequential":
            # 逐个交替模式
            phase2_result = await self._execute_phase2_sequential(task_id, problem_text, sub_problems, data_files or [], project_name=project_name, knowledge_base_id=knowledge_base_id, workflow_type=workflow_type)
            section_results = phase2_result.get("section_results", [])
            all_results.update(phase2_result)
        else:
            # 批量模式
            phase2_result = await self._execute_phase2_batch(task_id, problem_text, sub_problems, data_files or [], project_name=project_name, knowledge_base_id=knowledge_base_id, workflow_type=workflow_type)
            section_results = phase2_result.get("section_results", [])
            all_results.update(phase2_result)

        self._save_workflow_result(task_id, all_results, section_results)

        # 清理任务级知识库
        try:
            from ..core.knowledge_manager import get_knowledge_manager
            km = get_knowledge_manager()
            task_kb_name = f"task_kb_{task_id}"
            for base_id, base in list(km._bases.items()):
                if base.name == task_kb_name:
                    km.delete_base(base_id)
                    logger.info(f"经典编排器：已清理任务级知识库 {base_id}")
        except Exception as e:
            logger.debug(f"清理任务级知识库失败: {e}")

        return {
            "task_id": task_id,
            "status": "completed",
            "results": all_results,
            "room_id": f"room_{task_id}",
        }

    def _save_workflow_result(self, task_id: str, all_results: Dict, section_results: List):
        """将工作流结果保存到磁盘"""
        try:
            from ..core.task_persistence import save_task_result, save_task_messages, save_task_metadata
            from ..core.memory import get_memory_manager
            from datetime import datetime as dt

            # 保存记忆 + 提取经验教训
            mm = get_memory_manager()
            wm = mm.get_working(task_id)
            em = mm.get_episodic(task_id)
            if wm:
                wm.set_result("section_results", section_results)
            if em:
                em.compress()
            mm.save_task_memory(task_id)
            try:
                mm.extract_lessons_from_result(task_id, all_results)
            except Exception as e:
                logger.warning(f"Failed to extract lessons: {e}")

            # 保存聊天记录
            room = get_chat_room(task_id)
            if room:
                msgs = room.get_messages()
                save_task_messages(task_id, msgs)

            # 构建output字典（每个Agent输出用其名称作为键）
            output = {}
            # 从 all_results 直接获取（阶段1的结果）
            for key, val in all_results.items():
                if isinstance(val, dict):
                    output[key] = val
            # 从 task_history 提取阶段2（modeler/solver/writer）的 output_data
            for step in self.task_history.get(task_id, []):
                if step.output_data:
                    for key, val in step.output_data.items():
                        if isinstance(val, dict) and key not in output:
                            output[key] = val
                        elif isinstance(val, dict) and key in output:
                            # 合并：task_history 里的结果更新到已有的结果上
                            merged = dict(output[key])
                            merged.update(val)
                            output[key] = merged
            # section_results 作为整体也保存
            if section_results:
                output["section_results"] = section_results
            else:
                logger.warning(f"[{task_id}] section_results is empty, skipping save")

            save_task_result(task_id, {
                "task_id": task_id,
                "output": output,
                "completed_at": dt.now().isoformat(),
            })

            # 更新任务状态
            save_task_metadata(
                task_id=task_id,
                problem_text=all_results.get("problem_text", ""),
                status="completed",
                created_at="",
                completed_at=dt.now().isoformat(),
                total_steps=len(self.task_history.get(task_id, [])),
                progress=100,
                current_step="已完成",
            )
        except Exception as e:
            logger.error(f"Failed to save workflow result: {e}")

    def _post_agent_result(self, room, agent_name: str, label: str, output: Dict[str, Any]):
        """[DEPRECATED] LangGraph 路径下使用 _post_chat() 替代。"""
        try:
            if agent_name == "analyzer_agent":
                sub_problems = output.get("sub_problems", [])
                content = f"📊 【{label}结果】\n\n**问题类型**: {output.get('problem_type', '-')}\n**难度**: {output.get('difficulty', '-')}\n**整体方案**: {output.get('overall_approach', '-')}\n\n**子问题分解** ({len(sub_problems)}个):"
                for i, sp in enumerate(sub_problems, 1):
                    sp_name = sp.get("name", f"子问题{i}")
                    sp_desc = sp.get("description", "")
                    sp_type = sp.get("problem_type", "")
                    sp_method = sp.get("suggested_method", sp.get("approach", ""))
                    content += f"\n{i}. **{sp_name}** ({sp_type})\n   {sp_desc[:120]}"
                    if sp_method:
                        content += f"\n   📌 方法: {sp_method}"
                room.post(agent_name, content, "broadcast")

            elif agent_name == "writer_agent":
                title = output.get("title", "论文")
                latex = output.get("latex_code", "")
                room.post(agent_name, f"📄 【论文生成完成】\n\n**标题**: {title}\n\n**LaTeX代码长度**: {len(latex)} 字符\n\n请在「论文预览」中查看完整内容。", "broadcast")
        except Exception as e:
            logger.warning(f"_post_agent_result failed: {e}")

    def get_task_status(self, task_id: str) -> Optional[TaskStatusResponse]:
        steps = self.task_history.get(task_id, [])
        if not steps:
            return None
        completed = sum(1 for s in steps if s.status == TaskStatus.COMPLETED)
        current = completed
        total = len(steps)
        last = steps[-1]
        current_step = last.agent_name
        return TaskStatusResponse(
            task_id=task_id,
            status=last.status,
            current_step=current_step,
            current=current,
            total_steps=total,
            progress_percentage=(completed / total * 100) if total > 0 else 0.0,
        )

