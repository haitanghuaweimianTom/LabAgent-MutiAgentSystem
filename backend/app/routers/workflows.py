"""
数学建模多Agent系统 - 工作流路由

提供工作流管理API：
- 列出预定义工作流
- 创建自定义工作流
- 执行指定工作流
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from ..schemas import WorkflowDefinition, WorkflowStep

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflows", tags=["工作流管理"])

# 预定义工作流
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
        description="深度研究流程（强化资料搜集）",
        steps=[
            WorkflowStep(agent="research_agent", input={"action": "search", "query_type": "background"}),
            WorkflowStep(agent="research_agent", input={"action": "search", "query_type": "methods"}),
            WorkflowStep(agent="analyzer_agent", input={"action": "analyze"}),
            WorkflowStep(agent="modeler_agent", input={"action": "build_model"}),
            WorkflowStep(agent="solver_agent", input={"action": "solve"}),
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
}

# 用户自定义工作流（内存存储，生产环境应持久化）
_custom_workflows: Dict[str, WorkflowDefinition] = {}


@router.get("", response_model=List[Dict[str, Any]])
async def list_workflows() -> List[Dict[str, Any]]:
    """
    列出所有工作流（预定义+自定义）

    Returns:
        工作流列表
    """
    workflows = []

    # 添加预定义工作流
    for name, wf in PREDEFINED_WORKFLOWS.items():
        workflows.append({
            **wf.model_dump(),
            "type": "predefined",
            "editable": False,
        })

    # 添加自定义工作流
    for name, wf in _custom_workflows.items():
        workflows.append({
            **wf.model_dump(),
            "type": "custom",
            "editable": True,
        })

    return workflows


@router.get("/{workflow_name}", response_model=Dict[str, Any])
async def get_workflow(workflow_name: str) -> Dict[str, Any]:
    """
    获取指定工作流

    Args:
        workflow_name: 工作流名称

    Returns:
        工作流详情
    """
    wf = PREDEFINED_WORKFLOWS.get(workflow_name) or _custom_workflows.get(workflow_name)

    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_name} not found")

    return {
        **wf.model_dump(),
        "type": "predefined" if workflow_name in PREDEFINED_WORKFLOWS else "custom",
        "editable": workflow_name not in PREDEFINED_WORKFLOWS,
    }


@router.post("", response_model=Dict[str, Any])
async def create_workflow(workflow: WorkflowDefinition) -> Dict[str, Any]:
    """
    创建自定义工作流

    Args:
        workflow: 工作流定义

    Returns:
        创建结果
    """
    if workflow.name in PREDEFINED_WORKFLOWS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot override predefined workflow: {workflow.name}",
        )

    # 验证Agent名称
    valid_agents = ["research_agent", "analyzer_agent", "modeler_agent", "solver_agent", "writer_agent"]
    for step in workflow.steps:
        if step.agent not in valid_agents:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid agent name: {step.agent}",
            )

    _custom_workflows[workflow.name] = workflow
    logger.info(f"Created custom workflow: {workflow.name}")

    return {
        "success": True,
        "message": f"Workflow {workflow.name} created",
        "workflow": workflow.model_dump(),
    }


@router.put("/{workflow_name}", response_model=Dict[str, Any])
async def update_workflow(
    workflow_name: str,
    workflow: WorkflowDefinition,
) -> Dict[str, Any]:
    """
    更新自定义工作流

    Args:
        workflow_name: 工作流名称
        workflow: 新的工作流定义

    Returns:
        更新结果
    """
    if workflow_name in PREDEFINED_WORKFLOWS:
        raise HTTPException(
            status_code=400,
            detail="Cannot modify predefined workflows",
        )

    if workflow_name not in _custom_workflows:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_name} not found")

    workflow.name = workflow_name
    _custom_workflows[workflow_name] = workflow
    logger.info(f"Updated workflow: {workflow_name}")

    return {
        "success": True,
        "message": f"Workflow {workflow_name} updated",
        "workflow": workflow.model_dump(),
    }


@router.delete("/{workflow_name}", response_model=Dict[str, Any])
async def delete_workflow(workflow_name: str) -> Dict[str, Any]:
    """
    删除自定义工作流

    Args:
        workflow_name: 工作流名称

    Returns:
        删除结果
    """
    if workflow_name in PREDEFINED_WORKFLOWS:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete predefined workflows",
        )

    if workflow_name not in _custom_workflows:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_name} not found")

    del _custom_workflows[workflow_name]
    logger.info(f"Deleted workflow: {workflow_name}")

    return {
        "success": True,
        "message": f"Workflow {workflow_name} deleted",
    }
