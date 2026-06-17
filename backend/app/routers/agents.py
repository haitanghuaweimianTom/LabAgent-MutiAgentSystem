"""Agent路由 - Agent管理API"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["Agent管理"])

# 持久化文件路径
AGENT_CONFIG_FILE = Path(__file__).parent.parent.parent / "data" / "agent_configs.json"

# 默认 Agent 定义（model 留空，实际运行时从 agent_model_map / provider 获取）
TEAM: Dict[str, Dict[str, str]] = {
    "coordinator": {"name": "coordinator", "label": "协调者", "description": "项目负责人，制定计划协调进度", "model": ""},
    "research_agent": {"name": "research_agent", "label": "研究员", "description": "搜集文献和数据", "model": ""},
    "data_agent": {"name": "data_agent", "label": "数据分析师", "description": "数据分析与预处理", "model": ""},
    "analyzer_agent": {"name": "analyzer_agent", "label": "分析师", "description": "问题分析与任务分解", "model": ""},
    "modeler_agent": {"name": "modeler_agent", "label": "建模师", "description": "建立数学模型", "model": ""},
    "algorithm_engineer_agent": {"name": "algorithm_engineer_agent", "label": "算法工程师", "description": "设计创新算法与方法（CCF-A / 数学建模）", "model": ""},
    "financial_analyst_agent": {"name": "financial_analyst_agent", "label": "金融分析师", "description": "建立金融数学与量化模型", "model": ""},
    "solver_agent": {"name": "solver_agent", "label": "求解器", "description": "编程求解与验证", "model": ""},
    "writer_agent": {"name": "writer_agent", "label": "写作专家", "description": "生成完整LaTeX论文", "model": ""},
}

# Agent -> (provider_id, model_name) 映射，持久保存
agent_model_map: Dict[str, Dict[str, str]] = {}


def _load_agent_configs() -> None:
    """从磁盘加载 Agent 配置"""
    global agent_model_map
    if AGENT_CONFIG_FILE.exists():
        try:
            data = json.loads(AGENT_CONFIG_FILE.read_text("utf-8"))
            agent_model_map = data.get("agent_model_map", {})
            # 同步到 TEAM dict 的 model 字段
            for agent_name, mapping in agent_model_map.items():
                if agent_name in TEAM and "model" in mapping:
                    TEAM[agent_name]["model"] = mapping["model"]
            logger.info(f"从磁盘加载 {len(agent_model_map)} 个 Agent 配置")
        except Exception as e:
            logger.warning(f"加载 Agent 配置失败: {e}")


def _save_agent_configs() -> None:
    """保存 Agent 配置到磁盘"""
    AGENT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = AGENT_CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"agent_model_map": agent_model_map}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(AGENT_CONFIG_FILE)
    logger.info(f"Agent 配置已保存到 {AGENT_CONFIG_FILE}")


# 启动时加载
_load_agent_configs()


@router.get("")
async def list_agents() -> List[Dict[str, Any]]:
    """列出所有 Agent 及其当前模型配置"""
    from ..core.provider_config import get_custom_provider, get_default_provider_id

    default_provider_id = get_default_provider_id() or ""

    result: List[Dict[str, Any]] = []
    for name, info in TEAM.items():
        item: Dict[str, Any] = {"name": name}
        item.update(info)
        # 添加 provider/model 映射信息
        mapping = agent_model_map.get(name, {})
        if name in agent_model_map:
            # 该 Agent 已有独立配置（可能 provider_id 为空表示未指定）
            item["provider_id"] = mapping.get("provider_id", "")
            item["provider_model"] = mapping.get("model", info.get("model", ""))
        else:
            # 未配置过，回退到全局默认 provider 和默认模型
            item["provider_id"] = default_provider_id
            item["provider_model"] = info.get("model", "")
        # 添加 provider 名称
        pid = item["provider_id"]
        if pid:
            p = get_custom_provider(pid)
            item["provider_name"] = p.get("name", pid) if p else pid
        else:
            item["provider_name"] = ""
        result.append(item)
    return JSONResponse(content=result, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})


@router.get("/{agent_name}")
async def get_agent(agent_name: str) -> Dict[str, Any]:
    if agent_name not in TEAM:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
    from ..core.provider_config import get_default_provider_id
    item: Dict[str, Any] = {"name": agent_name}
    item.update(TEAM[agent_name])
    mapping = agent_model_map.get(agent_name, {})
    item["provider_id"] = mapping.get("provider_id", get_default_provider_id() or "")
    item["provider_model"] = mapping.get("model", TEAM[agent_name].get("model", ""))
    return item


@router.put("/{agent_name}/model")
async def update_model(agent_name: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """更新 Agent 的模型配置（包含 provider_id 和 model_name），持久保存"""
    if agent_name not in TEAM:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")

    new_model = body.get("model", "")
    provider_id = body.get("provider_id", "")
    if not new_model:
        raise HTTPException(status_code=400, detail="model required")

    # 更新内存
    TEAM[agent_name]["model"] = new_model
    agent_model_map[agent_name] = {
        "provider_id": provider_id,
        "model": new_model,
    }

    # 持久化到磁盘
    _save_agent_configs()

    # 重置 orchestrator 使新配置生效
    from .tasks import reset_orchestrator
    reset_orchestrator()

    logger.info(f"Agent {agent_name} 模型已更新: provider={provider_id}, model={new_model}")

    return {
        "agent": agent_name,
        "model": new_model,
        "provider_id": provider_id,
        "message": "模型配置已保存并持久化，Agent已重新初始化",
    }


@router.post("/{agent_name}/test-model")
async def test_agent_model(agent_name: str, body: Dict[str, Any] = None) -> Dict[str, Any]:
    """单独测试 Agent 当前配置的模型是否可用"""
    if agent_name not in TEAM:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")

    mapping = agent_model_map.get(agent_name, {})
    provider_id = (body or {}).get("provider_id") or mapping.get("provider_id", "")
    model_name = (body or {}).get("model") or mapping.get("model", TEAM[agent_name].get("model", ""))

    if not provider_id:
        return {"success": False, "error": "未配置 Provider，请先在 Agent 管理中设置 Provider"}

    from ..core.provider_config import get_custom_provider, build_test_config
    import httpx

    provider = get_custom_provider(provider_id)
    if not provider:
        return {"success": False, "error": f"Provider '{provider_id}' 不存在"}

    test_cfg = build_test_config(provider)
    test_cfg["model"] = model_name  # 使用 agent 指定的模型

    api_key = test_cfg.get("api_key", "")
    api_host = test_cfg.get("api_host", "")
    api_format = test_cfg.get("api_format", "openai_chat")
    auth_field = test_cfg.get("auth_field", "")

    if not api_host:
        return {"success": False, "error": "Provider api_host 为空"}

    try:
        if api_format == "anthropic":
            if auth_field == "anthropic_auth_token":
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
            else:
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
            payload = {"model": model_name, "max_tokens": 10, "messages": [{"role": "user", "content": "Hi"}]}
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{api_host}/v1/messages", headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                content = result.get("content", [{}])[0].get("text", "")
                return {"success": True, "response": content[:50], "model": model_name, "provider": provider_id, "latency_ms": int(response.elapsed.total_seconds() * 1000)}

        elif api_format == "ollama_chat":
            payload = {"model": model_name, "messages": [{"role": "user", "content": "Hi"}], "stream": False}
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{api_host}/api/chat", json=payload)
                response.raise_for_status()
                result = response.json()
                content = result.get("message", {}).get("content", "")
                return {"success": True, "response": content[:50], "model": model_name, "provider": provider_id, "latency_ms": int(response.elapsed.total_seconds() * 1000)}

        else:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"model": model_name, "messages": [{"role": "user", "content": "Say hi"}], "max_tokens": 10}
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{api_host}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content[:50], "model": model_name, "provider": provider_id, "latency_ms": int(response.elapsed.total_seconds() * 1000)}

    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP {e.response.status_code}", "detail": e.response.text[:300], "model": model_name, "provider": provider_id}
    except Exception as e:
        return {"success": False, "error": str(e), "model": model_name, "provider": provider_id}