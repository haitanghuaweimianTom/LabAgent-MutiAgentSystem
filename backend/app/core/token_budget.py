"""Token 预算管理 — 防止多智能体上下文爆炸。"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ==================== tiktoken 精确计数（回退粗估）====================
try:
    import tiktoken  # type: ignore

    _TB_ENCODER: Any = None

    def _tb_encoder() -> Any:
        global _TB_ENCODER
        if _TB_ENCODER is None:
            _TB_ENCODER = tiktoken.get_encoding("cl100k_base")
        return _TB_ENCODER

    def _tb_count(text: str) -> int:
        try:
            return len(_tb_encoder().encode(text))
        except Exception:
            return max(1, int(len(text) * 0.6))
except Exception:  # tiktoken 未安装
    def _tb_count(text: str) -> int:
        return max(1, int(len(text) * 0.6))


class ContextOverflowError(Exception):
    """上下文超出预算，需要 Orchestrator 决策拆分/升级/确认。"""
    pass


# 模型上下文窗口（单位：tokens）
MODEL_CONTEXT_WINDOWS = {
    "claude-sonnet": 200_000,
    "claude-opus": 200_000,
    "claude-haiku": 200_000,
    "gpt-4": 128_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "kimi": 128_000,
    "minimax": 500_000,
    "minimax-m3": 500_000,
    "MiniMax-M3": 500_000,
    "default": 128_000,
}


# 默认预算分配（百分比）
# v7.1: 增加 react_history 到 15%，减少 user_query 到 20%
# 复杂任务的 ReAct 循环需要更多空间存放 tool call 历史
DEFAULT_BUDGET_ALLOCATION = {
    "system_prompt": 0.18,
    "user_query": 0.20,
    "knowledge_context": 0.12,
    "memory_context": 0.10,
    "agent_profile": 0.05,
    "react_history": 0.15,  # 从 0.08 增加到 0.15，支持复杂 ReAct 任务
    "user_feedback": 0.15,  # Human-in-the-loop 用户反馈
    "summary_buffer": 0.05,  # 新增：压缩摘要缓冲区
}


@dataclass
class TokenBudget:
    """单个类别的 token 预算。"""
    total: int
    used: int = 0

    def remaining(self) -> int:
        return max(0, self.total - self.used)

    def reserve(self, tokens: int) -> bool:
        if self.used + tokens > self.total:
            return False
        self.used += tokens
        return True

    def release(self, tokens: int):
        self.used = max(0, self.used - tokens)


class TokenBudgetManager:
    """单例 Token 预算管理器。

    为每次 LLM 调用分配上下文预算，按类别限制注入内容长度。
    """

    _instance: Optional["TokenBudgetManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        model_key: str = "default",
        allocation: Optional[Dict[str, float]] = None,
        safety_ratio: float = 0.85,
        max_context_length: Optional[int] = None,
        auto_compress_ratio: float = 0.9,
    ):
        if self._initialized:
            return
        self.model_key = model_key
        if max_context_length is not None and max_context_length > 0:
            base = max_context_length
        else:
            base = MODEL_CONTEXT_WINDOWS.get(model_key, MODEL_CONTEXT_WINDOWS["default"])
        self.max_context_length = base
        self.auto_compress_ratio = auto_compress_ratio
        self.auto_compress_threshold = int(base * auto_compress_ratio)
        self.total_budget = int(base * safety_ratio)
        self.allocation = allocation or DEFAULT_BUDGET_ALLOCATION
        self.budgets: Dict[str, TokenBudget] = {}
        self._build_budgets()
        self._initialized = True

    def _build_budgets(self):
        """根据分配比例初始化各类别预算。"""
        self.budgets = {}
        for category, ratio in self.allocation.items():
            self.budgets[category] = TokenBudget(total=int(self.total_budget * ratio))

    def reconfigure(
        self,
        model_key: str,
        allocation: Optional[Dict[str, float]] = None,
        max_context_length: Optional[int] = None,
        auto_compress_ratio: float = 0.9,
    ):
        """运行时重新配置（切换模型时调用）。"""
        self.model_key = model_key
        if max_context_length is not None and max_context_length > 0:
            base = max_context_length
        else:
            base = MODEL_CONTEXT_WINDOWS.get(model_key, MODEL_CONTEXT_WINDOWS["default"])
        self.max_context_length = base
        self.auto_compress_ratio = auto_compress_ratio
        self.auto_compress_threshold = int(base * auto_compress_ratio)
        self.total_budget = base
        if allocation:
            self.allocation = allocation
        self._build_budgets()
        logger.info(
            f"TokenBudgetManager 重新配置: model={model_key}, total={self.total_budget}, "
            f"auto_compress_at={self.auto_compress_threshold} ({auto_compress_ratio:.0%})"
        )

    def reserve(self, category: str, tokens: int) -> bool:
        """为某个类别预留 tokens，成功返回 True。"""
        budget = self.budgets.get(category)
        if not budget:
            return False
        return budget.reserve(tokens)

    def release(self, category: str, tokens: int):
        budget = self.budgets.get(category)
        if budget:
            budget.release(tokens)

    def remaining(self, category: str) -> int:
        budget = self.budgets.get(category)
        return budget.remaining() if budget else 0

    def total_remaining(self) -> int:
        return sum(b.remaining() for b in self.budgets.values())

    def check_overflow(self, extra_tokens: int = 0):
        """检查总预算是否溢出。"""
        if self.total_remaining() < extra_tokens:
            raise ContextOverflowError(
                f"上下文预算不足: 剩余 {self.total_remaining()} tokens, 需要 {extra_tokens}"
            )

    def estimate_tokens(self, text: str) -> int:
        """精确估算 tokens：优先 tiktoken(cl100k_base)，回退字符粗估。"""
        if not text:
            return 0
        return _tb_count(text)

    def clip_text(self, text: str, max_tokens: int, suffix: str = "\n...[已裁剪]") -> str:
        """将文本裁剪到指定 token 预算内。"""
        if self.estimate_tokens(text) <= max_tokens:
            return text
        # 二分查找合适的截断长度
        low, high = 0, len(text)
        while low < high - 1:
            mid = (low + high) // 2
            candidate = text[:mid] + suffix
            if self.estimate_tokens(candidate) <= max_tokens:
                low = mid
            else:
                high = mid
        return text[:low] + suffix

    def get_budget_report(self) -> Dict[str, Dict[str, int]]:
        return {
            cat: {"total": b.total, "used": b.used, "remaining": b.remaining()}
            for cat, b in self.budgets.items()
        }


def get_token_budget_manager(
    model_key: str = "default",
    max_context_length: Optional[int] = None,
    auto_compress_ratio: float = 0.9,
) -> TokenBudgetManager:
    """获取全局单例。

    Args:
        model_key: 模型 key（MODEL_CONTEXT_WINDOWS 中的键）。
        max_context_length: 自定义上下文长度（覆盖默认值），如 MiniMax-M3 的 500_000。
        auto_compress_ratio: 自动压缩阈值比例（0-1，默认 0.9）。
    """
    # Singleton: 在已经初始化的情况下，重新配置而不是新建实例。
    mgr = TokenBudgetManager.__new__(TokenBudgetManager)
    mgr.__init__(
        model_key=model_key,
        max_context_length=max_context_length,
        auto_compress_ratio=auto_compress_ratio,
    )
    return mgr
