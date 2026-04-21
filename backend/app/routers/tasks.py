"""任务路由"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..schemas import (
    TaskCreateRequest, TaskStatusResponse, TaskResultResponse,
    TaskCancelRequest, TaskStatus,
)
from ..agents import (
    Orchestrator, ResearchAgent, AnalyzerAgent, ModelerAgent,
    SolverAgent, WriterAgent, DataAgent,
)
from ..config import get_settings
from ..core.chat_room import get_chat_room
from ..core.runtime_config import get_runtime_api_key
from ..core.paths import get_data_dir
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

# 项目根目录（E:/cherryClaw/math_modeling_multi_agent/）
PROJECT_ROOT: Path = DATA_DIR.parent.parent.parent  # backend/data/uploads → backend/data → backend → 项目根


def reset_orchestrator() -> None:
    """重置Orchestrator，下次调用时会用最新的API密钥重新初始化"""
    global _orchestrator
    _orchestrator = None
    logger.info("Orchestrator 已重置，将在下次任务时用最新配置初始化")


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

        agents = {
            "research_agent": ResearchAgent(
                model=settings.default_model,
                api_key=api_key,
                api_base_url=settings.api_base_url,
                mcp_tools=get_agent_mcp_tools("research_agent"),
            ),
            "data_agent": DataAgent(
                model=settings.default_model,
                api_key=api_key,
                api_base_url=settings.api_base_url,
                data_dir=str(DATA_DIR),
            ),
            "analyzer_agent": AnalyzerAgent(
                model=settings.default_model,
                api_key=api_key,
                api_base_url=settings.api_base_url,
                mcp_tools=get_agent_mcp_tools("analyzer_agent"),
            ),
            "modeler_agent": ModelerAgent(
                model=settings.default_model,
                api_key=api_key,
                api_base_url=settings.api_base_url,
                mcp_tools=get_agent_mcp_tools("modeler_agent"),
            ),
            "solver_agent": SolverAgent(
                model=settings.default_model,
                api_key=api_key,
                api_base_url=settings.api_base_url,
                mcp_tools=get_agent_mcp_tools("solver_agent"),
            ),
            "writer_agent": WriterAgent(
                model=settings.default_model,
                api_key=api_key,
                api_base_url=settings.api_base_url,
            ),
        }
        _orchestrator = Orchestrator(agents=agents)
    return _orchestrator


def get_uploaded_files() -> list:
    """获取已上传的数据文件路径（从 uploads 目录和项目根目录）"""
    files = []

    # 1. 从 uploads 目录获取
    if DATA_DIR.exists():
        files.extend([str(f) for f in DATA_DIR.iterdir() if f.is_file()])

    # 2. 从项目根目录获取（附件1-4.xlsx 等数据文件）
    if PROJECT_ROOT.exists():
        for f in PROJECT_ROOT.iterdir():
            if f.is_file() and f.suffix in [".xlsx", ".xls", ".csv", ".json"]:
                # 跳过非数据文件
                if f.name.startswith("附件") or f.name in ["data.json", "problem.json"]:
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
    task_id = "task_" + uuid4().hex[:12]
    created_at = datetime.now().isoformat()
    orch = get_orchestrator()
    orch.task_history[task_id] = []

    # 持久化：保存任务元数据
    save_task_metadata(
        task_id=task_id,
        problem_text=req.problem_text,
        status="running",
        created_at=created_at,
        total_steps=0,
        progress=0,
        current_step="等待启动",
    )

    # 收集已上传的数据文件
    data_files = get_uploaded_files()
    logger.info(f"Task {task_id}: found {len(data_files)} data files")

    asyncio.create_task(_run_workflow(task_id, req.problem_text, req.workflow, data_files, req.mode))
    return {
        "task_id": task_id,
        "status": "running",
        "message": "任务已提交，开始执行",
        "created_at": created_at,
        "data_files_count": len(data_files),
    }


async def _run_workflow(task_id: str, problem_text: str, workflow, data_files: list, mode: str = "batch"):
    try:
        orch = get_orchestrator()
        # execute_workflow 内部会保存结果
        await orch.execute_workflow(task_id, problem_text, workflow, data_files=data_files, mode=mode)
        logger.info(f"Task {task_id} completed and saved")
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        save_task_metadata(
            task_id=task_id,
            problem_text=problem_text,
            status="failed",
            created_at=task_id.replace("task_", ""),
            completed_at=datetime.now().isoformat(),
            error=str(e),
        )


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

    async def gen():
        while True:
            status = orch.get_task_status(task_id)
            # 也检查持久化
            from ..core.task_persistence import load_task_metadata
            meta = load_task_metadata(task_id)

            if not status and not meta:
                data = json.dumps({"error": "not found"})
                yield "data: " + data + "\n\n"
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

            data = json.dumps({
                "task_id": task_id,
                "status": st,
                "progress": prog,
                "current_step": cur,
                "total_steps": tot,
            })
            yield "data: " + data + "\n\n"
            if st in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, "completed", "failed", "cancelled"]:
                break
            await asyncio.sleep(2)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


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
    data_files = get_uploaded_files()

    # 异步执行阶段1
    asyncio.create_task(_run_phase1_workflow(task_id, problem_text, data_files))

    return {"task_id": task_id, "status": "running", "phase": "phase1", "message": "阶段1执行中..."}


async def _run_phase1_workflow(task_id: str, problem_text: str, data_files: list):
    from ..core.task_persistence import load_task_metadata, save_task_result, save_task_metadata
    try:
        orch = get_orchestrator()
        result = await orch.execute_phase1(task_id, problem_text, data_files)
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
    data_files = get_uploaded_files()

    asyncio.create_task(_run_phase2_workflow(task_id, problem_text, sub_problems, data_files, mode))

    return {"task_id": task_id, "status": "running", "phase": "phase2", "mode": mode, "message": f"阶段2执行中（{'逐个递进' if mode == 'sequential' else '批量'}建模求解）..."}


async def _run_phase2_workflow(task_id: str, problem_text: str, sub_problems: List, data_files: list, mode: str = "batch"):
    from ..core.task_persistence import load_task_metadata, save_task_result, save_task_metadata
    try:
        orch = get_orchestrator()
        result = await orch.execute_phase2(task_id, problem_text, sub_problems, data_files, mode=mode)
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
    data_files = get_uploaded_files()

    asyncio.create_task(_run_phase2_workflow(task_id, problem_text, sub_problems, data_files))

    return {"task_id": task_id, "status": "running", "phase": "phase2", "message": f"开始批量建模求解{len(sub_problems)}个子问题..."}


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

    # 桌面路径
    desktop = Path.home() / "Desktop"
    output_dir = desktop / folder_name
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
        "output_dir": str(output_dir),
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
