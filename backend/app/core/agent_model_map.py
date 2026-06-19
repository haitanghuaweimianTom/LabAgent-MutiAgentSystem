"""Agent × 模板 模型路由（Phase 7）。

不同任务阶段用不同模型以平衡质量 / 成本 / 速度：
- analyzer / modeler：逻辑强的模型
- solver：代码准的模型
- research：量大、容错的模型
- writer：成文质量高的模型（CCF-A 必须高质量）
- peer_review：4 维评分
- experimentation：产出方案即可

按 ``template_id`` 进一步覆盖：
- 旧 4 套模板（CUMCM / 课程 / 金融 / 综述）：用最低成本模型组合
- CCF-A 4 套模板：强制 writer 用高质量模型、peer_review 用强模型、solver 用强模型

路由结果通过 :class:`AgentModelRouter` 提供统一接口，
:func:`get_agent_model_router` 是全局单例。

零破窗：若未配置（默认），所有 Agent 走当前默认 Provider 的第一个可用模型（向后兼容）。
"""
from __future__ import annotations
import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# 默认模型组合（按 agent 维度）
# v5.0: 不再硬编码任何模型名称，默认空字符串表示"从 Provider 动态获取"
AGENT_DEFAULT_MODELS: Dict[str, str] = {
    "analyzer_agent": "",
    "data_agent": "",
    "modeler_agent": "",
    "solver_agent": "",
    "research_agent": "",
    "writer_agent": "",
    "peer_review_agent": "",
    "experimentation_agent": "",
}


# 按 template_id 覆盖（默认空，用户可动态配置）
TEMPLATE_OVERRIDES: Dict[str, Dict[str, str]] = {}


class AgentModelRouter:
    """线程安全的 Agent × Template 模型路由器。"""

    def __init__(
        self,
        base_map: Optional[Dict[str, str]] = None,
        template_overrides: Optional[Dict[str, Dict[str, str]]] = None,
    ):
        self._base = dict(base_map or AGENT_DEFAULT_MODELS)
        self._overrides = {k: dict(v) for k, v in (template_overrides or TEMPLATE_OVERRIDES).items()}
        self._lock = threading.RLock()
        # 运行时统计
        self._usage: Dict[str, int] = {}

    def get_model(
        self,
        agent_name: str,
        template_id: str = "math_modeling",
        default: str = "",
    ) -> str:
        """解析 ``(agent, template) -> model``。

        优先级：template override > agent 独立配置 > 默认 Provider 的第一个可用模型 > default > ''。
        """
        with self._lock:
            # 1. template override
            override = self._overrides.get(template_id) or {}
            if agent_name in override and override[agent_name]:
                model = override[agent_name]
            # 2. agent 独立配置（从 agent_configs.json 加载的）
            elif agent_name in self._base and self._base[agent_name]:
                model = self._base[agent_name]
            # 3. 动态获取默认 Provider 的第一个可用模型
            else:
                model = self._get_default_provider_model() or default

        with self._lock:
            if model:
                self._usage[model] = self._usage.get(model, 0) + 1
        return model

    def _get_default_provider_model(self) -> str:
        """从当前默认 Provider 获取第一个可用模型名称。"""
        try:
            from ..core.provider_config import get_default_provider
            dp = get_default_provider()
            if dp and dp.get("models"):
                for m in dp["models"]:
                    if m.get("enabled") and m.get("name"):
                        return m["name"]
                # 没有 enabled 的，返回第一个
                return dp["models"][0].get("name", "")
        except Exception:
            pass
        return ""

    def register_override(
        self, template_id: str, agent_name: str, model: str
    ) -> None:
        """运行时注册 / 覆盖（来自前端 Settings）。"""
        with self._lock:
            self._overrides.setdefault(template_id, {})[agent_name] = model

    def usage(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._usage)

    def summary(self, template_id: str = "math_modeling") -> Dict[str, str]:
        """返回当前 template 下的所有 agent -> model 映射（用于 Settings UI 展示）。"""
        with self._lock:
            return {
                agent: self.get_model(agent, template_id)
                for agent in AGENT_DEFAULT_MODELS.keys()
            }


# ==================== 单例 ====================

_router: Optional[AgentModelRouter] = None
_router_lock = threading.Lock()


def get_agent_model_router() -> AgentModelRouter:
    """获取全局路由器单例。"""
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                _router = AgentModelRouter()
    return _router


def reset_agent_model_router() -> None:
    """测试用：重置单例。"""
    global _router
    with _router_lock:
        _router = None
