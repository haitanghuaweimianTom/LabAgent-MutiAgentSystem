"""
数学建模多Agent系统 - 工作流路由（只读）

工作流已由模板自动绑定，本模块仅用于展示系统支持的预定义工作流：
- standard / quick / deep_research / code_focused / research_paper

注意：实际运行时由 LangGraph 编排器根据 template + workflow_type
动态裁剪 Agent，不走本文件中的静态 steps。
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ..schemas import WorkflowDefinition, WorkflowStep

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflows", tags=["工作流管理"])

# 预定义工作流（模板绑定，仅作展示，实际运行由 LangGraph 编排器处理）
PREDEFINED_WORKFLOWS: Dict[str, WorkflowDefinition] = {
    "standard": WorkflowDefinition(
        name="standard",
        description="标准论文生成流程（推荐）",
        steps=[
            WorkflowStep(agent="research_agent", input={"action": "search"}),
            WorkflowStep(agent="analyzer_agent", input={"action": "analyze"}),
            WorkflowStep(agent="modeler_agent", input={"action": "build_model"}),
            WorkflowStep(agent="solver_agent", input={"action": "solve"}),
            WorkflowStep(agent="writer_agent", input={"action": "write_paper"}),
        ],
    ),
    "quick": WorkflowDefinition(
        name="quick",
        description="快速生成（跳过研究阶段）",
        steps=[
            WorkflowStep(agent="analyzer_agent", input={"action": "analyze"}),
            WorkflowStep(agent="modeler_agent", input={"action": "build_model"}),
            WorkflowStep(agent="solver_agent", input={"action": "solve"}),
            WorkflowStep(agent="writer_agent", input={"action": "write_paper"}),
        ],
    ),
    "deep_research": WorkflowDefinition(
        name="deep_research",
        description="深度研究流程（强化资料搜集，跳过建模求解，适合调研/综述）",
        steps=[
            WorkflowStep(agent="research_agent", input={"action": "search", "query_type": "background"}),
            WorkflowStep(agent="research_agent", input={"action": "search", "query_type": "methods"}),
            WorkflowStep(agent="analyzer_agent", input={"action": "analyze"}),
            WorkflowStep(agent="writer_agent", input={"action": "write_paper"}),
        ],
    ),
    "code_focused": WorkflowDefinition(
        name="code_focused",
        description="代码优先流程（强化求解）",
        steps=[
            WorkflowStep(agent="research_agent", input={"action": "search"}),
            WorkflowStep(agent="analyzer_agent", input={"action": "analyze"}),
            WorkflowStep(agent="modeler_agent", input={"action": "build_model"}),
            WorkflowStep(agent="solver_agent", input={"action": "solve"}),
            WorkflowStep(agent="solver_agent", input={"action": "debug"}),
            WorkflowStep(agent="writer_agent", input={"action": "write_paper"}),
        ],
    ),
    "research_paper": WorkflowDefinition(
        name="research_paper",
        description="CCF-A 论文完整流程（含同行评议与修订）",
        steps=[
            WorkflowStep(agent="research_agent", input={"action": "search"}),
            WorkflowStep(agent="analyzer_agent", input={"action": "analyze"}),
            WorkflowStep(agent="modeler_agent", input={"action": "build_model"}),
            WorkflowStep(agent="solver_agent", input={"action": "solve"}),
            WorkflowStep(agent="writer_agent", input={"action": "write_paper"}),
            WorkflowStep(agent="peer_review_agent", input={"action": "review"}),
            WorkflowStep(agent="writer_agent", input={"action": "revise"}),
        ],
    ),
}


@router.get("", response_model=List[Dict[str, Any]])
async def list_workflows() -> List[Dict[str, Any]]:
    """列出所有预定义工作流（只读）。"""
    return [
        {**wf.model_dump(), "type": "predefined", "editable": False}
        for wf in PREDEFINED_WORKFLOWS.values()
    ]


@router.get("/{workflow_name}", response_model=Dict[str, Any])
async def get_workflow(workflow_name: str) -> Dict[str, Any]:
    """获取指定预定义工作流（只读）。"""
    wf = PREDEFINED_WORKFLOWS.get(workflow_name)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_name} not found")
    return {**wf.model_dump(), "type": "predefined", "editable": False}
