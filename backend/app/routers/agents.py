"""Agent路由 - Agent管理API"""
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List

router = APIRouter(prefix="/agents", tags=["Agent管理"])

TEAM: Dict[str, Dict[str, str]] = {
    "coordinator": {"name": "coordinator", "label": "协调者", "description": "项目负责人，制定计划协调进度", "model": "minimax-m2.7"},
    "research_agent": {"name": "research_agent", "label": "研究员", "description": "搜集文献和数据", "model": "minimax-m2.7"},
    "data_agent": {"name": "data_agent", "label": "数据分析师", "description": "数据分析与预处理", "model": "minimax-m2.7"},
    "analyzer_agent": {"name": "analyzer_agent", "label": "分析师", "description": "问题分析与任务分解", "model": "minimax-m2.7"},
    "modeler_agent": {"name": "modeler_agent", "label": "建模师", "description": "建立数学模型", "model": "minimax-m2.7"},
    "solver_agent": {"name": "solver_agent", "label": "求解器", "description": "编程求解与验证", "model": "minimax-m2.7"},
    "writer_agent": {"name": "writer_agent", "label": "写作专家", "description": "生成完整LaTeX论文", "model": "minimax-m2.7"},
}


@router.get("", response_model=List[Dict[str, str]])
async def list_agents() -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    for name, info in TEAM.items():
        item: Dict[str, str] = {"name": name}
        item.update(info)
        result.append(item)
    return result


@router.get("/{agent_name}", response_model=Dict[str, str])
async def get_agent(agent_name: str) -> Dict[str, str]:
    if agent_name not in TEAM:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
    item: Dict[str, str] = {"name": agent_name}
    item.update(TEAM[agent_name])
    return item


@router.put("/{agent_name}/model")
async def update_model(agent_name: str, body: Dict[str, Any]) -> Dict[str, str]:
    if agent_name not in TEAM:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
    new_model = body.get("model", "")
    if not new_model:
        raise HTTPException(status_code=400, detail="model required")
    TEAM[agent_name]["model"] = new_model
    return {"agent": agent_name, "model": new_model}
