"""Token 预算管理 — 防止多智能体上下文爆炸。"""
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


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
    "minimax": 128_000,
    "mimo": 128_000,
    "default": 128_000,
}


# 默认预算分配（百分比）
DEFAULT_BUDGET_ALLOCATION = {
    "system_prompt": 0.20,
    "user_query": 0.30,
    "knowledge_context": 0.15,
    "memory_context": 0.15,
    "agent_profile": 0.10,
    "react_history": 0.10,
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
    ):
        if self._initialized:
            return
        self.model_key = model_key
        self.total_budget = int(MODEL_CONTEXT_WINDOWS.get(model_key, MODEL_CONTEXT_WINDOWS["default"]) * safety_ratio)
        self.allocation = allocation or DEFAULT_BUDGET_ALLOCATION
        self.budgets: Dict[str, TokenBudget] = {}
        self._build_budgets()
        self._initialized = True

    def _build_budgets(self):
        """根据分配比例初始化各类别预算。"""
        self.budgets = {}
        for category, ratio in self.allocation.items():
            self.budgets[category] = TokenBudget(total=int(self.total_budget * ratio))

    def reconfigure(self, model_key: str, allocation: Optional[Dict[str, float]] = None):
        """运行时重新配置（切换模型时调用）。"""
        self.model_key = model_key
        self.total_budget = MODEL_CONTEXT_WINDOWS.get(model_key, MODEL_CONTEXT_WINDOWS["default"])
        if allocation:
            self.allocation = allocation
        self._build_budgets()
        logger.info(f"TokenBudgetManager 重新配置: model={model_key}, total={self.total_budget}")

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
        """简单估算 tokens（中文字符 1:1，英文词 1:1.3）。"""
        if not text:
            return 0
        # 粗略估算：先按字符数，再按常见中英文比例
        chars = len(text)
        return max(1, int(chars * 0.6))

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


def get_token_budget_manager(model_key: str = "default") -> TokenBudgetManager:
    """获取全局单例。"""
    return TokenBudgetManager(model_key=model_key)
