"""任务路由"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..schemas import (
    TaskCreateRequest, TaskStatusResponse, TaskResultResponse,
    TaskCancelRequest, TaskStatus, RerunRequest,
)
from ..agents import (
    Orchestrator, ResearchAgent, AnalyzerAgent, ModelerAgent,
    SolverAgent, WriterAgent, DataAgent, AlgorithmEngineerAgent,
    FinancialAnalystAgent,
)
from ..config import get_settings
from ..core.chat_room import get_chat_room
from ..core.runtime_config import get_runtime_api_key
from ..core.paths import get_data_dir, get_project_data_dir, get_project_output_dir
from ..services.learning import add_lessons_from_task
from ..services.preflight import (
    get_preflight_service,
    PreflightReport,
    DataMismatchError,
    DataCollectionFailedError,
    DataAdequacy,
)
from ..core.task_persistence import (
    save_task_metadata, save_task_messages, save_task_result,
    load_task_messages, load_task_result, list_all_tasks,
    load_task_metadata,
    delete_task as persistence_delete_task,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["任务管理"])

_orchestrator = None
DATA_DIR: Path = get_data_dir()  # 使用统一的路径管理

# 项目根目录（backend/data/uploads → backend/data → backend → 项目根）
PROJECT_ROOT: Path = DATA_DIR.parent.parent.parent


def reset_orchestrator() -> None:
    """重置 Orchestrator 及其依赖的运行时缓存，下次调用时使用最新配置重新初始化。

    清理内容：
    - 全局 _orchestrator 单例
    - Agent model/provider 映射（重新从磁盘加载 agent_configs.json）
    - 触发垃圾回收，确保旧 Agent 实例释放
    """
    global _orchestrator
    _orchestrator = None

    # 重新加载 Agent 配置，避免 rerun 时仍使用内存中的旧 provider/model 映射
    try:
        from .agents import _load_agent_configs
        _load_agent_configs()
    except Exception as e:
        logger.warning(f"reset_orchestrator: 重新加载 Agent 配置失败: {e}")

    # 强制释放旧的 Agent / LangGraph 编排器实例
    try:
        import gc
        gc.collect()
    except Exception:
        pass

    logger.info("Orchestrator 已重置，将在下次任务时用最新配置初始化")


def _get_agent_config(agent_name: str) -> Dict[str, str]:
    """从 agent_model_map 获取 Agent 配置，延迟导入避免循环依赖"""
    try:
        from .agents import agent_model_map
        mapping = agent_model_map.get(agent_name, {})
        return {
            "provider_id": mapping.get("provider_id", ""),
            "model": mapping.get("model", ""),
        }
    except Exception:
        return {"provider_id": "", "model": ""}


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        settings = get_settings()
        api_key = get_runtime_api_key()

        # 从 MCP 管理器获取各 Agent 的工具列表
        try:
            from ..mcp import get_mcp_manager
            mcp_mgr = get_mcp_manager()
        except Exception:
            mcp_mgr = None

        def get_agent_mcp_tools(agent_name: str) -> List[str]:
            if mcp_mgr is None:
                return []
            return mcp_mgr.get_tools_for_agent(agent_name)

        def make_agent(agent_class, agent_name: str, **extra_kwargs):
            """根据 agent_model_map 配置创建 Agent"""
            cfg = _get_agent_config(agent_name)
            model = cfg["model"] or settings.default_model
            provider_id = cfg["provider_id"]
            return agent_class(
                model=model,
                api_key=api_key,
                api_base_url=settings.api_base_url,
                provider_id=provider_id,
                **extra_kwargs,
            )

        agents = {
            "research_agent": make_agent(ResearchAgent, "research_agent",
                mcp_tools=get_agent_mcp_tools("research_agent")),
            "data_agent": make_agent(DataAgent, "data_agent",
                data_dir=str(DATA_DIR)),
            "analyzer_agent": make_agent(AnalyzerAgent, "analyzer_agent",
                mcp_tools=get_agent_mcp_tools("analyzer_agent")),
            "modeler_agent": make_agent(ModelerAgent, "modeler_agent",
                mcp_tools=get_agent_mcp_tools("modeler_agent")),
            "algorithm_engineer_agent": make_agent(AlgorithmEngineerAgent, "algorithm_engineer_agent",
                mcp_tools=get_agent_mcp_tools("algorithm_engineer_agent")),
            "financial_analyst_agent": make_agent(FinancialAnalystAgent, "financial_analyst_agent",
                mcp_tools=get_agent_mcp_tools("financial_analyst_agent")),
            "solver_agent": make_agent(SolverAgent, "solver_agent",
                mcp_tools=get_agent_mcp_tools("solver_agent")),
            "writer_agent": make_agent(WriterAgent, "writer_agent"),
        }
        _orchestrator = Orchestrator(agents=agents)
    return _orchestrator


def get_uploaded_files(selected_names: Optional[List[str]] = None, project_name: Optional[str] = None) -> list:
    """获取已上传的数据文件路径

    Args:
        selected_names: 如果提供，只返回文件名在该列表中的文件
        project_name: 项目名，指定时优先从项目 data 目录读取
    """
    files = []
    target_dir = get_project_data_dir(project_name)

    # 1. 从目标数据目录获取（项目目录或全局 uploads）
    if target_dir.exists():
        for f in target_dir.iterdir():
            if f.is_file():
                if selected_names is not None:
                    if f.name in selected_names:
                        files.append(str(f))
                else:
                    files.append(str(f))

    # 2. 从项目根目录获取（附件1-4.xlsx 等数据文件）——仅无项目时保留旧行为
    if not project_name and PROJECT_ROOT.exists():
        for f in PROJECT_ROOT.iterdir():
            if f.is_file() and f.suffix in [".xlsx", ".xls", ".csv", ".json"]:
                if f.name.startswith("附件") or f.name in ["data.json", "problem.json"]:
                    if selected_names is not None:
                        if f.name in selected_names:
                            files.append(str(f))
                    else:
                        files.append(str(f))

    # 去重
    seen = set()
    unique_files = []
    for fp in files:
        if fp not in seen:
            seen.add(fp)
            unique_files.append(fp)

    return unique_files


@router.post("/submit")
async def submit_task(req: TaskCreateRequest):
    # 验证问题描述不能为空
    if not req.problem_text or not req.problem_text.strip():
        raise HTTPException(
            status_code=400,
            detail="问题描述不能为空，请输入研究题目或问题描述"
        )

    task_id = "task_" + uuid4().hex[:12]
    created_at = datetime.now().isoformat()

    # 提取模板和工作流参数（用户显式选择优先）
    template = (req.options or {}).get("template")
    workflow_type = (req.options or {}).get("workflow")
    mode = req.mode

    # 如果指定了项目名，确保项目存在并同步
    project_name = req.project_name
    if project_name and project_name.strip():
        from ..core.project_persistence import get_project, create_project, add_task_to_project
        if not get_project(project_name):
            create_project(name=project_name)
        add_task_to_project(project_name, task_id)

    # 1. 保存初始预检状态
    save_task_metadata(
        task_id=task_id,
        problem_text=req.problem_text,
        status=TaskStatus.PREFLIGHT_RUNNING,
        created_at=created_at,
        total_steps=0,
        progress=0,
        current_step="preflight 决策中",
    )

    # 2. 收集已上传的数据文件
    selected_names = req.data_files
    data_files = get_uploaded_files(selected_names=selected_names, project_name=project_name)
    logger.info(f"Task {task_id}: found {len(data_files)} data files (selected={len(selected_names) if selected_names else 'all'}, project={project_name})")

    # 3. Preflight 决策
    preflight_service = get_preflight_service()
    try:
        preflight_report = await preflight_service.decide(
            problem_text=req.problem_text,
            data_files=data_files,
            template=template,
            workflow_type=workflow_type,
            mode=mode,
            project_name=project_name,
        )
    except Exception as e:
        logger.error(f"Task {task_id}: preflight 决策失败: {e}")
        save_task_metadata(
            task_id=task_id,
            problem_text=req.problem_text,
            status=TaskStatus.FAILED,
            created_at=created_at,
            completed_at=datetime.now().isoformat(),
            error=f"preflight 决策失败: {e}",
            data_files=data_files,
            project_name=project_name,
        )
        raise HTTPException(status_code=500, detail=f"preflight 决策失败: {e}")

    # 4. 数据不匹配 → 立即 422
    if preflight_report.data_mismatch_warning:
        logger.warning(f"Task {task_id}: 数据不匹配 - {preflight_report.data_mismatch_warning}")
        save_task_metadata(
            task_id=task_id,
            problem_text=req.problem_text,
            status=TaskStatus.CANNOT_SOLVE,
            created_at=created_at,
            completed_at=datetime.now().isoformat(),
            error=preflight_report.data_mismatch_warning,
            preflight_report=preflight_report.to_dict(),
            data_schemas=preflight_report.data_schemas,
            auto_decision_path="data_mismatch",
            data_files=data_files,
            project_name=project_name,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "message": "数据与题目不匹配",
                "preflight_report": preflight_report.to_dict(),
            },
        )

    # 5. 无数据或数据不足 → 尝试自主搜集（用户允许时）
    allow_self_collect = req.data_source in ("self_collect", "upload_and_collect")
    if preflight_report.data_adequacy == DataAdequacy.MISSING and allow_self_collect:
        save_task_metadata(
            task_id=task_id,
            problem_text=req.problem_text,
            status=TaskStatus.SELF_COLLECTING_DATA,
            created_at=created_at,
            total_steps=0,
            progress=0,
            current_step="自主搜集数据中",
            preflight_report=preflight_report.to_dict(),
            data_schemas=preflight_report.data_schemas,
            auto_decision_path="llm_collected",
            data_files=data_files,
            project_name=project_name,
        )

        orch = get_orchestrator()
        research_agent = orch.agents.get("research_agent")
        if research_agent and preflight_report.collection_plan:
            try:
                success, collected = await preflight_service.self_collect_data(
                    collection_plan=preflight_report.collection_plan,
                    search_fn=lambda q: research_agent.execute(
                        task_input={"action": "search", "query": q},
                        context={},
                    ),
                    task_id=task_id,
                    project_name=project_name,
                )
                if success:
                    # 重新 preflight（包含新搜集到的 URL 列表）
                    # 当前 self_collect 只保存 URL，未真正下载，因此仍视为 missing
                    # 后续 Phase 2 工具层实现下载后可在此重新决策
                    logger.info(f"Task {task_id}: 自主搜集到候选数据 {len(collected)} 条")
            except Exception as e:
                logger.warning(f"Task {task_id}: 自主搜集数据异常: {e}")

    # 6. 仍然缺失数据 → 422 要求上传
    # 但 deep_research 工作流自主搜索数据，不拦截；用户选了 self_collect 也尊重
    final_workflow_check = workflow_type or preflight_report.recommended_workflow
    if preflight_report.data_adequacy == DataAdequacy.MISSING and not data_files and final_workflow_check != "deep_research":
        logger.warning(f"Task {task_id}: 无数据且无法自主搜集，要求用户上传")
        save_task_metadata(
            task_id=task_id,
            problem_text=req.problem_text,
            status=TaskStatus.CANNOT_SOLVE,
            created_at=created_at,
            completed_at=datetime.now().isoformat(),
            error="缺少数据，请上传数据文件或允许系统自主搜集",
            preflight_report=preflight_report.to_dict(),
            data_schemas=preflight_report.data_schemas,
            auto_decision_path="user_provided",
            data_files=data_files,
            project_name=project_name,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "message": "缺少数据，请上传数据文件",
                "preflight_report": preflight_report.to_dict(),
            },
        )

    # 7. 使用推荐配置（用户未显式指定时）
    final_template = template or preflight_report.recommended_template
    final_workflow = workflow_type or preflight_report.recommended_workflow
    final_mode = mode or preflight_report.recommended_mode
    use_critique = (req.options or {}).get("use_critique", True)

    # 8. 保存最终决策到任务元数据
    save_task_metadata(
        task_id=task_id,
        problem_text=req.problem_text,
        status=TaskStatus.RUNNING,
        created_at=created_at,
        total_steps=0,
        progress=0,
        current_step="等待启动",
        data_files=data_files,
        project_name=project_name,
        knowledge_base_id=req.knowledge_base_id,
        knowledge_base_ids=req.knowledge_base_ids,
        template=final_template,
        workflow_type=final_workflow,
        mode=final_mode,
        use_critique=use_critique,
        problem_type=preflight_report.problem_type,
        preflight_report=preflight_report.to_dict(),
        data_schemas=preflight_report.data_schemas,
        auto_decision_path="llm_collected" if (not data_files and allow_self_collect) else "user_provided",
    )

    # 9. 启动工作流
    asyncio.create_task(_run_workflow(
        task_id, req.problem_text, req.workflow, data_files,
        final_mode, project_name, req.get_effective_kb_ids() or None,
        final_template, final_workflow,
        preflight_report.to_dict(),
        use_critique,
    ))

    return {
        "task_id": task_id,
        "status": TaskStatus.RUNNING,
        "message": "任务已提交，开始执行",
        "created_at": created_at,
        "data_files_count": len(data_files),
        "project_name": project_name,
        "preflight_report": preflight_report.to_dict(),
    }


async def _run_workflow(
    task_id: str,
    problem_text: str,
    workflow,
    data_files: list,
    mode: str = "batch",
    project_name: Optional[str] = None,
    knowledge_base_ids: Optional[List[str]] = None,  # v5.3.0: 多 KB
    template: str = "math_modeling",
    workflow_type: str = "standard",
    preflight_report: Optional[Dict] = None,
    use_critique: bool = True,
):
    # v5.3.0: 兼容旧接口 — knowledge_base_ids 是单值时也转 list
    if knowledge_base_ids is not None and not isinstance(knowledge_base_ids, list):
        knowledge_base_ids = [knowledge_base_ids]
    try:
        orch = get_orchestrator()
        # execute_workflow 内部会保存结果
        # TODO(Phase 3): 把 preflight_report 传入 LangGraph orchestrator 的初始 state
        await orch.execute_workflow(
            task_id, problem_text, workflow,
            data_files=data_files, mode=mode, project_name=project_name,
            knowledge_base_ids=knowledge_base_ids,
            knowledge_base_id=knowledge_base_ids[0] if knowledge_base_ids else None,
            template=template, workflow_type=workflow_type,
            use_critique=use_critique,
        )
        logger.info(f"Task {task_id} completed and saved")
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        save_task_metadata(
            task_id=task_id,
            problem_text=problem_text,
            status=TaskStatus.FAILED,
            created_at=task_id.replace("task_", ""),
            completed_at=datetime.now().isoformat(),
            error=str(e),
        )


@router.post("/{task_id}/preflight")
async def run_preflight(task_id: str, req: Optional[TaskCreateRequest] = None):
    """显式触发或重新触发 preflight 决策。

    如果任务已存在，返回已有的 preflight_report；否则根据请求体重新决策。
    """
    meta = load_task_metadata(task_id)
    if meta and meta.get("preflight_report"):
        return {"task_id": task_id, "preflight_report": meta["preflight_report"]}

    body = req or TaskCreateRequest(problem_text="")
    selected_names = body.data_files
    project_name = body.project_name
    data_files = get_uploaded_files(selected_names=selected_names, project_name=project_name)
    preflight_service = get_preflight_service()
    report = await preflight_service.decide(
        problem_text=body.problem_text,
        data_files=data_files,
        template=(body.options or {}).get("template"),
        workflow_type=(body.options or {}).get("workflow"),
        mode=body.mode,
        project_name=project_name,
    )
    return {"task_id": task_id, "preflight_report": report.to_dict()}


@router.post("/{task_id}/confirm")
async def confirm_preflight(task_id: str, req: dict):
    """用户确认 preflight 推荐后继续执行。"""
    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Task not found")

    # 允许用户覆盖推荐配置
    overrides = req or {}
    template = overrides.get("template") or meta.get("template", "math_modeling")
    workflow_type = overrides.get("workflow_type") or meta.get("workflow_type", "standard")
    mode = overrides.get("mode") or meta.get("mode", "batch")

    problem_text = meta.get("problem_text", "")
    project_name = meta.get("project_name")
    data_files = meta.get("data_files", [])
    # v5.3.0: 多 KB 兼容 — 优先 knowledge_base_ids，回退到 knowledge_base_id
    knowledge_base_ids = meta.get("knowledge_base_ids")
    if knowledge_base_ids is None:
        legacy_kb_id = meta.get("knowledge_base_id")
        knowledge_base_ids = [legacy_kb_id] if legacy_kb_id else None

    save_task_metadata(
        task_id=task_id,
        problem_text=problem_text,
        status=TaskStatus.RUNNING,
        created_at=meta.get("created_at", ""),
        total_steps=0,
        progress=0,
        current_step="等待启动",
        template=template,
        workflow_type=workflow_type,
        mode=mode,
        data_files=data_files,
        project_name=project_name,
        knowledge_base_id=knowledge_base_ids[0] if knowledge_base_ids else None,
        knowledge_base_ids=knowledge_base_ids,
        preflight_report=meta.get("preflight_report"),
        data_schemas=meta.get("data_schemas"),
        auto_decision_path=meta.get("auto_decision_path"),
    )

    asyncio.create_task(_run_workflow(
        task_id, problem_text, None, data_files,
        mode, project_name, knowledge_base_ids,
        template, workflow_type,
        meta.get("preflight_report"),
    ))
    return {"task_id": task_id, "status": TaskStatus.RUNNING}


@router.get("/{task_id}/status")
async def get_status(task_id: str):
    # 先从持久化数据获取（即使内存中没有）
    from ..core.task_persistence import load_task_metadata
    meta = load_task_metadata(task_id)
    if meta:
        return {
            "task_id": task_id,
            "status": meta.get("status", "unknown"),
            "progress_percentage": meta.get("progress", 0),
            "current_step": meta.get("current_step", ""),
            "total_steps": meta.get("total_steps", 0),
        }

    orch = get_orchestrator()
    status = orch.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return status


@router.get("/{task_id}/debug-history")
async def debug_history(task_id: str):
    """调试端点：查看 task_history 内容"""
    orch = get_orchestrator()
    steps = orch.task_history.get(task_id, [])
    return {
        "task_id": task_id,
        "history_len": len(steps),
        "steps": [
            {
                "step_id": s.step_id,
                "agent_name": s.agent_name,
                "status": s.status.value if hasattr(s.status, 'value') else str(s.status),
                "has_output": s.output_data is not None,
                "output_keys": list(s.output_data.keys()) if s.output_data else [],
            }
            for s in steps
        ],
    }


@router.get("/{task_id}/result")
async def get_result(task_id: str):
    # 优先从持久化数据获取
    result = load_task_result(task_id)
    if result:
        return result

    orch = get_orchestrator()
    status = orch.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="not found")
    if status.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="not completed")
    steps = orch.task_history.get(task_id, [])
    output = {}
    for s in steps:
        if s.output_data:
            for key, val in s.output_data.items():
                if key not in output:
                    output[key] = val
                elif isinstance(val, dict) and isinstance(output.get(key), dict):
                    merged = dict(output[key])
                    merged.update(val)
                    output[key] = merged
    return TaskResultResponse(
        task_id=task_id,
        status=status.status,
        output=output,
        completed_at=steps[-1].completed_at if steps else None,
    )


@router.get("/{task_id}/stream")
async def stream(task_id: str):
    orch = get_orchestrator()
    from ..core.task_persistence import load_task_metadata

    async def gen():
        last_status = None
        last_progress = -1
        last_step = ""
        while True:
            status = orch.get_task_status(task_id)
            meta = load_task_metadata(task_id)

            if not status and not meta:
                yield "event: error\ndata: " + json.dumps({"error": "not found"}) + "\n\n"
                break

            if status:
                st = status.status
                prog = status.progress_percentage
                cur = status.current_step
                tot = status.total_steps
            else:
                st = meta.get("status", "unknown")
                prog = meta.get("progress", 0)
                cur = meta.get("current_step", "")
                tot = meta.get("total_steps", 0)

            # 实时更新持久化进度
            save_task_metadata(task_id, "", st, "", progress=prog, current_step=cur, total_steps=tot)

            # 只在状态变化时推送事件
            if st != last_status or prog != last_progress or cur != last_step:
                last_status = st
                last_progress = prog
                last_step = cur

                # 判断事件类型
                event_type = "phase_changed"
                if st in [TaskStatus.COMPLETED, "completed"]:
                    event_type = "completed"
                elif st in [TaskStatus.FAILED, "failed"]:
                    event_type = "failed"
                elif cur and "peer_review" in str(cur).lower():
                    event_type = "peer_review_done"
                elif cur and "revise" in str(cur).lower():
                    event_type = "revision_done"

                payload = {
                    "task_id": task_id,
                    "status": st,
                    "progress": prog,
                    "current_step": cur,
                    "total_steps": tot,
                    "name": map_status_to_event_name(st, cur),
                }
                yield f"event: {event_type}\ndata: " + json.dumps(payload) + "\n\n"

            if st in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, "completed", "failed", "cancelled"]:
                break
            await asyncio.sleep(2)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


def map_status_to_event_name(status: str, current_step: str) -> str:
    """将后端状态映射到前端状态机名称"""
    s = (status or "").lower()
    if s == "completed":
        return "completed"
    if s == "failed":
        return "failed"
    if s == "paused" or s == "interrupted":
        return "paused"
    if s == "preflight_running":
        return "preflight_running"
    if s == "self_collecting_data":
        return "self_collecting_data"
    if s == "cannot_solve":
        return "cannot_solve"
    if s == "phase1_completed" or s == "phase1_completed_reviewing":
        return "phase1_reviewing"
    if s == "phase2_running" or s == "running":
        if current_step and "iterat" in current_step.lower():
            return "iterating_solver"
        if current_step and "peer_review" in current_step.lower():
            return "peer_review"
        if current_step and "revise" in current_step.lower():
            return "revising"
        if current_step and "final" in current_step.lower():
            return "finalizing"
        return "phase2_running"
    if s == "phase1_running":
        return "phase1_running"
    return "phase1_running"


@router.get("/{task_id}/messages")
async def get_messages(task_id: str):
    # 优先从持久化获取
    msgs = load_task_messages(task_id)
    if msgs:
        return msgs

    room = get_chat_room(task_id)
    if not room:
        raise HTTPException(status_code=404, detail="not found")
    return room.get_messages()


@router.post("/{task_id}/messages")
async def post_user_message(task_id: str, req: dict):
    """用户向聊天室发送消息（参与 Agent 讨论）。

    Human-in-the-loop 设计：
    - 用户消息会记录到聊天室，供 Agent 读取
    - 如果工作流正在等待用户输入（如 phase1_reviewing），
      用户消息可以触发继续执行
    - 如果用户提到特定 Agent（@mentions），该 Agent 会优先响应
    - 如果用户没有提到任何 Agent，系统会智能路由到最相关的 Agent
    """
    room = get_chat_room(task_id)
    if not room:
        raise HTTPException(status_code=404, detail="聊天室不存在")

    content = req.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    mentions = req.get("mentions", [])
    msg = room.user_post(content, mentions=mentions)

    # Human-in-the-loop：检查工作流状态，决定是否需要响应用户
    orch = get_orchestrator()
    task_status = orch.get_task_status(task_id)

    # 如果任务处于等待用户确认的状态，标记为可以继续
    if task_status and task_status.status in ["phase1_reviewing", "paused", "interrupted"]:
        # 用户发言后，解除暂停状态，允许工作流继续
        orch.resume_task(task_id)
        room.set_waiting_for_user(False)
        logger.info(f"Task {task_id}: 用户输入触发工作流继续")

    # 如果用户提到了特定 Agent，触发该 Agent 响应
    if mentions:
        for agent_name in mentions:
            agent = orch.agents.get(agent_name)
            if agent and hasattr(agent, "execute"):
                try:
                    # 异步触发 Agent 响应用户
                    asyncio.create_task(_agent_respond_to_user(
                        task_id, agent_name, agent, content, room
                    ))
                except Exception as e:
                    logger.warning(f"Agent {agent_name} 响应用户失败: {e}")
    else:
        # 智能路由：用户没有 @mentions 任何 Agent，自动分发给最相关的 Agent
        current_step = task_status.current_step if task_status else ""
        routed_agents = _route_user_message(content, current_step)

        for agent_name in routed_agents:
            if agent_name == "coordinator":
                # 协调者直接在聊天室回复
                room.post(
                    "coordinator",
                    f"收到您的反馈。我已记录您的建议，将在后续步骤中考虑。"
                    f"如果您希望特定 Agent 处理，请使用 @Agent名称 提及他们。\n\n"
                    f"💡 提示：可用 @research_agent、@data_agent、@modeler_agent、"
                    f"@solver_agent、@writer_agent 等直接联系对应专家。",
                    "broadcast"
                )
            else:
                agent = orch.agents.get(agent_name)
                if agent and hasattr(agent, "execute"):
                    try:
                        asyncio.create_task(_agent_respond_to_user(
                            task_id, agent_name, agent, content, room
                        ))
                        logger.info(f"Task {task_id}: 智能路由用户消息到 {agent_name}")
                    except Exception as e:
                        logger.warning(f"Agent {agent_name} 响应用户失败: {e}")

    return {
        "message_id": msg.id,
        "status": "sent",
        "workflow_resumed": task_status.status in ["phase1_reviewing", "paused", "interrupted"] if task_status else False,
    }


# 智能路由：关键词到 Agent 的映射（用于自动分发用户反馈）
_AGENT_KEYWORDS = {
    "research_agent": ["文献", "搜索", "资料", "引用", "reference", "paper", "文献综述", "相关研究", "背景", "survey"],
    "data_agent": ["数据", "清洗", "预处理", "特征", "dataset", "csv", "表格", "缺失值", "归一化", "标准化"],
    "analyzer_agent": ["分析", "问题", "分解", "理解", "需求", "约束", "条件", "假设", "问题描述", "任务"],
    "modeler_agent": ["模型", "建模", "数学", "公式", "方程", "优化", "约束", "变量", "参数", "建模"],
    "algorithm_engineer_agent": ["算法", "方法", "策略", "创新", "复杂度", "启发式", "元启发式", "遗传算法", "神经网络"],
    "solver_agent": ["求解", "代码", "编程", "实现", "python", "运行", "调试", "错误", "bug", "计算", "数值"],
    "writer_agent": ["论文", "写作", "latex", "段落", "章节", "摘要", "引言", "结论", "格式", "排版", "语言", "英文"],
    "peer_review_agent": ["审稿", "评议", "质量", "缺陷", "改进", "建议", "评价", "评分", "问题", "漏洞"],
    "figure_agent": ["图表", "图片", "可视化", "画图", "figure", "plot", "chart", "graph", "插图", "示意图"],
}


def _route_user_message(content: str, current_step: str = "") -> List[str]:
    """智能路由：根据用户消息内容自动分发给最相关的 Agent。

    返回应该响应的 Agent 名称列表（按相关性排序）。
    """
    content_lower = content.lower()
    scores: Dict[str, int] = {}

    # 1. 关键词匹配
    for agent_name, keywords in _AGENT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw.lower() in content_lower:
                score += 1
                # 精确匹配加分
                if kw in content:
                    score += 1
        if score > 0:
            scores[agent_name] = score

    # 2. 根据当前工作流步骤推断（如果关键词匹配不足）
    if not scores and current_step:
        step_lower = current_step.lower()
        step_mapping = {
            "research": ["research_agent"],
            "data": ["data_agent"],
            "analy": ["analyzer_agent"],
            "model": ["modeler_agent"],
            "algorithm": ["algorithm_engineer_agent"],
            "solver": ["solver_agent"],
            "writer": ["writer_agent"],
            "peer_review": ["peer_review_agent"],
            "figure": ["figure_agent"],
        }
        for step_key, agents in step_mapping.items():
            if step_key in step_lower:
                scores[agents[0]] = 1  # 给予基础分
                break

    # 3. 如果没有匹配到任何 Agent，默认路由到协调者
    if not scores:
        return ["coordinator"]

    # 按分数排序，返回前 2 个最相关的 Agent
    sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [agent for agent, _ in sorted_agents[:2]]


async def _agent_respond_to_user(
    task_id: str,
    agent_name: str,
    agent,
    user_content: str,
    room,
):
    """Agent 响应用户消息。

    如果用户给出的是修正建议，Agent 会：
    1. 确认收到建议
    2. 将建议记录到聊天室上下文
    3. 如果是工作流中的 Agent，标记需要重新执行相关步骤
    """
    try:
        # 构建上下文，包含用户反馈历史
        feedback_summary = room.get_latest_feedback_summary()
        context = {
            "task_id": task_id,
            "chat_room": room,
            "problem_text": room.problem_text,
            "user_message": user_content,
            "user_feedback": feedback_summary,
        }

        # 检测用户意图
        content_lower = user_content.lower()
        is_correction = any(kw in content_lower for kw in ["修正", "修改", "改", "不对", "错误", "问题", "应该", "建议"])
        is_approval = any(kw in content_lower for kw in ["确认", "同意", "可以", "好", "ok", "yes"])

        if is_correction:
            # 修正建议：Agent 需要确认并记录
            if hasattr(agent, "respond_to_user"):
                output = await agent.respond_to_user(
                    user_message=user_content,
                    intent="correction",
                    feedback=feedback_summary,
                    context=context,
                )
            else:
                # 在聊天室中广播修正建议已被记录
                room.post(
                    agent_name,
                    f"✅ 已收到您的修正建议。我会在后续工作中考虑这些调整。\n\n"
                    f"💡 如果您希望立即修改当前结果，请说「重新执行」或「重做」。",
                    "broadcast"
                )
        elif is_approval:
            # 确认/批准：Agent 感谢并继续
            if hasattr(agent, "respond_to_user"):
                output = await agent.respond_to_user(
                    user_message=user_content,
                    intent="approval",
                    feedback=feedback_summary,
                    context=context,
                )
            else:
                room.post(
                    agent_name,
                    f"感谢您的确认！我会继续按当前方向推进工作。",
                    "broadcast"
                )
        else:
            # 一般询问或讨论
            if hasattr(agent, "respond_to_user"):
                output = await agent.respond_to_user(
                    user_message=user_content,
                    intent="general",
                    feedback=feedback_summary,
                    context=context,
                )
            else:
                room.post(
                    agent_name,
                    f"收到您的消息。我会根据您的反馈调整工作。",
                    "broadcast"
                )
                # Agent 回复会由 agent.execute 内部通过 chat_room.post 发送
    except Exception as e:
        logger.warning(f"Agent {agent_name} 响应用户时出错: {e}")
        room.post(agent_name, f"抱歉，我暂时无法处理您的请求。错误: {str(e)[:100]}", "error")


@router.get("/{task_id}/messages/stream")
async def stream_messages(task_id: str):
    """SSE 实时推送聊天室消息。"""
    room = get_chat_room(task_id)
    if not room:
        raise HTTPException(status_code=404, detail="聊天室不存在")

    return StreamingResponse(
        room.message_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{task_id}/discuss")
async def start_discussion(task_id: str, req: dict):
    """发起多 Agent 讨论。"""
    room = get_chat_room(task_id)
    if not room:
        raise HTTPException(status_code=404, detail="聊天室不存在")

    topic = req.get("topic", "").strip()
    participants = req.get("participants", ["analyzer_agent", "modeler_agent", "peer_review_agent"])
    if not topic:
        raise HTTPException(status_code=400, detail="讨论主题不能为空")

    discuss_id = room.start_discussion(topic, participants)
    return {"discuss_id": discuss_id, "participants": participants}


@router.get("/")
async def list_tasks():
    """列出所有任务（从持久化存储，完整元数据）"""
    return list_all_tasks()


@router.post("/{task_id}/phase1")
async def run_phase1(task_id: str):
    """阶段1：分析+数据+文献，结束后等待用户确认子问题"""
    from ..core.task_persistence import load_task_metadata
    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Task not found")

    problem_text = meta.get("problem_text", "")
    project_name = meta.get("project_name")
    data_files = meta.get("data_files", [])
    if not data_files:
        data_files = get_uploaded_files(project_name=project_name)

    template = meta.get("template", "math_modeling")
    workflow_type = meta.get("workflow_type", "standard")

    # 异步执行阶段1
    asyncio.create_task(_run_phase1_workflow(task_id, problem_text, data_files, project_name, template, workflow_type))

    return {"task_id": task_id, "status": "running", "phase": "phase1", "message": "阶段1执行中..."}


async def _run_phase1_workflow(task_id: str, problem_text: str, data_files: list, project_name: Optional[str] = None, template: str = "math_modeling", workflow_type: str = "standard"):
    from ..core.task_persistence import load_task_metadata, save_task_result, save_task_metadata
    try:
        orch = get_orchestrator()
        result = await orch.execute_phase1(task_id, problem_text, data_files, project_name=project_name, template=template, workflow_type=workflow_type)
        logger.info(f"Phase1 completed for {task_id}")
        save_task_result(task_id, {
            "task_id": task_id,
            "phase": "phase1_completed",
            "output": result,
            "completed_at": datetime.now().isoformat(),
        })
        meta = load_task_metadata(task_id) or {}
        save_task_metadata(
            task_id=task_id, problem_text=problem_text, status="phase1_completed",
            created_at=meta.get("created_at", ""), completed_at=datetime.now().isoformat(),
            total_steps=0, progress=33, current_step="请确认子问题列表",
        )
    except Exception as e:
        logger.error(f"Phase1 failed for {task_id}: {e}")
        meta = load_task_metadata(task_id) or {}
        save_task_metadata(
            task_id=task_id, problem_text=problem_text, status="failed",
            created_at=meta.get("created_at", ""), completed_at=datetime.now().isoformat(),
            error=str(e),
        )


@router.post("/{task_id}/phase2")
async def run_phase2(task_id: str, req: dict = None):
    """阶段2：建模+求解+论文（用户确认子问题后执行）"""
    from ..core.task_persistence import load_task_metadata, load_task_result, save_task_metadata

    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Task not found")

    # 获取用户提交的子问题列表（可能经过编辑）
    sub_problems = req.get("sub_problems") if req else None
    if not sub_problems:
        raise HTTPException(status_code=400, detail="缺少 sub_problems 参数")

    # 获取求解模式：batch（一次性）或 sequential（逐个递进）
    mode = req.get("mode", "batch") if req else "batch"

    problem_text = meta.get("problem_text", "")
    project_name = meta.get("project_name")
    data_files = meta.get("data_files", [])
    if not data_files:
        data_files = get_uploaded_files(project_name=project_name)

    template = meta.get("template", "math_modeling")
    workflow_type = meta.get("workflow_type", "standard")

    asyncio.create_task(_run_phase2_workflow(task_id, problem_text, sub_problems, data_files, mode, project_name, template, workflow_type))

    return {"task_id": task_id, "status": "running", "phase": "phase2", "mode": mode, "message": f"阶段2执行中（{'逐个递进' if mode == 'sequential' else '批量'}建模求解）..."}


async def _run_phase2_workflow(task_id: str, problem_text: str, sub_problems: List, data_files: list, mode: str = "batch", project_name: Optional[str] = None, template: str = "math_modeling", workflow_type: str = "standard"):
    from ..core.task_persistence import load_task_metadata, save_task_result, save_task_metadata
    from ..core.paths import get_project_output_dir
    from ..services.camera_ready import collect_artifacts, build
    try:
        orch = get_orchestrator()
        result = await orch.execute_phase2(task_id, problem_text, sub_problems, data_files, mode=mode, project_name=project_name, template=template, workflow_type=workflow_type)
        logger.info(f"Phase2 completed for {task_id} (mode={mode})")

        steps = orch.task_history.get(task_id, [])
        output = {}
        for s in steps:
            if s.output_data:
                for key, val in s.output_data.items():
                    if key not in output:
                        output[key] = val
                    elif isinstance(val, dict) and isinstance(output.get(key), dict):
                        merged = dict(output[key])
                        merged.update(val)
                        output[key] = merged

        save_task_result(task_id, {"task_id": task_id, "output": output, "completed_at": datetime.now().isoformat()})

        # v5.1: 把 writer output 写到 final/main.tex + final/chapter_summaries.json，
        # 让 camera_ready 一定可以读到 LaTeX 和 citations（不再依赖 _save_output_files）
        try:
            task_output_dir = get_project_output_dir(project_name)
            final_dir = task_output_dir / "final"
            final_dir.mkdir(parents=True, exist_ok=True)

            writer_out = output.get("writer_agent") or {}
            latex_code = writer_out.get("latex_code", "")
            if latex_code:
                (final_dir / "main.tex").write_text(latex_code, encoding="utf-8")
                # 兼容老路径：也写一份 MathModeling_Paper.tex
                (final_dir / "MathModeling_Paper.tex").write_text(latex_code, encoding="utf-8")
                logger.info(f"Saved final/main.tex for {task_id} ({len(latex_code)} chars)")

            # chapter_summaries.json —— camera_ready collect_artifacts 读 citations 用
            chapters = writer_out.get("chapters", []) or []
            if chapters:
                (final_dir / "chapter_summaries.json").write_text(
                    json.dumps(chapters, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                logger.info(f"Saved final/chapter_summaries.json for {task_id} ({len(chapters)} chapters)")

            # solution.json —— camera_ready 读 metadata + solver 输出
            (final_dir / "solution.json").write_text(
                json.dumps({
                    "title": writer_out.get("title", ""),
                    "abstract": writer_out.get("abstract", ""),
                    "keywords": writer_out.get("keywords", []),
                    "writer_agent": writer_out,
                    "solver_agent": output.get("solver_agent", {}),
                    "modeler_agent": output.get("modeler_agent", {}),
                    "analyzer_agent": output.get("analyzer_agent", {}),
                    "research_agent": output.get("research_agent", {}),
                    "citations": writer_out.get("citations", []),  # v5.1: 顶层兜底
                }, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as save_exc:
            logger.warning(f"Failed to save final/ for {task_id}: {save_exc}")

        # v4.2: 自动触发 camera-ready 打包（仅当 phase2 成功）
        try:
            task_output_dir = get_project_output_dir(project_name)
            artifact = collect_artifacts(task_id, task_output_dir, template_id=template)
            cr_result = build(task_id, artifact, task_output_dir, make_zip=True, max_zip_mb=50)
            logger.info(f"Auto camera-ready for {task_id}: zip={cr_result.zip_path}, verification={cr_result.verification}")
        except Exception as cr_exc:  # noqa: BLE001
            logger.warning(f"Auto camera-ready failed for {task_id}: {cr_exc}")

        meta = load_task_metadata(task_id) or {}
        save_task_metadata(
            task_id=task_id, problem_text=problem_text, status="completed",
            created_at=meta.get("created_at", ""), completed_at=datetime.now().isoformat(),
            total_steps=len(steps), progress=100, current_step="已完成",
        )
    except Exception as e:
        logger.error(f"Phase2 failed for {task_id}: {e}")
        meta = load_task_metadata(task_id) or {}
        save_task_metadata(
            task_id=task_id, problem_text=problem_text, status="failed",
            created_at=meta.get("created_at", ""), completed_at=datetime.now().isoformat(),
            error=str(e),
        )


@router.post("/{task_id}/confirm-subproblems")
async def confirm_subproblems(task_id: str, req: dict):
    """确认子问题列表，进入阶段2"""
    from ..core.task_persistence import load_task_metadata
    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Task not found")

    sub_problems = req.get("sub_problems", [])
    if not sub_problems:
        raise HTTPException(status_code=400, detail="sub_problems不能为空")

    problem_text = meta.get("problem_text", "")
    project_name = meta.get("project_name")
    template = meta.get("template", "math_modeling")
    workflow_type = meta.get("workflow_type", "standard")
    data_files = meta.get("data_files", [])
    if not data_files:
        data_files = get_uploaded_files(project_name=project_name)

    asyncio.create_task(_run_phase2_workflow(task_id, problem_text, sub_problems, data_files, project_name=project_name, template=template, workflow_type=workflow_type))

    return {"task_id": task_id, "status": "running", "phase": "phase2", "message": f"开始批量建模求解{len(sub_problems)}个子问题..."}


# ====================================================================
# Phase 3: Camera-Ready 打包端点
# ====================================================================

@router.post("/{task_id}/camera-ready")
async def build_camera_ready(task_id: str, req: Optional[dict] = None):
    """把任务产物打成 camera-ready zip（Phase 3）。

    Body（可选）:
        ``template_id``: 论文模板 ID（默认从 task meta 读）
        ``make_zip``: 是否同时打 zip（默认 True）
        ``max_zip_mb``: zip 大小上限（默认 50MB）

    返回:
        ``output_dir``: 产物目录（``<项目输出目录>/camera_ready_<task_id>/``）
        ``zip_path``: zip 文件路径（如 make_zip=True）
        ``skipped_reasons``: 缺失的产物记录
        ``artifact_summary``: 收集到的产物数量
    """
    from ..core.task_persistence import load_task_metadata
    from ..services.camera_ready import (
        collect_artifacts, build, CameraReadyArtifact,
    )
    from ..core.paths import get_project_output_dir

    req = req or {}
    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Task not found")

    template_id = req.get("template_id") or meta.get("template", "math_modeling")
    make_zip = bool(req.get("make_zip", True))
    max_zip_mb = int(req.get("max_zip_mb", 50))

    project_name = meta.get("project_name") or task_id
    try:
        task_output_dir = get_project_output_dir(project_name)
    except Exception:
        task_output_dir = Path("./output") / f"work_{project_name}"

    if not task_output_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Task output dir not found: {task_output_dir}",
        )

    # 收集产物
    artifact = collect_artifacts(task_id, task_output_dir, template_id=template_id)

    # 把求解 Agent 输出的 code_manifest 摘要注入（如果有）
    try:
        result_path = task_output_dir / "final" / "solution.json"
        if result_path.exists():
            sol = json.loads(result_path.read_text(encoding="utf-8"))
            # 从求解器结果中提 code_manifest 文本（多 sub 时合并）
            sp_solutions = sol.get("solver_agent", {}).get("sub_problem_solutions", []) or []
            manifest_lines = []
            for sp_sol in sp_solutions:
                cm = sp_sol.get("code_manifest") or {}
                if cm and cm.get("manifest"):
                    for f in cm["manifest"].get("files", []):
                        manifest_lines.append(f"- {f.get('path')} (role={f.get('role')}): {f.get('description', '')}")
            if manifest_lines:
                artifact.code_manifest_text = "# Code Manifest\n" + "\n".join(manifest_lines)
            # bib entries 从 chapter_summaries 收集（实际有 arxiv_id 的条目）
            bib = []
            chap_sum = sol.get("writer_agent", {}).get("chapters", []) or []
            for ch in chap_sum:
                for cit in ch.get("citations", []) or []:
                    if isinstance(cit, dict) and (cit.get("arxiv_id") or cit.get("key")):
                        bib.append(cit)
            artifact.bib_entries = bib
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"camera-ready 收集 bib 失败: {exc}")

    # 打包
    output_root = task_output_dir
    result = build(
        task_id=task_id,
        artifact=artifact,
        output_dir=output_root,
        make_zip=make_zip,
        max_zip_mb=max_zip_mb,
    )
    return result.to_dict()


@router.get("/{task_id}/camera-ready")
async def get_camera_ready_status(task_id: str):
    """查询 camera-ready 产物状态（不重新打包）。"""
    from ..core.task_persistence import load_task_metadata
    from ..core.paths import get_project_output_dir

    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Task not found")
    project_name = meta.get("project_name") or task_id
    try:
        task_output_dir = get_project_output_dir(project_name)
    except Exception:
        task_output_dir = Path("./output") / f"work_{project_name}"

    pkg = task_output_dir / f"camera_ready_{task_id}"
    zip_path = task_output_dir / f"camera_ready_{task_id}.zip"

    # 独立交付物（直接给用户的：tex / pdf / bib / 参考文献来源）
    tex_path = pkg / "main.tex" if (pkg / "main.tex").exists() else None
    pdf_in_pkg = pkg / "main.pdf"
    pdf_in_pkg_rel = str(pdf_in_pkg.relative_to(PROJECT_ROOT)) if pdf_in_pkg.exists() else None
    # 编译后复制到 output_dir 根的 paper_{task_id}.pdf
    pdf_root = task_output_dir / f"paper_{task_id}.pdf"
    pdf_root_rel = str(pdf_root.relative_to(PROJECT_ROOT)) if pdf_root.exists() else None
    bib_path = pkg / "main.bib" if (pkg / "main.bib").exists() else None
    refs_sources_path = pkg / "references_sources.txt" if (pkg / "references_sources.txt").exists() else None

    def _rel(p: Optional[Path]) -> Optional[str]:
        if not p:
            return None
        try:
            return str(p.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(p)

    pkg_rel = _rel(pkg) if pkg.exists() else None
    zip_rel = _rel(zip_path) if zip_path.exists() else None
    tex_rel = _rel(tex_path)
    bib_rel = _rel(bib_path)
    refs_rel = _rel(refs_sources_path)

    return {
        "task_id": task_id,
        "package_dir": pkg_rel,
        "zip_path": zip_rel,
        # 直接可下载的独立交付物
        "tex_path": tex_rel,
        "pdf_path": pdf_root_rel or pdf_in_pkg_rel,
        "bib_path": bib_rel,
        "refs_sources_path": refs_rel,
        "exists": pkg.exists() or zip_path.exists(),
    }


@router.get("/{task_id}/camera-ready/download")
async def download_camera_ready(task_id: str, path: str):
    """下载 camera-ready 文件（zip 或独立交付物）。

    支持的 file_path.name 格式：
    - ``camera_ready_<task_id>.zip`` — 完整打包
    - ``main.tex`` — 论文源文件（必须在 camera_ready_<task_id>/ 内）
    - ``main.pdf`` — 编译产物（在 camera_ready_<task_id>/ 内或 output_dir 根目录）
    - ``main.bib`` — 参考文献 bib 文件
    - ``references_sources.txt`` — 参考文献原始来源（链接/DOI/arXiv）
    - ``paper_<task_id>.pdf`` — 复制到 output_dir 根目录的 PDF
    """
    from fastapi.responses import FileResponse
    from ..core.task_persistence import load_task_metadata

    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Task not found")

    # 安全检查：只允许下载预定义的交付物文件名
    file_path = Path(path)
    allowed_names = {
        f"camera_ready_{task_id}.zip",
        "main.tex",
        "main.pdf",
        "main.bib",
        "references_sources.txt",
        f"paper_{task_id}.pdf",
    }
    if file_path.name not in allowed_names:
        raise HTTPException(status_code=400, detail="Invalid file path")

    # 解析绝对路径
    project_name = meta.get("project_name") or task_id
    try:
        task_output_dir = get_project_output_dir(project_name)
    except Exception:
        task_output_dir = Path("./output") / f"work_{project_name}"

    # 候选位置（pkg 内 + output_dir 根目录）
    pkg_dir = task_output_dir / f"camera_ready_{task_id}"
    candidates = [
        pkg_dir / file_path.name,
        task_output_dir / file_path.name,
    ]
    full_path = None
    for cand in candidates:
        if cand.exists():
            full_path = cand
            break

    if not full_path:
        raise HTTPException(status_code=404, detail="File not found")

    # MIME 类型
    mime_map = {
        ".zip": "application/zip",
        ".tex": "application/x-tex",
        ".pdf": "application/pdf",
        ".bib": "application/x-bibtex",
        ".txt": "text/plain; charset=utf-8",
    }
    media_type = mime_map.get(full_path.suffix, "application/octet-stream")

    return FileResponse(
        path=str(full_path),
        filename=file_path.name,
        media_type=media_type,
    )


@router.post("/{task_id}/cancel")
async def cancel(task_id: str, req: TaskCancelRequest):
    orch = get_orchestrator()
    if task_id not in orch.task_history:
        raise HTTPException(status_code=404, detail="not found")
    for step in orch.task_history[task_id]:
        if step.status == TaskStatus.RUNNING:
            step.status = TaskStatus.CANCELLED
            step.completed_at = datetime.now()

    # 更新持久化状态
    from ..core.task_persistence import load_task_metadata
    meta = load_task_metadata(task_id)
    if meta:
        save_task_metadata(
            task_id=task_id,
            problem_text=meta.get("problem_text", ""),
            status="cancelled",
            created_at=meta.get("created_at", ""),
            completed_at=datetime.now().isoformat(),
            total_steps=meta.get("total_steps", 0),
            progress=meta.get("progress", 0),
            current_step="已取消",
        )

    return {"task_id": task_id, "status": "cancelled"}


@router.post("/{task_id}/rerun")
async def rerun_task(task_id: str, req: Optional[RerunRequest] = None):
    """用当前系统配置重新执行一个历史任务。

    从历史任务元数据中读取问题描述、数据文件、项目等信息，
    使用当前最新的 API 配置（provider / key / model）重新执行。
    """
    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 生成新 task_id
    new_task_id = "task_" + uuid4().hex[:12]
    created_at = datetime.now().isoformat()

    # 从历史任务提取参数，用户可覆盖
    # 兼容旧字段：旧版本可能用 "problem" 而不是 "problem_text"
    historical_problem = meta.get("problem_text") or meta.get("problem", "")
    problem_text = (req.problem_text if req and req.problem_text else None) or historical_problem
    if not problem_text or not problem_text.strip():
        # 如果用户通过 rerun 请求补充了问题描述，优先使用
        if req and req.problem_text and req.problem_text.strip():
            problem_text = req.problem_text.strip()
        else:
            # 422 前写 metadata 保持状态一致
            save_task_metadata(
                task_id=task_id,
                problem_text=historical_problem,
                status="cannot_solve",
                created_at=meta.get("created_at", ""),
                completed_at=datetime.now().isoformat(),
                error="rerun: 历史任务缺少问题描述，无法重新执行",
            )
            raise HTTPException(
                status_code=422,
                detail="历史任务缺少问题描述，无法重新执行。请新建任务并输入问题。",
            )
    data_files = meta.get("data_files", [])
    project_name = meta.get("project_name")
    # v5.3.0: 多 KB 兼容
    knowledge_base_ids = meta.get("knowledge_base_ids")
    if knowledge_base_ids is None:
        legacy_kb_id = meta.get("knowledge_base_id")
        knowledge_base_ids = [legacy_kb_id] if legacy_kb_id else None
    template = (req.template if req and req.template else None) or meta.get("template", "math_modeling")
    workflow_type = (req.workflow_type if req and req.workflow_type else None) or meta.get("workflow_type", "standard")
    mode = (req.mode if req and req.mode else None) or meta.get("mode", "batch")

    logger.info(f"Rerun task {task_id} → new task {new_task_id} (template={template}, workflow={workflow_type})")

    # 关联到同一项目
    if project_name:
        from ..core.project_persistence import get_project, create_project, add_task_to_project
        if not get_project(project_name):
            create_project(name=project_name)
        add_task_to_project(project_name, new_task_id)

    # 重置 orchestrator 以使用当前最新的 API 配置
    reset_orchestrator()

    # 保存新任务初始状态
    save_task_metadata(
        task_id=new_task_id,
        problem_text=problem_text,
        status=TaskStatus.RUNNING,
        created_at=created_at,
        total_steps=0,
        progress=0,
        current_step="重新执行中",
        data_files=data_files,
        project_name=project_name,
        knowledge_base_id=knowledge_base_ids[0] if knowledge_base_ids else None,
        knowledge_base_ids=knowledge_base_ids,
        template=template,
        workflow_type=workflow_type,
        mode=mode,
        rerun_of=task_id,
    )

    # 启动异步工作流
    asyncio.create_task(_run_workflow(
        task_id=new_task_id,
        problem_text=problem_text,
        workflow=None,
        data_files=data_files,
        mode=mode,
        project_name=project_name,
        knowledge_base_ids=knowledge_base_ids,
        template=template,
        workflow_type=workflow_type,
    ))

    return {
        "task_id": new_task_id,
        "rerun_of": task_id,
        "status": "running",
        "message": f"已基于历史任务 {task_id} 重新执行，使用当前系统配置",
        "template": template,
        "workflow_type": workflow_type,
    }


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """删除任务所有数据"""
    success = persistence_delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="not found")
    return {"task_id": task_id, "status": "deleted"}


@router.post("/batch-delete")
async def batch_delete_tasks(req: dict):
    """批量删除任务"""
    task_ids: List[str] = req.get("task_ids", [])
    if not task_ids:
        raise HTTPException(status_code=400, detail="task_ids不能为空")

    deleted = []
    failed = []
    for tid in task_ids:
        if persistence_delete_task(tid):
            deleted.append(tid)
        else:
            failed.append(tid)

    return {
        "deleted_count": len(deleted),
        "failed_count": len(failed),
        "deleted": deleted,
        "failed": failed,
    }


@router.post("/export")
async def export_task_output(req: dict):
    """导出任务结果到桌面文件夹（以赛题名称命名）"""
    task_id: str = req.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id不能为空")

    # 获取任务结果
    result = load_task_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="任务结果不存在")

    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="任务元数据不存在")

    # 获取问题文本，提取赛题名称作为文件夹名
    problem_text = meta.get("problem_text", "")
    # 从问题文本中提取标题（取前80字符，移除特殊字符）
    import re
    folder_name = problem_text[:100].replace("\n", " ").strip()
    folder_name = re.sub(r'[\\/:*?"<>|]', '_', folder_name)
    if len(folder_name) > 50:
        folder_name = folder_name[:50]
    if not folder_name:
        folder_name = f"赛题_{task_id}"

    # 使用项目输出目录替代桌面路径，避免绑定用户主目录
    export_root = get_project_output_dir(project_name or task_id) / "exports"
    output_dir = export_root / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    output_files = []

    # 1. 导出 LaTeX 论文
    latex_code = result.get("output", {}).get("latex_code") or result.get("latex_code")
    if latex_code:
        latex_file = output_dir / "paper.tex"
        latex_file.write_text(latex_code, encoding="utf-8")
        output_files.append(str(latex_file.name))

    # 2. 导出相关代码（solver生成的代码）
    solver_output = result.get("output", {}).get("solver_agent") or result.get("solver_agent")
    if solver_output:
        codes = solver_output.get("codes", [])
        codes.extend(solver_output.get("sub_problem_codes", []))
        for idx, code_item in enumerate(codes):
            if isinstance(code_item, dict):
                code_content = code_item.get("code", "")
                code_lang = code_item.get("language", "python")
                code_file = output_dir / f"code_sub{idx+1}.py"
                code_file.write_text(code_content, encoding="utf-8")
                output_files.append(str(code_file.name))

    # 3. 导出模型描述
    modeler_output = result.get("output", {}).get("modeler_agent") or result.get("modeler_agent")
    if modeler_output:
        models = modeler_output.get("sub_problem_models", [])
        model_desc_lines = []
        for m in models:
            model_desc_lines.append(f"### 子问题: {m.get('sub_problem_id', '')}")
            model_desc_lines.append(f"模型名称: {m.get('model_name', '')}")
            model_desc_lines.append(f"模型类型: {m.get('model_type', '')}")
            model_desc_lines.append(f"算法: {m.get('algorithm', '')}")
            model_desc_lines.append(f"描述: {m.get('description', '')}")
            model_desc_lines.append(f"决策变量: {m.get('decision_variables', '')}")
            model_desc_lines.append(f"目标函数: {m.get('objective_function', '')}")
            model_desc_lines.append("---")
        if model_desc_lines:
            models_file = output_dir / "models_description.md"
            models_file.write_text("\n".join(model_desc_lines), encoding="utf-8")
            output_files.append(str(models_file.name))

    # 4. 导出数据分析结果
    analyses = result.get("output", {}).get("analyses", []) or result.get("analyses", [])
    if analyses:
        analysis_file = output_dir / "data_analysis.json"
        analysis_file.write_text(json.dumps(analyses, ensure_ascii=False, indent=2), encoding="utf-8")
        output_files.append(str(analysis_file.name))

    # 5. 导出完整结果JSON
    full_result_file = output_dir / "full_result.json"
    full_result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    output_files.append(str(full_result_file.name))

    return {
        "success": True,
        "output_dir": str(output_dir.relative_to(PROJECT_ROOT)),
        "files": output_files,
        "file_count": len(output_files),
    }


@router.post("/{task_id}/pause")
async def pause_task(task_id: str):
    """暂停任务"""
    from ..core.task_persistence import load_task_metadata
    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在")

    status = meta.get("status", "")
    if status not in ["running", "phase1", "phase2"]:
        raise HTTPException(status_code=400, detail=f"当前状态不可暂停: {status}")

    orch = get_orchestrator()
    orch.pause_task(task_id, "用户手动暂停")

    from ..core.task_persistence import save_task_metadata
    save_task_metadata(
        task_id=task_id, problem_text=meta.get("problem_text", ""),
        status="paused", created_at=meta.get("created_at", ""),
        completed_at=datetime.now().isoformat(),
        total_steps=meta.get("total_steps", 0),
        progress=meta.get("progress", 0),
        current_step="已暂停（可手动修正）",
    )

    return {"task_id": task_id, "status": "paused", "message": "任务已暂停，各Agent输出已保存，可修正后继续"}


@router.post("/{task_id}/resume")
async def resume_task(task_id: str):
    """恢复任务"""
    from ..core.task_persistence import load_task_metadata
    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在")

    orch = get_orchestrator()
    paused_data = orch.get_pause_data(task_id)

    save_task_metadata(
        task_id=task_id, problem_text=meta.get("problem_text", ""),
        status="running", created_at=meta.get("created_at", ""),
        total_steps=meta.get("total_steps", 0),
        progress=meta.get("progress", 0),
        current_step="继续执行",
    )
    orch.resume_task(task_id)

    return {"task_id": task_id, "status": "running", "message": "任务已恢复", "paused_data_keys": list(paused_data.keys())}


@router.get("/{task_id}/pause-data")
async def get_pause_data(task_id: str):
    """获取暂停时的数据（用户可编辑）"""
    from ..core.task_persistence import load_task_metadata
    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在")

    orch = get_orchestrator()
    pause_data = orch.get_pause_data(task_id)

    return {
        "task_id": task_id,
        "paused": orch.is_paused(task_id),
        "pause_data": {
            "analyzer_agent": pause_data.get("analyzer_agent", {}),
            "data_agent": pause_data.get("data_agent", {}),
            "research_agent": pause_data.get("research_agent", {}),
            "modeler_agent": pause_data.get("modeler_agent", {}),
            "section_results": pause_data.get("section_results_template", []),
        },
        "pause_location": orch._task_paused_at.get(task_id, ""),
    }


@router.post("/{task_id}/edit-and-continue")
async def edit_and_continue(task_id: str, req: dict):
    """用户编辑暂停数据后继续执行"""
    from ..core.task_persistence import load_task_metadata, save_task_metadata

    meta = load_task_metadata(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在")

    edited_data = req.get("edited_data", {})
    phase = meta.get("phase", "phase1")

    orch = get_orchestrator()
    # 保存用户编辑的数据
    for key, value in edited_data.items():
        orch.update_pause_data(task_id, key, value)
    # 标记阶段1编辑数据
    if phase == "phase1":
        orch.update_pause_data(task_id, "phase1_edited", edited_data)

    orch.resume_task(task_id)

    save_task_metadata(
        task_id=task_id, problem_text=meta.get("problem_text", ""),
        status="running", created_at=meta.get("created_at", ""),
        total_steps=meta.get("total_steps", 0), progress=meta.get("progress", 0),
        current_step="继续执行",
    )

    return {"task_id": task_id, "status": "resumed", "message": "已应用编辑，任务继续执行"}


@router.post("/{task_id}/feedback")
async def submit_feedback(task_id: str, req: dict):
    """提交任务反馈，并提取经验教训存入 LessonsMemory"""
    result = load_task_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="任务结果不存在")

    feedback = req.get("feedback", {})
    count = add_lessons_from_task(task_id, result, feedback)

    return {
        "task_id": task_id,
        "lessons_added": count,
        "message": f"已保存 {count} 条经验教训",
    }
