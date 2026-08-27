"""Auto-Compress Hook — 在每个 Agent 执行前自动压缩上下文。

设计目标：
- 当任意 Agent 的累计上下文（results dict）≥ max_context_length × ratio 时，
  自动触发 ``ContextCompressor.maybe_compress``，避免上下文爆炸。
- 默认 max_context_length = 500_000，推理 Agent 512_000，ratio = 0.9。
- 每 Agent 可单独设置 ``max_context_length`` 和 ``auto_compress_ratio``，
  未设置时用全局默认值。

接入方式：
1. 在 ``BaseAgent.execute()`` 中调用 ``auto_compress_if_needed(state, agent_name)``。
2. 或在 LangGraph orchestrator 的每个 node 前调用。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .context_compressor import (
    ContextCompressor,
    CompressorConfig,
    CompressionStats,
    estimate_tokens,
    get_compressor as _get_default_compressor,
)

logger = logging.getLogger(__name__)


# ==================== 配置 ====================


# 默认全局上下文长度。可通过环境变量覆盖。
DEFAULT_MAX_CONTEXT_LENGTH = int(
    os.getenv("LLM_MAX_CONTEXT_LENGTH", "500000")
)
DEFAULT_AUTO_COMPRESS_RATIO = float(
    os.getenv("LLM_AUTO_COMPRESS_RATIO", "0.9")
)

# 推理相关 Agent 用 512K（orchestrator / 建模 / 写作 / 代码生成 / 评审）
# 其余 Agent 用默认 256K
DEFAULT_REASONING_CONTEXT_LENGTH = int(
    os.getenv("LLM_REASONING_CONTEXT_LENGTH", "512000")
)

# 推理相关 Agent 名称列表
REASONING_AGENTS = {
    "orchestrator",
    "modeler", "modeler_v2",
    "writer", "writer_v2",
    "coder", "code_executor",
    "reviewer", "peer_reviewer",
    "literature_reviewer", "researcher",
    "statistician",
    "data_analyst",
    "methodology_expert",
}


@dataclass
class AgentContextPolicy:
    """单个 Agent 的上下文策略。

    全部字段可选；None 时用全局默认值。"""
    max_context_length: Optional[int] = None
    auto_compress_ratio: Optional[float] = None
    enabled: bool = True

    def effective_threshold(self, default_ctx: int, default_ratio: float) -> int:
        ctx = self.max_context_length if self.max_context_length else default_ctx
        ratio = self.auto_compress_ratio if self.auto_compress_ratio else default_ratio
        if ctx <= 0:
            return 0
        return int(ctx * ratio)


@dataclass
class AutoCompressConfig:
    """全局 auto-compress 配置。"""
    max_context_length: int = DEFAULT_MAX_CONTEXT_LENGTH
    auto_compress_ratio: float = DEFAULT_AUTO_COMPRESS_RATIO
    agent_policies: Dict[str, AgentContextPolicy] = field(default_factory=dict)
    # 强制压缩触发后的兜底：当累计 token 已超过 95% × ctx 时，跳过 L1 摘要直接 L2 截断
    hard_truncate_ratio: float = 0.95

    @property
    def threshold_tokens(self) -> int:
        return int(self.max_context_length * self.auto_compress_ratio)

    def for_agent(self, agent_name: str) -> AgentContextPolicy:
        return self.agent_policies.get(agent_name, AgentContextPolicy())


# ==================== Hook 主体 ====================


class AutoCompressHook:
    """在每个 Agent 执行前自动压缩上下文。

    使用方式：

    .. code-block:: python

        hook = AutoCompressHook(AutoCompressConfig(max_context_length=500_000))

        # 在每个 Agent 入口：
        stats = hook.before_agent(task_id, agent_name, results, llm_caller=agent.call_llm)
        if stats.level_used != "none":
            logger.info(f"compressed before {agent_name}: {stats}")

    或在 LangGraph 中包装 node：

    .. code-block:: python

        def wrapped_node(state):
            hook.before_agent(state["task_id"], "modeler", state["results"])
            return original_node(state)
    """

    def __init__(
        self,
        config: Optional[AutoCompressConfig] = None,
        compressor: Optional[ContextCompressor] = None,
    ):
        self.config = config or AutoCompressConfig()
        self.compressor = compressor or ContextCompressor(
            CompressorConfig(
                max_context_length=self.config.max_context_length,
                auto_compress_ratio=self.config.auto_compress_ratio,
            )
        )
        self._stats_log: Dict[str, list] = {}

    def before_agent(
        self,
        task_id: str,
        agent_name: str,
        results: Dict[str, Dict[str, Any]],
        llm_caller: Optional[Any] = None,
    ) -> CompressionStats:
        """在 Agent 执行前检查上下文，必要时压缩。

        Args:
            task_id: 任务 ID（去重 key）
            agent_name: 即将执行的 Agent 名称
            results: 当前累计的所有 Agent 输出（dict of dict）
            llm_caller: LLM 调用函数（用于 L1 摘要）

        Returns:
            :class:`CompressionStats`（level_used="none" 表示未触发压缩；
            仍填充 original_tokens 方便上游决策）
        """
        stats = CompressionStats()
        policy = self.config.for_agent(agent_name)
        if not policy.enabled:
            stats.original_tokens = sum(estimate_tokens(out) for out in results.values())
            stats.compressed_tokens = stats.original_tokens
            return stats

        ctx = policy.max_context_length or self.config.max_context_length
        ratio = policy.auto_compress_ratio or self.config.auto_compress_ratio
        threshold = int(ctx * ratio)

        total_tokens = sum(estimate_tokens(out) for out in results.values())
        stats.original_tokens = total_tokens

        if total_tokens < threshold:
            logger.debug(
                f"[AutoCompress] task={task_id} agent={agent_name}: "
                f"{total_tokens} < {threshold} (ctx={ctx}, ratio={ratio:.0%}), skip"
            )
            stats.compressed_tokens = total_tokens
            return stats

        logger.info(
            f"[AutoCompress] task={task_id} agent={agent_name}: "
            f"{total_tokens} >= {threshold} (ctx={ctx}, ratio={ratio:.0%}), "
            f"triggering compression"
        )

        stats = self.compressor.maybe_compress(
            task_id=f"{task_id}::{agent_name}",
            results=results,
            llm_caller=llm_caller,
            max_context_length=ctx,
            auto_compress_ratio=ratio,
        )

        # 记录
        self._stats_log.setdefault(task_id, []).append(
            {"agent": agent_name, "stats": stats}
        )

        # 兜底：若压缩后仍超 95% × ctx，直接硬截断
        post = sum(estimate_tokens(out) for out in results.values())
        hard_cap = int(ctx * self.config.hard_truncate_ratio)
        if post > hard_cap:
            logger.warning(
                f"[AutoCompress] task={task_id} agent={agent_name}: "
                f"post-compress still {post} > {hard_cap}, force L2"
            )
            self._force_l2(results, ctx)
            stats.saved_tokens = max(stats.saved_tokens, total_tokens - post)
            if stats.level_used == "none":
                stats.level_used = "L2"

        return stats

    def _force_l2(self, results: Dict[str, Dict[str, Any]], ctx: int) -> None:
        """兜底硬截断：把每个 Agent 的输出裁剪到 ctx/len(results) tokens。"""
        from .context_compressor import PROTECTED_FIELDS

        per_agent_cap = max(1000, ctx // max(1, len(results)))
        for agent_name, output in results.items():
            if not isinstance(output, dict):
                continue
            tokens = estimate_tokens(output)
            if tokens <= per_agent_cap:
                continue
            # protected 字段保留，其它字段整体截断到 per_agent_cap
            keep: Dict[str, Any] = {}
            budget = per_agent_cap
            for k, v in output.items():
                if k in PROTECTED_FIELDS:
                    keep[k] = v
                    budget -= estimate_tokens(v)
                    continue
                if budget <= 0:
                    continue
                if isinstance(v, str):
                    # 二分截断到 budget tokens
                    low, high = 0, len(v)
                    while low < high - 1:
                        mid = (low + high) // 2
                        if estimate_tokens(v[:mid]) <= budget:
                            low = mid
                        else:
                            high = mid
                    keep[k] = v[:low] + "...[hard]"
                    budget -= estimate_tokens(keep[k])
                elif isinstance(v, (list, dict)):
                    # 只保留前 1 个元素
                    if isinstance(v, list) and v:
                        keep[k] = v[:1]
                    elif isinstance(v, dict) and v:
                        first_key = next(iter(v))
                        keep[k] = {first_key: v[first_key]}
                    else:
                        keep[k] = v
                    budget -= estimate_tokens(keep[k])
                else:
                    keep[k] = v
                    budget -= 1
            results[agent_name] = keep

    def get_stats_log(self, task_id: str) -> list:
        return self._stats_log.get(task_id, [])

    def configure_minimax(self, max_context_length: int = 500_000, ratio: float = 0.9) -> None:
        """一键切到 MiniMax-M3 配置（500K 默认 / 512K 推理 / 90% 压缩）。"""
        self.config.max_context_length = max_context_length
        self.config.auto_compress_ratio = ratio
        self.compressor.config.max_context_length = max_context_length
        self.compressor.config.auto_compress_ratio = ratio
        # 更新推理 Agent 的 512K 策略
        for agent_name in REASONING_AGENTS:
            self.config.agent_policies[agent_name] = AgentContextPolicy(
                max_context_length=DEFAULT_REASONING_CONTEXT_LENGTH,
                auto_compress_ratio=ratio,
            )
        logger.info(
            f"[AutoCompress] reconfigured to MiniMax-M3: "
            f"default_ctx={max_context_length}, reasoning_ctx={DEFAULT_REASONING_CONTEXT_LENGTH}, "
            f"auto_compress_at={int(max_context_length * ratio)}"
        )


# ==================== 全局单例 ====================

_global_hook: Optional[AutoCompressHook] = None


def get_auto_compress_hook(
    max_context_length: Optional[int] = None,
    auto_compress_ratio: Optional[float] = None,
) -> AutoCompressHook:
    """获取全局 auto-compress hook 单例。

    第一次调用时按环境变量 / 传入参数初始化；之后复用同一实例。
    推理相关 Agent（orchestrator / modeler / writer / coder 等）使用 512K 上下文，
    其余 Agent 使用默认 256K。
    """
    global _global_hook
    if _global_hook is None:
        cfg = AutoCompressConfig(
            max_context_length=max_context_length or DEFAULT_MAX_CONTEXT_LENGTH,
            auto_compress_ratio=auto_compress_ratio or DEFAULT_AUTO_COMPRESS_RATIO,
        )
        # 为推理相关 Agent 注册 512K 策略
        for agent_name in REASONING_AGENTS:
            cfg.agent_policies[agent_name] = AgentContextPolicy(
                max_context_length=DEFAULT_REASONING_CONTEXT_LENGTH,
                auto_compress_ratio=auto_compress_ratio or DEFAULT_AUTO_COMPRESS_RATIO,
            )
        _global_hook = AutoCompressHook(cfg)
        logger.info(
            f"[AutoCompress] initialized: default={cfg.max_context_length}, "
            f"reasoning={DEFAULT_REASONING_CONTEXT_LENGTH}, "
            f"ratio={cfg.auto_compress_ratio}, "
            f"reasoning_agents={len(REASONING_AGENTS)}"
        )
    return _global_hook


def reset_auto_compress_hook() -> None:
    """重置 hook（用于测试或 reload）。"""
    global _global_hook
    _global_hook = None
