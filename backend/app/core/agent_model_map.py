"""Agent × 模板 模型路由（Phase 7）。

不同任务阶段用不同模型以平衡质量 / 成本 / 速度：
- analyzer / modeler：sonnet（逻辑强）
- solver：sonnet（代码准）
- research：haiku（量大、容错）
- writer：opus（成文质量是天花板，CCF-A 必须 opus）
- peer_review：sonnet（4 维评分）
- experimentation：haiku（产出方案即可）

按 ``template_id`` 进一步覆盖：
- 旧 4 套模板（CUMCM / 课程 / 金融 / 综述）：用最低成本模型组合（默认 sonnet）
- CCF-A 4 套模板：强制 writer 用 opus、peer_review 用 sonnet、solver 用 sonnet

路由结果通过 :class:`AgentModelRouter` 提供统一接口，
:func:`get_agent_model_router` 是全局单例。

零破窗：若未配置（默认），所有 Agent 走 Settings.default_model（向后兼容）。
"""
from __future__ import annotations
import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# 默认模型组合（按 agent 维度）
# v4.2: 统一使用 mimo-V2-pro（Xiaomi MiMo，cc-switch 路由）
AGENT_DEFAULT_MODELS: Dict[str, str] = {
    "analyzer_agent": "mimo-V2-pro",
    "data_agent": "mimo-V2-pro",
    "modeler_agent": "mimo-V2-pro",
    "solver_agent": "mimo-V2-pro",
    "research_agent": "mimo-V2-pro",
    "writer_agent": "mimo-V2-pro",
    "peer_review_agent": "mimo-V2-pro",
    "experimentation_agent": "mimo-V2-pro",
}


# 按 template_id 覆盖（全部用 mimo-V2-pro）
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

        优先级：template override > base_map > default > ''。
        """
        with self._lock:
            override = self._overrides.get(template_id) or {}
            if agent_name in override:
                model = override[agent_name]
            elif agent_name in self._base:
                model = self._base[agent_name]
            else:
                model = default
        with self._lock:
            self._usage[model] = self._usage.get(model, 0) + 1
        return model

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
