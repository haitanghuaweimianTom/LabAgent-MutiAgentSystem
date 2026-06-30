"""AutoML 服务 —— 自动超参数搜索与优化。

核心能力：
- 基于 TPE（Tree-structured Parzen Estimator）的贝叶斯优化
- 支持多种搜索策略：TPE、随机搜索、网格搜索
- 与 ExperimentRunner 集成，支持 GPU 训练
- 自动记录搜索历史并推荐最优配置

v1.0: 轻量级实现，零外部依赖（纯 Python + numpy/scipy）。
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# 搜索空间定义
# =============================================================================

@dataclass
class HyperParameter:
    """单个超参数定义。"""

    name: str
    type: str  # "float", "int", "categorical", "log_float"
    low: Optional[float] = None
    high: Optional[float] = None
    choices: Optional[List[Any]] = None
    default: Optional[Any] = None

    def sample(self) -> Any:
        """从搜索空间中随机采样一个值。"""
        if self.type == "float":
            return random.uniform(self.low, self.high)
        elif self.type == "int":
            return random.randint(int(self.low), int(self.high))
        elif self.type == "log_float":
            log_low, log_high = np.log(self.low), np.log(self.high)
            return np.exp(random.uniform(log_low, log_high))
        elif self.type == "categorical":
            return random.choice(self.choices) if self.choices else None
        return self.default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "low": self.low,
            "high": self.high,
            "choices": self.choices,
            "default": self.default,
        }


@dataclass
class SearchSpace:
    """超参数搜索空间。"""

    params: List[HyperParameter] = field(default_factory=list)

    def sample_config(self) -> Dict[str, Any]:
        """随机采样一个完整配置。"""
        return {p.name: p.sample() for p in self.params}

    def add_float(self, name: str, low: float, high: float) -> "SearchSpace":
        self.params.append(HyperParameter(name=name, type="float", low=low, high=high))
        return self

    def add_int(self, name: str, low: int, high: int) -> "SearchSpace":
        self.params.append(HyperParameter(name=name, type="int", low=low, high=high))
        return self

    def add_log_float(self, name: str, low: float, high: float) -> "SearchSpace":
        self.params.append(HyperParameter(name=name, type="log_float", low=low, high=high))
        return self

    def add_categorical(self, name: str, choices: List[Any]) -> "SearchSpace":
        self.params.append(HyperParameter(name=name, type="categorical", choices=choices))
        return self


# =============================================================================
# TPE 贝叶斯优化（轻量级实现）
# =============================================================================

class TPEOptimizer:
    """Tree-structured Parzen Estimator 优化器。

    算法流程：
    1. 随机采样 n_startup_trials 个配置
    2. 按观测值分成好/坏两组（gamma 分位数）
    3. 为每个超参数分别拟合好/坏核密度估计（KDE）
    4. 选择使 EI(x) = p_good(x) / p_bad(x) 最大的 x 作为下一个候选
    5. 重复 2-4 直到达到最大迭代次数
    """

    def __init__(
        self,
        search_space: SearchSpace,
        n_startup_trials: int = 5,
        n_ei_candidates: int = 100,
        gamma: float = 0.25,
        random_state: Optional[int] = None,
    ):
        self.search_space = search_space
        self.n_startup_trials = n_startup_trials
        self.n_ei_candidates = n_ei_candidates
        self.gamma = gamma
        self.trials: List[Dict[str, Any]] = []
        self.random_state = random_state
        if random_state is not None:
            random.seed(random_state)
            np.random.seed(random_state)

    def _split_observations(self) -> Tuple[List[Dict], List[Dict]]:
        """将观测分成好/坏两组。"""
        if len(self.trials) < self.n_startup_trials:
            return [], self.trials

        sorted_trials = sorted(self.trials, key=lambda t: t["value"])
        n_good = max(1, int(len(sorted_trials) * self.gamma))
        good = sorted_trials[:n_good]
        bad = sorted_trials[n_good:]
        return good, bad

    def _kde_sample(self, values: List[float], low: float, high: float) -> float:
        """使用高斯核密度估计采样。"""
        if not values:
            return random.uniform(low, high)

        values = np.array(values)
        bandwidth = max(np.std(values) * 0.5, (high - low) * 0.05)
        if bandwidth == 0:
            bandwidth = (high - low) * 0.05

        # 从已有值中随机选一个，加高斯噪声
        base = random.choice(values)
        sample = np.random.normal(base, bandwidth)
        # 截断到边界
        return float(np.clip(sample, low, high))

    def _suggest_next(self) -> Dict[str, Any]:
        """建议下一个要评估的配置。"""
        good, bad = self._split_observations()

        if len(self.trials) < self.n_startup_trials or not good or not bad:
            # 随机探索阶段
            return self.search_space.sample_config()

        # 为每个超参数分别采样
        config = {}
        for param in self.search_space.params:
            good_values = [t["params"][param.name] for t in good if param.name in t["params"]]
            bad_values = [t["params"][param.name] for t in bad if param.name in t["params"]]

            if param.type == "categorical":
                # 对类别型，选择使 good/bad 比例最大的
                if not good_values or not bad_values:
                    config[param.name] = param.sample()
                    continue
                best_choice = None
                best_ratio = -1
                for choice in param.choices:
                    g_count = sum(1 for v in good_values if v == choice)
                    b_count = sum(1 for v in bad_values if v == choice)
                    ratio = (g_count + 1) / (b_count + 1)  # 加 1 平滑
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_choice = choice
                config[param.name] = best_choice
            else:
                # 对数值型，从 good 的分布采样
                low = param.low if param.low is not None else min(good_values)
                high = param.high if param.high is not None else max(good_values)
                if param.type == "log_float":
                    log_low, log_high = np.log(low), np.log(high)
                    log_values = [np.log(v) for v in good_values]
                    config[param.name] = np.exp(self._kde_sample(log_values, log_low, log_high))
                else:
                    config[param.name] = self._kde_sample(good_values, low, high)

        return config

    def optimize(
        self,
        objective: Callable[[Dict[str, Any]], float],
        max_trials: int = 20,
        direction: str = "maximize",
        progress_callback: Optional[Callable[[int, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """运行优化。

        Args:
            objective: 接收配置 dict，返回评估值（越大越好）
            max_trials: 最大评估次数
            direction: "maximize" 或 "minimize"
            progress_callback: 进度回调

        Returns:
            {
                "best_params": 最优配置,
                "best_value": 最优值,
                "trials": 所有试验记录,
                "history": 历史最佳值,
            }
        """
        for trial_id in range(max_trials):
            config = self._suggest_next()
            logger.info(f"[AutoML] Trial {trial_id + 1}/{max_trials}: {config}")

            try:
                value = objective(config)
            except Exception as e:
                logger.warning(f"[AutoML] Trial {trial_id + 1} 评估失败: {e}")
                value = float("-inf") if direction == "maximize" else float("inf")

            trial = {
                "trial_id": trial_id,
                "params": config,
                "value": value if direction == "maximize" else -value,
            }
            self.trials.append(trial)

            if progress_callback:
                progress_callback(trial_id, trial)

        # 找出最优
        best_trial = max(self.trials, key=lambda t: t["value"])
        best_value = best_trial["value"] if direction == "maximize" else -best_trial["value"]

        return {
            "best_params": best_trial["params"],
            "best_value": best_value,
            "trials": self.trials,
            "history": [
                {
                    "trial_id": t["trial_id"],
                    "value": t["value"] if direction == "maximize" else -t["value"],
                }
                for t in self.trials
            ],
            "n_trials": max_trials,
            "direction": direction,
        }


# =============================================================================
# 其他搜索策略
# =============================================================================

class RandomSearchOptimizer:
    """随机搜索优化器（基线对比用）。"""

    def __init__(self, search_space: SearchSpace, random_state: Optional[int] = None):
        self.search_space = search_space
        if random_state is not None:
            random.seed(random_state)

    def optimize(
        self,
        objective: Callable[[Dict[str, Any]], float],
        max_trials: int = 20,
        direction: str = "maximize",
    ) -> Dict[str, Any]:
        trials = []
        for trial_id in range(max_trials):
            config = self.search_space.sample_config()
            try:
                value = objective(config)
            except Exception as e:
                logger.warning(f"[AutoML Random] Trial {trial_id + 1} 失败: {e}")
                value = float("-inf") if direction == "maximize" else float("inf")
            trials.append({"trial_id": trial_id, "params": config, "value": value})

        best = max(trials, key=lambda t: t["value"]) if direction == "maximize" else min(trials, key=lambda t: t["value"])
        return {
            "best_params": best["params"],
            "best_value": best["value"],
            "trials": trials,
            "n_trials": max_trials,
            "direction": direction,
            "strategy": "random_search",
        }


class GridSearchOptimizer:
    """网格搜索优化器（适用于小搜索空间）。"""

    def __init__(self, search_space: SearchSpace):
        self.search_space = search_space

    def optimize(
        self,
        objective: Callable[[Dict[str, Any]], float],
        max_trials: int = 20,
        direction: str = "maximize",
    ) -> Dict[str, Any]:
        # 生成网格点
        grids = []
        for param in self.search_space.params:
            if param.type == "categorical":
                grids.append([(param.name, c) for c in param.choices])
            elif param.type == "int":
                n = min(5, int(param.high - param.low) + 1)
                vals = np.linspace(param.low, param.high, n, dtype=int)
                grids.append([(param.name, int(v)) for v in vals])
            else:
                n = 5
                vals = np.linspace(param.low, param.high, n)
                grids.append([(param.name, float(v)) for v in vals])

        # 笛卡尔积（限制数量）
        from itertools import product
        all_configs = list(product(*grids))[:max_trials]

        trials = []
        for trial_id, combo in enumerate(all_configs):
            config = {name: val for name, val in combo}
            try:
                value = objective(config)
            except Exception as e:
                logger.warning(f"[AutoML Grid] Trial {trial_id + 1} 失败: {e}")
                value = float("-inf") if direction == "maximize" else float("inf")
            trials.append({"trial_id": trial_id, "params": config, "value": value})

        best = max(trials, key=lambda t: t["value"]) if direction == "maximize" else min(trials, key=lambda t: t["value"])
        return {
            "best_params": best["params"],
            "best_value": best["value"],
            "trials": trials,
            "n_trials": len(trials),
            "direction": direction,
            "strategy": "grid_search",
        }


# =============================================================================
# AutoML 服务主类
# =============================================================================

class AutoMLService:
    """AutoML 服务 —— 统一接口。

    使用示例：
        space = SearchSpace()
            .add_log_float("lr", 1e-5, 1e-1)
            .add_int("batch_size", 16, 128)
            .add_categorical("optimizer", ["sgd", "adam", "adamw"])
            .add_float("dropout", 0.0, 0.5)

        service = AutoMLService(space)
        result = service.search(
            objective=lambda cfg: train_and_eval(cfg),
            max_trials=20,
            strategy="tpe",
        )
    """

    def __init__(self, search_space: SearchSpace):
        self.search_space = search_space

    def search(
        self,
        objective: Callable[[Dict[str, Any]], float],
        max_trials: int = 20,
        strategy: str = "tpe",
        direction: str = "maximize",
        random_state: Optional[int] = 42,
        progress_callback: Optional[Callable[[int, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """运行超参数搜索。

        Args:
            objective: 目标函数，接收配置 dict，返回标量值
            max_trials: 最大评估次数
            strategy: "tpe", "random", "grid"
            direction: "maximize" 或 "minimize"
            random_state: 随机种子
            progress_callback: 进度回调

        Returns:
            搜索结果 dict
        """
        logger.info(f"[AutoML] 开始搜索: strategy={strategy}, max_trials={max_trials}, direction={direction}")

        if strategy == "tpe":
            optimizer = TPEOptimizer(self.search_space, random_state=random_state)
            result = optimizer.optimize(objective, max_trials, direction, progress_callback)
        elif strategy == "random":
            optimizer = RandomSearchOptimizer(self.search_space, random_state=random_state)
            result = optimizer.optimize(objective, max_trials, direction)
        elif strategy == "grid":
            optimizer = GridSearchOptimizer(self.search_space)
            result = optimizer.optimize(objective, max_trials, direction)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        result["strategy"] = strategy
        result["search_space"] = [p.to_dict() for p in self.search_space.params]
        logger.info(f"[AutoML] 搜索完成: best_value={result['best_value']:.4f}")
        return result

    def get_recommendation_report(self, result: Dict[str, Any]) -> str:
        """生成人类可读的建议报告。"""
        lines = [
            "# AutoML 超参数搜索报告",
            "",
            f"**搜索策略**: {result['strategy']}",
            f"**评估次数**: {result['n_trials']}",
            f"**优化方向**: {result['direction']}",
            f"**最优值**: {result['best_value']:.4f}",
            "",
            "## 最优超参数配置",
            "",
        ]
        for name, value in result["best_params"].items():
            lines.append(f"- **{name}**: `{value}`")
        lines.append("")
        lines.append("## 搜索历史")
        lines.append("")
        lines.append("| Trial | Value | Key Params |")
        lines.append("|-------|-------|------------|")
        for t in result["trials"][:10]:
            params_str = ", ".join([f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}" for k, v in list(t["params"].items())[:3]])
            val = t["value"] if result["direction"] == "maximize" else -t["value"]
            lines.append(f"| {t['trial_id']} | {val:.4f} | {params_str} |")
        return "\n".join(lines)


# =============================================================================
# 便捷函数
# =============================================================================

def create_search_space_from_method(method: Dict[str, Any]) -> SearchSpace:
    """从 algorithm_engineer_agent 输出的方法描述中自动构建搜索空间。

    Args:
        method: algorithm_engineer_agent 的 proposed_method 输出

    Returns:
        SearchSpace 实例
    """
    space = SearchSpace()
    hps = method.get("hyperparameters", [])

    for hp in hps:
        if not isinstance(hp, dict):
            continue
        name = hp.get("name", "")
        default = hp.get("default", "")
        desc = hp.get("description", "")

        # 尝试从描述中推断范围
        if "learning rate" in desc.lower() or "lr" in name.lower():
            space.add_log_float(name, 1e-5, 1e-1)
        elif "batch" in name.lower():
            space.add_int(name, 8, 256)
        elif "epoch" in name.lower():
            space.add_int(name, 5, 200)
        elif "dropout" in name.lower():
            space.add_float(name, 0.0, 0.7)
        elif "weight decay" in desc.lower() or "decay" in name.lower():
            space.add_log_float(name, 1e-6, 1e-2)
        elif "momentum" in name.lower():
            space.add_float(name, 0.5, 0.99)
        elif "optimizer" in name.lower():
            space.add_categorical(name, ["sgd", "adam", "adamw", "rmsprop"])
        elif "activation" in name.lower():
            space.add_categorical(name, ["relu", "gelu", "swish", "leaky_relu"])
        else:
            # 默认尝试解析数值范围
            try:
                val = float(default)
                if val > 0:
                    low = max(val * 0.1, val - 10)
                    high = min(val * 10, val + 10)
                    if low > 0 and high / low > 10:
                        space.add_log_float(name, low, high)
                    else:
                        space.add_float(name, low, high)
                else:
                    space.add_float(name, val - 1, val + 1)
            except (ValueError, TypeError):
                space.add_categorical(name, [str(default), "auto"])

    return space


def run_automl_for_experiment(
    experiment_runner: Any,
    script_path: str,
    search_space: SearchSpace,
    max_trials: int = 10,
    strategy: str = "tpe",
) -> Dict[str, Any]:
    """为实验运行 AutoML 搜索。

    Args:
        experiment_runner: ExperimentRunner 实例
        script_path: 实验脚本路径
        search_space: 超参数搜索空间
        max_trials: 最大试验次数
        strategy: 搜索策略

    Returns:
        AutoML 搜索结果
    """
    service = AutoMLService(search_space)

    def objective(config: Dict[str, Any]) -> float:
        """目标函数：运行实验并返回验证准确率。"""
        from ..services.experiment_runner import ExperimentScript

        script = ExperimentScript(
            name="automl_trial",
            path=__import__("pathlib").Path(script_path),
            args=config,
            role="main",
        )
        result = experiment_runner._run_single(script, output_dir=None)
        if not result.success:
            return 0.0
        # 优先使用 accuracy，回退到其他指标
        metrics = result.metrics
        acc = metrics.get("accuracy", metrics.get("val_accuracy", metrics.get("f1", 0.0)))
        return float(acc) if acc else 0.0

    return service.search(
        objective=objective,
        max_trials=max_trials,
        strategy=strategy,
        direction="maximize",
    )
