"""Contextual Bandit — 基于 LinUCB 的自适应重试策略

将代码执行失败后的重试决策建模为 Contextual Bandit 问题：
- 上下文：错误类型、当前模式、尝试次数、历史指标趋势
- 动作：继续(同模式)、降级(restricted)、升级(jailbreak)、放弃
- 奖励：后续迭代指标提升为正，失败/无提升为负

替代原有固定规则的 Circuit Breaker 逻辑，实现自适应决策。

LinUCB 算法核心：
    对每个动作 a 维护 (A_a, b_a)，其中 A_a 是 d×d 正则矩阵，b_a 是 d 维奖励向量。
    选择动作：a* = argmax_a θ_a^T x + α √(x^T A_a^{-1} x)
    更新：A_a += x x^T, b_a += r x

参考：Li et al., "A Contextual-Bandit Approach to Personalized News Article Recommendation" (2010)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------- 动作空间 ----------
ACTIONS = {
    0: "continue",    # 继续当前模式重试
    1: "degrade",     # 降级为 restricted 模式
    2: "upgrade",     # 升级为 jailbreak 模式
    3: "abort",       # 放弃当前问题
}

# ---------- 上下文特征维度 ----------
# 特征向量编码：
# [error_count_normalized, mode_restricted, mode_jailbreak,
#  attempt_normalized, metric_trend_slope, metric_last, consecutive_failures]
FEATURE_DIM = 7


def _build_context(
    error_count: int,
    execution_mode: str,
    attempt: int,
    metrics_trend: List[float],
    max_errors: int = 5,
    max_attempts: int = 3,
) -> np.ndarray:
    """构建上下文特征向量

    Args:
        error_count: 连续错误次数
        execution_mode: 当前执行模式 ("restricted" | "jailbreak")
        attempt: 当前尝试次数
        metrics_trend: 历史指标值列表（最近几次迭代）
        max_errors: 错误次数归一化上限
        max_attempts: 尝试次数归一化上限

    Returns:
        shape (FEATURE_DIM,) 的特征向量
    """
    # 错误次数归一化到 [0, 1]
    err_norm = min(error_count / max_errors, 1.0)

    # 模式 one-hot
    mode_r = 1.0 if execution_mode == "restricted" else 0.0
    mode_j = 1.0 if execution_mode == "jailbreak" else 0.0

    # 尝试次数归一化
    att_norm = min(attempt / max_attempts, 1.0)

    # 指标趋势斜率（最近 3 个点的线性回归斜率）
    if len(metrics_trend) >= 2:
        recent = metrics_trend[-3:] if len(metrics_trend) >= 3 else metrics_trend
        x = np.arange(len(recent), dtype=float)
        slope = np.polyfit(x, recent, 1)[0] if len(recent) >= 2 else 0.0
    else:
        slope = 0.0

    # 最近一个指标值
    metric_last = metrics_trend[-1] if metrics_trend else 0.5

    # 连续失败次数（与 error_count 相同但上限不同）
    consec_fail = min(error_count / 3.0, 1.0)

    return np.array([
        err_norm, mode_r, mode_j, att_norm,
        slope, metric_last, consec_fail
    ], dtype=np.float64)


class LinUCBBandit:
    """LinUCB 上下文老虎机

    使用岭回归为每个动作维护参数估计，通过置信上界探索-利用。
    """

    def __init__(
        self,
        n_actions: int = 4,
        feature_dim: int = FEATURE_DIM,
        alpha: float = 0.5,
        save_path: Optional[str] = None,
    ):
        """
        Args:
            n_actions: 动作数量
            feature_dim: 上下文特征维度
            alpha: 探索参数（越大越探索）
            save_path: 模型持久化路径
        """
        self.n_actions = n_actions
        self.d = feature_dim
        self.alpha = alpha
        self.save_path = save_path

        # 每个动作维护 A (d×d) 和 b (d×1)
        self.A = [np.eye(self.d) for _ in range(self.n_actions)]
        self.b = [np.zeros(self.d) for _ in range(self.n_actions)]

        # 统计
        self._n_updates = 0
        self._action_counts = np.zeros(self.n_actions, dtype=int)

        # 加载已有模型
        if save_path and Path(save_path).exists():
            self._load()

    def select_action(self, context: np.ndarray) -> int:
        """选择动作

        a* = argmax_a θ_a^T x + α √(x^T A_a^{-1} x)

        Args:
            context: 上下文特征向量 (d,)

        Returns:
            选中的动作索引
        """
        ucb_values = np.zeros(self.n_actions)

        for a in range(self.n_actions):
            A_inv = np.linalg.inv(self.A[a])
            theta = A_inv @ self.b[a]

            # 期望奖励
            mean = theta @ context

            # 置信上界
            uncertainty = self.alpha * np.sqrt(context @ A_inv @ context)

            ucb_values[a] = mean + uncertainty

        # 选择 UCB 最大的动作
        action = int(np.argmax(ucb_values))

        # 记录日志
        logger.debug(
            f"LinUCB 选择动作: {ACTIONS[action]} "
            f"(UCBs={[f'{v:.3f}' for v in ucb_values]})"
        )

        return action

    def update(self, action: int, context: np.ndarray, reward: float):
        """更新参数

        A_a += x x^T
        b_a += r x

        Args:
            action: 执行的动作
            context: 上下文特征向量
            reward: 获得的奖励
        """
        self.A[action] += np.outer(context, context)
        self.b[action] += reward * context
        self._n_updates += 1
        self._action_counts[action] += 1

        logger.debug(
            f"LinUCB 更新: action={ACTIONS[action]}, reward={reward:.3f}, "
            f"total_updates={self._n_updates}"
        )

    def get_policy_summary(self) -> Dict[str, Any]:
        """获取当前策略摘要"""
        summary = {"actions": {}, "total_updates": self._n_updates}
        for a in range(self.n_actions):
            A_inv = np.linalg.inv(self.A[a])
            theta = A_inv @ self.b[a]
            summary["actions"][ACTIONS[a]] = {
                "count": int(self._action_counts[a]),
                "weights": theta.tolist(),
            }
        return summary

    def _save(self):
        """保存模型到文件"""
        if not self.save_path:
            return

        data = {
            "n_actions": self.n_actions,
            "d": self.d,
            "alpha": self.alpha,
            "A": [a.tolist() for a in self.A],
            "b": [bv.tolist() for bv in self.b],
            "n_updates": self._n_updates,
            "action_counts": self._action_counts.tolist(),
        }

        Path(self.save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.save_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"LinUCB 模型已保存: {self.save_path}")

    def _load(self):
        """从文件加载模型"""
        with open(self.save_path) as f:
            data = json.load(f)

        self.A = [np.array(a) for a in data["A"]]
        self.b = [np.array(bv) for bv in data["b"]]
        self._n_updates = data.get("n_updates", 0)
        self._action_counts = np.array(data.get("action_counts", [0] * self.n_actions))

        logger.info(f"LinUCB 模型已加载: {self.save_path} ({self._n_updates} 次更新)")


class ContextualBanditDecision:
    """Contextual Bandit 决策器 — 集成到 Orchestrator 的 reviewer_reflection 节点

    替代原有的固定规则熔断逻辑：
    - 原逻辑: error_count >= 3 → 降级; 连续2次无提升 → 升级
    - Bandit: 根据上下文自适应选择最优动作
    """

    def __init__(
        self,
        model_dir: Optional[str] = None,
        alpha: float = 0.5,
        reward_improvement: float = 1.0,
        reward_failure: float = -1.0,
        reward_no_change: float = -0.2,
    ):
        """
        Args:
            model_dir: 模型保存目录
            alpha: LinUCB 探索参数
            reward_improvement: 指标提升时的奖励
            reward_failure: 执行失败时的奖励
            reward_no_change: 指标无变化时的奖励
        """
        save_path = None
        if model_dir:
            save_path = str(Path(model_dir) / "contextual_bandit.json")

        self.bandit = LinUCBBandit(alpha=alpha, save_path=save_path)
        self.reward_improvement = reward_improvement
        self.reward_failure = reward_failure
        self.reward_no_change = reward_no_change

        # 用于计算 reward 的上一次状态
        self._last_metric: Optional[float] = None

    def decide(
        self,
        error_count: int,
        execution_mode: str,
        attempt: int,
        metrics_trend: List[float],
    ) -> Dict[str, Any]:
        """根据当前上下文做出决策

        Args:
            error_count: 连续错误次数
            execution_mode: 当前执行模式
            attempt: 当前尝试次数
            metrics_trend: 历史指标趋势

        Returns:
            {
                "action": str,           # "continue" | "degrade" | "upgrade" | "abort"
                "action_id": int,        # 0-3
                "context": list,         # 特征向量（用于后续更新）
                "reason": str,           # 决策理由
            }
        """
        context = _build_context(
            error_count=error_count,
            execution_mode=execution_mode,
            attempt=attempt,
            metrics_trend=metrics_trend,
        )

        action_id = self.bandit.select_action(context)
        action_name = ACTIONS[action_id]

        # 生成决策理由
        reason = self._generate_reason(action_name, error_count, execution_mode, attempt)

        return {
            "action": action_name,
            "action_id": action_id,
            "context": context.tolist(),
            "reason": reason,
        }

    def update_from_result(
        self,
        action_id: int,
        context_list: List[float],
        success: bool,
        metric_improved: bool,
        current_metric: Optional[float] = None,
    ):
        """根据执行结果更新 Bandit

        Args:
            action_id: 之前选择的动作
            context_list: 之前的上下文特征
            success: 本次执行是否成功
            metric_improved: 指标是否提升
            current_metric: 当前指标值
        """
        context = np.array(context_list)

        # 计算奖励
        if not success:
            reward = self.reward_failure
        elif metric_improved:
            reward = self.reward_improvement
        else:
            reward = self.reward_no_change

        self.bandit.update(action_id, context, reward)

        # 持久化（每 5 次更新保存一次）
        if self.bandit._n_updates % 5 == 0:
            self.bandit._save()

    def _generate_reason(
        self,
        action: str,
        error_count: int,
        execution_mode: str,
        attempt: int,
    ) -> str:
        """生成决策理由"""
        if action == "continue":
            return (
                f"Bandit 决策：继续当前 {execution_mode} 模式重试"
                f"（error_count={error_count}, attempt={attempt}）"
            )
        elif action == "degrade":
            return (
                f"Bandit 决策：降级为 restricted 模式"
                f"（error_count={error_count} 较高，尝试简化方案）"
            )
        elif action == "upgrade":
            return (
                f"Bandit 决策：升级为 jailbreak 模式"
                f"（{execution_mode} 模式下指标未提升，允许自由生成）"
            )
        else:  # abort
            return (
                f"Bandit 决策：放弃当前问题"
                f"（attempt={attempt} 已达上限，或连续失败过多）"
            )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "policy": self.bandit.get_policy_summary(),
            "last_metric": self._last_metric,
        }


# ---------- 离线评估工具 ----------
def offline_evaluate(
    logs: List[Dict[str, Any]],
    bandit: LinUCBBandit,
) -> float:
    """Importance Sampling 离线评估新策略的期望奖励

    Args:
        logs: 历史日志列表，每条包含:
            - context: 上下文特征
            - action: 实际执行的动作
            - reward: 获得的奖励
            - prob_taken: 执行时该动作的概率（若无则用均匀分布估计）
        bandit: 要评估的新策略

    Returns:
        期望奖励的 IS 估计
    """
    if not logs:
        return 0.0

    total_reward = 0.0
    for entry in logs:
        context = np.array(entry["context"])
        action = entry["action"]
        reward = entry["reward"]

        # 新策略下选择该动作的概率（简化：用 UCB 值近似）
        ucb_values = np.zeros(bandit.n_actions)
        for a in range(bandit.n_actions):
            A_inv = np.linalg.inv(bandit.A[a])
            theta = A_inv @ bandit.b[a]
            ucb_values[a] = theta @ context + bandit.alpha * np.sqrt(context @ A_inv @ context)

        # softmax 近似概率
        exp_ucb = np.exp(ucb_values - np.max(ucb_values))
        probs = exp_ucb / exp_ucb.sum()

        new_prob = probs[action]
        old_prob = entry.get("prob_taken", 1.0 / bandit.n_actions)

        if old_prob > 0:
            total_reward += reward * (new_prob / old_prob)

    return total_reward / len(logs)
