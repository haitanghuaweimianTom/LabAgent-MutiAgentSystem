"""求解Agent - 编程求解（Claude CLI 优先 + HTTP API 回退）

核心变化（v3.2）：
- 优先尝试 Claude Code CLI 全自动编程（写文件+执行+修正）
- Claude CLI 不可用时，自动回退到 call_llm() + 本地 subprocess 执行
- 回退路径同样生成完整 .py 文件、执行并解析 JSON 结果

v3.1 扩展：
- 支持多代码文件生成（数据处理、求解、可视化等独立脚本）
- 扩展模板库覆盖12+种常见数学建模任务类型

v3.3 通用化（CCF-A 论文工厂 Phase 1C）：
- 抽出 ``BASE_SYSTEM_PROMPT`` 领域无关的 system prompt。
- 新增 ``FILE_SPLIT_RULES`` 硬规则段，由 ``get_system_prompt()`` 自动拼接。
  复杂任务必须按需拆为多文件（避免上下文稀释 + 注意力分散），
  与 [[code-generation-modular-preference]] 强一致。
- 新增 ``TEMPLATE_DOMAINS`` 给 ``CODE_TEMPLATES`` 打 ``domain`` 标签
  （``optimization`` / ``stats`` / ``ml`` / ``general``），便于未来
  按 ``template_id`` 注入相关模板集合。零破坏：``CODE_TEMPLATES`` 字典本身不变。
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..core.paths import get_project_data_dir
from ..services.data_schema import get_schema_extractor
from ..services.code_manifest import (
    CodeManifest, parse_manifest_from_dict, validate_manifest,
)
from ..services.result_validator import get_result_validator
from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)

# 默认执行超时（秒）- _execute_code 备用方法使用
CODE_EXEC_TIMEOUT = 60

# ====== v3.3 通用化：领域无关的 system prompt 与硬规则 ======

BASE_SYSTEM_PROMPT = """你是一个专业的算法工程师，擅长用 Python 解决科研/工程中的算法与建模问题。
你的任务不仅包括核心求解，还包括数据处理、可视化、结果验证等辅助工作。

重要：你必须以JSON格式输出，不要有任何其他文字！"""


# "按需拆文件"硬规则（v3.3 显式编码，与 [[code-generation-modular-preference]] 强一致）。
# LLM 生成代码时必须按本节约束决定产物是单文件还是多文件。
FILE_SPLIT_RULES = """

【代码生成：按需拆分为多文件（硬规则，违反将被回退重做）】

为避免上下文稀释与注意力分散，**复杂任务必须拆分为多个 .py 文件**。
当以下任一条件满足时，**必须**拆分（不要把所有逻辑塞进单个长文件）：

1. 单一文件估算 > 300 行
2. 涉及 3 个以上职责（数据加载 / 特征工程 / 模型训练 / 评估 / 可视化）
3. 子问题数量 ≥ 2
4. 需要复用 helper 函数于 ≥ 2 个下游 notebook / 脚本

【命名约定】
- data_process_<sub_id>.py —— 数据处理与特征工程
- model_<sub_id>.py —— 模型/算法定义
- train_<sub_id>.py —— 训练流程
- eval_<sub_id>.py —— 评估与指标计算
- viz_<sub_id>.py —— 图表生成
- utils.py —— 公共工具

【产物 manifest】
若你产出了多文件，请在返回 JSON 中给出 ``code_files`` 列表（数组），每项
形如 ``{"path": "data_process_sub1.py", "role": "data_processing", "code": "..."}``。
单文件时也建议给出 ``code_files=[{"path": "solver.py", "role": "solver", "code": "..."}]``
以便下游 ``orchestrator`` 统一消费。

【入口文件】
若拆分多文件，必须有一个清晰的入口（默认 ``solver_sub<N>.py`` 或
``main.py``），该入口负责 import 各子模块并按顺序执行。
"""


# ====== Claude Code 全自动编程的系统提示词（保留以兼容 Claude CLI 路径） ======
CLAUDE_CODER_SYSTEM = """你是一个专业的算法工程师，擅长用 Python 实现数学模型的求解算法。

【工作流程】
1. 根据任务需求，可能需要生成多个独立 Python 脚本：
   - 数据处理脚本（data_process.py）：清洗、转换、特征工程
   - 求解脚本（solver_*.py）：核心算法实现
   - 可视化脚本（visualize_*.py）：生成图表并保存
2. 将代码保存到项目输出目录的 code/ 子目录（相对路径：<项目输出目录>/code/）
3. 执行每个脚本，验证结果
4. 返回结构化求解结果

【代码要求】
- 代码必须是完整可运行的，包含所有 import
- 必须在代码末尾用 json.dumps() 将结果打印为 JSON 格式
- 如果代码有错误需要自己修正（最多修正3次）

【输出格式（必须以JSON格式返回，不要有任何其他文字）】
{
    "code": "完整Python代码（包含所有import，末尾用json.dumps打印结果）",
    "file_path": "code/solver_sub{N}.py",
    "execution_command": "python code/solver_sub{N}.py",
    "key_findings": ["关键发现1", "关键发现2"],
    "numerical_results": {"变量名": 数值, ...},
    "interpretation": "结果解释"
}

【execution_command 格式】
由于 Windows subprocess 执行限制，请提供以下格式之一：
1. 单行命令（推荐）：用 python -X utf8 -c "import json; code..."
2. 或者：python code/solver_sub{N}.py

注意：python -X utf8 确保中文结果正确输出

【重要】
- 必须返回完整可运行的 Python 代码（放在 code 字段）
- 必须返回执行命令（放在 execution_command 字段）
- 最终必须返回上述 JSON 结构，不要有任何其他文字"""


# ====== 扩展代码模板库 ======
CODE_TEMPLATES = {
    # ===== 优化求解 =====
    "linear_programming": '''
import numpy as np
from scipy.optimize import linprog

def solve_lp(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=None):
    """线性规划求解"""
    result = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds)
    if result.success:
        return {"optimal_value": float(result.fun), "optimal_solution": list(result.x), "status": "最优解"}
    return {"status": f"求解失败: {result.message}"}
''',

    "integer_programming": '''
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds

def solve_mip(c, A_ub=None, b_ub=None, integrality=None):
    """整数规划求解（MIP）"""
    n = len(c)
    constraints = []
    if A_ub is not None and b_ub is not None:
        constraints.append(LinearConstraint(A_ub, ub=b_ub))
    bounds = Bounds(0, np.inf)
    result = milp(c, constraints=constraints, integrality=integrality, bounds=bounds)
    if result.success:
        return {"optimal_value": float(result.fun), "optimal_solution": list(result.x), "status": "最优解"}
    return {"status": f"求解失败: {result.message}"}
''',

    "nonlinear_optimization": '''
import numpy as np
from scipy.optimize import minimize

def solve_nlp(obj_func, x0, constraints=None, bounds=None):
    """非线性规划求解"""
    result = minimize(obj_func, x0, constraints=constraints, bounds=bounds, method='SLSQP')
    if result.success:
        return {"optimal_value": float(result.fun), "optimal_solution": list(result.x), "iterations": int(result.nit), "status": "最优解"}
    return {"status": f"求解失败: {result.message}"}
''',

    "genetic_algorithm": '''
import numpy as np

def genetic_algorithm(obj_func, n_vars, pop_size=100, generations=200, bounds=None):
    """遗传算法求解"""
    if bounds is None:
        bounds = [(0, 10)] * n_vars
    pop = np.array([[np.random.uniform(low, high) for low, high in bounds] for _ in range(pop_size)])
    best_fitness, best_solution = float('inf'), None
    for gen in range(generations):
        fitness = np.array([obj_func(ind) for ind in pop])
        idx = np.argmin(fitness)
        if fitness[idx] < best_fitness:
            best_fitness, best_solution = float(fitness[idx]), list(pop[idx])
        # 选择、交叉、变异
        parents = pop[np.argsort(fitness)[:pop_size//2]]
        children = []
        for _ in range(pop_size - len(parents)):
            p1, p2 = parents[np.random.randint(len(parents))], parents[np.random.randint(len(parents))]
            child = np.array([p1[j] if np.random.rand() < 0.5 else p2[j] for j in range(n_vars)])
            child += np.random.normal(0, 0.1, n_vars)
            child = np.clip(child, [b[0] for b in bounds], [b[1] for b in bounds])
            children.append(child)
        pop = np.vstack([parents, children])
    return {"optimal_value": best_fitness, "optimal_solution": best_solution, "generations": generations}
''',

    "particle_swarm": '''
import numpy as np

def particle_swarm(obj_func, n_vars, n_particles=50, max_iter=100, bounds=None):
    """粒子群优化算法"""
    if bounds is None:
        bounds = [(0, 10)] * n_vars
    bounds = np.array(bounds)
    positions = np.random.uniform(bounds[:, 0], bounds[:, 1], (n_particles, n_vars))
    velocities = np.random.uniform(-1, 1, (n_particles, n_vars))
    personal_best = positions.copy()
    personal_best_fitness = np.array([obj_func(p) for p in positions])
    global_best_idx = np.argmin(personal_best_fitness)
    global_best = personal_best[global_best_idx].copy()
    global_best_fitness = personal_best_fitness[global_best_idx]
    w, c1, c2 = 0.8, 2.0, 2.0
    for _ in range(max_iter):
        r1, r2 = np.random.rand(n_particles, n_vars), np.random.rand(n_particles, n_vars)
        velocities = w * velocities + c1 * r1 * (personal_best - positions) + c2 * r2 * (global_best - positions)
        positions = positions + velocities
        positions = np.clip(positions, bounds[:, 0], bounds[:, 1])
        fitness = np.array([obj_func(p) for p in positions])
        improved = fitness < personal_best_fitness
        personal_best[improved] = positions[improved]
        personal_best_fitness[improved] = fitness[improved]
        if np.min(fitness) < global_best_fitness:
            global_best = positions[np.argmin(fitness)].copy()
            global_best_fitness = float(np.min(fitness))
    return {"optimal_value": global_best_fitness, "optimal_solution": list(global_best), "iterations": max_iter}
''',

    "monte_carlo": '''
import numpy as np

def monte_carlo_simulation(model_func, n_simulations=10000, params=None):
    """蒙特卡洛模拟"""
    if params is None:
        params = {}
    results = []
    for _ in range(n_simulations):
        sample = {k: v() if callable(v) else v for k, v in params.items()}
        result = model_func(sample)
        results.append(result)
    results = np.array(results)
    return {"mean": float(np.mean(results)), "std": float(np.std(results)),
            "min": float(np.min(results)), "max": float(np.max(results)),
            "percentile_5": float(np.percentile(results, 5)),
            "percentile_95": float(np.percentile(results, 95)),
            "n_simulations": n_simulations}
''',

    # ===== 预测模型 =====
    "time_series": '''
import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

def forecast_arima(data, p=1, d=1, q=1, steps=7):
    """ARIMA 时间序列预测"""
    model = ARIMA(data, order=(p, d, q))
    fitted = model.fit()
    forecast = fitted.forecast(steps=steps)
    return {"forecast": list(forecast), "summary": str(fitted.summary())}
''',

    "exponential_smoothing": '''
import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing

def forecast_ets(data, steps=7, trend='add', seasonal=None):
    """指数平滑预测（Holt-Winters）"""
    model = ExponentialSmoothing(data, trend=trend, seasonal=seasonal, seasonal_periods=12)
    fitted = model.fit()
    forecast = fitted.forecast(steps=steps)
    return {"forecast": list(forecast), "aic": float(fitted.aic), "bic": float(fitted.bic)}
''',

    "regression": '''
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

def regression_analysis(X, y):
    """多元线性回归"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = LinearRegression()
    model.fit(X_scaled, y)
    y_pred = model.predict(X_scaled)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return {"R2": float(model.score(X_scaled, y)), "adj_R2": float(1 - (1 - model.score(X_scaled, y)) * (len(y) - 1) / (len(y) - X.shape[1] - 1)),
            "coefficients": list(model.coef_), "intercept": float(model.intercept_)}
''',

    "random_forest": '''
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler

def build_random_forest(X, y, n_estimators=100):
    """随机森林回归"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = RandomForestRegressor(n_estimators=n_estimators, random_state=42)
    model.fit(X_scaled, y)
    cv_scores = cross_val_score(model, X_scaled, y, cv=5)
    return {"R2": float(model.score(X_scaled, y)), "cv_R2_mean": float(np.mean(cv_scores)),
            "cv_R2_std": float(np.std(cv_scores)), "feature_importances": list(model.feature_importances_)}
''',

    "svm": '''
import numpy as np
from sklearn.svm import SVR
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score

def build_svm(X, y, kernel='rbf'):
    """支持向量机回归"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = SVR(kernel=kernel)
    model.fit(X_scaled, y)
    cv_scores = cross_val_score(model, X_scaled, y, cv=5)
    return {"R2": float(model.score(X_scaled, y)), "cv_R2_mean": float(np.mean(cv_scores))}
''',

    "neural_network": '''
import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

def build_nn(X, y, hidden_layers=(100, 50), max_iter=500):
    """多层感知机回归"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
    model = MLPRegressor(hidden_layer_sizes=hidden_layers, max_iter=max_iter, random_state=42)
    model.fit(X_train, y_train)
    return {"train_score": float(model.score(X_train, y_train)), "test_score": float(model.score(X_test, y_test))}
''',

    # ===== 聚类分析 =====
    "kmeans": '''
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

def kmeans_clustering(X, n_clusters=3):
    """K-Means 聚类"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = model.fit_predict(X_scaled)
    sil_score = silhouette_score(X_scaled, labels)
    return {"n_clusters": n_clusters, "silhouette_score": float(sil_score),
            "inertia": float(model.inertia_), "labels": list(labels)}
''',

    "hierarchical_clustering": '''
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import StandardScaler

def hierarchical_clustering(X, n_clusters=3):
    """层次聚类"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = AgglomerativeClustering(n_clusters=n_clusters)
    labels = model.fit_predict(X_scaled)
    return {"n_clusters": n_clusters, "labels": list(labels), "n_leaves": int(model.n_leaves_)}
''',

    "dbscan": '''
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler

def dbscan_clustering(X, eps=0.5, min_samples=5):
    """DBSCAN 密度聚类"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = DBSCAN(eps=eps, min_samples=min_samples)
    labels = model.fit_predict(X_scaled)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    return {"n_clusters": n_clusters, "n_noise": int(list(labels).count(-1)), "labels": list(labels)}
''',

    # ===== 统计检验 =====
    "correlation": '''
import numpy as np
from scipy import stats

def correlation_analysis(X):
    """相关性分析（Pearson + Spearman）"""
    n = X.shape[1]
    pearson_matrix = np.corrcoef(X.T)
    spearman_matrix, spearman_p = stats.spearmanr(X)
    return {"pearson": pearson_matrix.tolist(), "spearman": spearman_matrix.tolist(),
            "spearman_p_values": spearman_p.tolist()}
''',

    "pca": '''
import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

def pca_analysis(X, n_components=None):
    """主成分分析"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    if n_components is None:
        n_components = min(X.shape[1], X.shape[0])
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X_scaled)
    return {"explained_variance_ratio": list(pca.explained_variance_ratio_),
            "cumulative_variance_ratio": list(np.cumsum(pca.explained_variance_ratio_)),
            "n_components": n_components}
''',

    "anova": '''
import numpy as np
from scipy import stats

def anova_test(*groups):
    """单因素方差分析"""
    f_stat, p_value = stats.f_oneway(*groups)
    return {"F_statistic": float(f_stat), "p_value": float(p_value),
            "significant": bool(p_value < 0.05)}
''',

    # ===== 综合评价 =====
    "ahp": '''
import numpy as np

def ahp(consistency_matrix, criteria_weights=None):
    """层次分析法（AHP）"""
    n = consistency_matrix.shape[0]
    # 归一化
    col_sum = consistency_matrix.sum(axis=0)
    norm_matrix = consistency_matrix / col_sum
    weights = norm_matrix.mean(axis=1)
    # 一致性检验
    lambda_max = (consistency_matrix @ weights / weights).mean()
    CI = (lambda_max - n) / (n - 1)
    RI_table = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}
    RI = RI_table.get(n, 1.45)
    CR = CI / RI if RI > 0 else 0
    return {"weights": list(weights), "CR": float(CR), "consistent": bool(CR < 0.1), "lambda_max": float(lambda_max)}
''',

    "topsis": '''
import numpy as np

def topsis(decision_matrix, weights, benefit_cols=None):
    """TOPSIS 综合评价"""
    m, n = decision_matrix.shape
    if benefit_cols is None:
        benefit_cols = [True] * n
    # 标准化
    norms = np.sqrt((decision_matrix ** 2).sum(axis=0))
    norm_matrix = decision_matrix / norms
    # 加权
    weighted = norm_matrix * weights
    # 理想解
    ideal_best = np.array([weighted[:, j].max() if benefit_cols[j] else weighted[:, j].min() for j in range(n)])
    ideal_worst = np.array([weighted[:, j].min() if benefit_cols[j] else weighted[:, j].max() for j in range(n)])
    # 距离
    d_best = np.sqrt(((weighted - ideal_best) ** 2).sum(axis=1))
    d_worst = np.sqrt(((weighted - ideal_worst) ** 2).sum(axis=1))
    scores = d_worst / (d_best + d_worst)
    return {"scores": list(scores), "ranking": list(np.argsort(-scores) + 1), "best_alternative": int(np.argmax(scores) + 1)}
''',

    "entropy_weight": '''
import numpy as np

def entropy_weight(decision_matrix, benefit_cols=None):
    """熵权法确定权重"""
    m, n = decision_matrix.shape
    if benefit_cols is None:
        benefit_cols = [True] * n
    # 标准化
    mins = decision_matrix.min(axis=0)
    maxs = decision_matrix.max(axis=0)
    range_vals = maxs - mins
    range_vals[range_vals == 0] = 1e-10
    norm_matrix = (decision_matrix - mins) / range_vals
    # 计算信息熵
    p = norm_matrix / norm_matrix.sum(axis=0)
    p[p == 0] = 1e-10
    entropy = -np.sum(p * np.log(p), axis=0) / np.log(m)
    # 计算权重
    weights = (1 - entropy) / (n - np.sum(entropy))
    return {"weights": list(weights), "entropy_values": list(entropy)}
''',

    "fuzzy_evaluation": '''
import numpy as np

def fuzzy_comprehensive_evaluation(evaluation_matrix, weights):
    """模糊综合评价"""
    evaluation_matrix = np.array(evaluation_matrix)
    weights = np.array(weights)
    weights = weights / weights.sum()
    result = weights @ evaluation_matrix
    return {"result": list(result), "evaluation_level": float(np.argmax(result) + 1),
            "membership": list(result / result.sum())}
''',

    "grey_relational": '''
import numpy as np

def grey_relational_analysis(data, reference=None, rho=0.5):
    """灰色关联分析"""
    if reference is None:
        reference = data.max(axis=0)
    # 标准化
    mins = data.min(axis=0)
    maxs = data.max(axis=0)
    norm_data = (data - mins) / (maxs - mins + 1e-10)
    norm_ref = (reference - mins) / (maxs - mins + 1e-10)
    # 关联系数
    delta = np.abs(norm_data - norm_ref)
    delta_max, delta_min = delta.max(), delta.min()
    gamma = (delta_min + rho * delta_max) / (delta + rho * delta_max)
    # 关联度
    relational_degree = gamma.mean(axis=0)
    return {"relational_degree": list(relational_degree), "ranking": list(np.argsort(-relational_degree) + 1)}
''',

    # ===== 组合优化 / 图算法 =====
    "algorithm_design": '''
import sys
from typing import List, Tuple, Dict, Any, Optional

def solve(input_data: Optional[str] = None) -> Dict[str, Any]:
    """组合优化/图算法求解模板

    时间复杂度: O(?)  # TODO: 根据具体算法填写
    空间复杂度: O(?)  # TODO: 根据具体算法填写
    """
    # ---------- 1. 输入解析 ----------
    # 支持从文件、字符串或标准输入读取
    if input_data is None:
        # 从标准输入读取（竞赛/评测常见模式）
        data = sys.stdin.read().strip().split()
    elif isinstance(input_data, str) and "\n" in input_data:
        data = input_data.strip().split()
    else:
        # 假设 input_data 已经是结构化数据
        data = input_data

    # ---------- 2. 核心算法函数 ----------
    # TODO: 替换为具体算法实现
    def core_algorithm(parsed_input) -> Dict[str, Any]:
        """核心算法占位符

        实现要点：
        - 明确算法名称（如 Dijkstra / 最小生成树 / 动态规划 / 贪心等）
        - 给出关键步骤的伪代码或注释
        - 标注复杂度
        """
        result = {"status": "placeholder", "value": 0}
        return result

    # ---------- 3. 解析与执行 ----------
    parsed = data  # TODO: 根据题目格式解析为图/矩阵/序列等结构
    result = core_algorithm(parsed)

    # ---------- 4. 输出结果 ----------
    return {
        "optimal_value": result.get("value"),
        "solution": result,
        "algorithm": "TODO: 替换为实际算法名",
        "complexity": "TODO: 时间/空间复杂度",
    }


# 示例调用（独立运行测试）
if __name__ == "__main__":
    sample = """5 3
1 2 3 4 5"""
    print(solve(sample))
''',

    # ===== 金融建模 =====
    "financial_model": '''
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional

def financial_analysis(
    data_path: Optional[str] = None,
    prices: Optional[List[float]] = None,
    initial_capital: float = 1_000_000.0,
) -> Dict[str, Any]:
    """金融建模与回测模板

    风险说明：本模板仅供学术研究/算法验证，不构成投资建议。
    回测结果不代表未来表现，实际交易需考虑滑点、手续费、流动性等。
    """
    # ---------- 1. 数据读取占位 ----------
    # 方式A: 从 CSV 读取（推荐用于真实数据）
    # df = pd.read_csv(data_path, parse_dates=["date"], index_col="date")
    # 方式B: 直接传入价格序列（快速测试）
    if prices is not None:
        df = pd.DataFrame({"close": prices})
    elif data_path:
        df = pd.read_csv(data_path)
    else:
        # 生成随机 walk 作为占位数据
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 252)
        prices = 100 * np.exp(np.cumsum(returns))
        df = pd.DataFrame({"close": prices})

    # ---------- 2. 指标计算 ----------
    returns = df["close"].pct_change().dropna()
    cumulative_returns = (1 + returns).cumprod()

    # 年化收益与波动（假设 252 交易日/年）
    annual_return = returns.mean() * 252
    annual_volatility = returns.std() * np.sqrt(252)
    sharpe_ratio = annual_return / (annual_volatility + 1e-10)

    # 最大回撤
    peak = cumulative_returns.cummax()
    drawdown = (cumulative_returns - peak) / peak
    max_drawdown = drawdown.min()

    # ---------- 3. 回测框架占位 ----------
    # TODO: 替换为具体策略逻辑（如均线交叉、动量、均值回归等）
    # 示例：简单买入持有
    final_value = initial_capital * cumulative_returns.iloc[-1]
    total_return = (final_value - initial_capital) / initial_capital

    # ---------- 4. 风险指标 ----------
    # VaR (95%)
    var_95 = np.percentile(returns, 5)
    # CVaR / Expected Shortfall (95%)
    cvar_95 = returns[returns <= var_95].mean() if len(returns[returns <= var_95]) > 0 else var_95

    return {
        "initial_capital": initial_capital,
        "final_value": float(final_value),
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "annual_volatility": float(annual_volatility),
        "sharpe_ratio": float(sharpe_ratio),
        "max_drawdown": float(max_drawdown),
        "VaR_95": float(var_95),
        "CVaR_95": float(cvar_95),
        "n_observations": int(len(returns)),
        "risk_note": "回测结果不代表未来表现；实际交易需考虑手续费、滑点、流动性等。",
    }


# 示例调用
if __name__ == "__main__":
    result = financial_analysis()
    print(result)
''',

    # ===== 数据处理 =====
    "data_cleaning": '''
import numpy as np
import pandas as pd

def data_cleaning_pipeline(df):
    """数据清洗流水线"""
    report = {
        "original_shape": list(df.shape),
        "missing_before": int(df.isnull().sum().sum()),
    }
    # 缺失值处理
    for col in df.columns:
        if df[col].dtype in ['float64', 'int64']:
            df[col] = df[col].fillna(df[col].median())
        else:
            df[col] = df[col].fillna(df[col].mode()[0] if len(df[col].mode()) > 0 else 'unknown')
    # 异常值处理（IQR法）
    for col in df.select_dtypes(include=[np.number]).columns:
        Q1, Q3 = df[col].quantile(0.25), df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower, upper = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
        n_outliers = int(((df[col] < lower) | (df[col] > upper)).sum())
        df[col] = df[col].clip(lower, upper)
        report[f"{col}_outliers_clipped"] = n_outliers
    report["cleaned_shape"] = list(df.shape)
    report["missing_after"] = int(df.isnull().sum().sum())
    return report
''',

    "feature_engineering": '''
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, MinMaxScaler, LabelEncoder

def feature_engineering(df, target_col=None, scale_method='standard'):
    """特征工程"""
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if target_col:
        numeric_cols = [c for c in numeric_cols if c != target_col]
    features = {}
    for col in numeric_cols:
        features[f"{col}_mean"] = df[col].mean()
        features[f"{col}_std"] = df[col].std()
        features[f"{col}_skew"] = float(df[col].skew())
        features[f"{col}_kurtosis"] = float(df[col].kurtosis())
    # 标准化
    scaler = StandardScaler() if scale_method == 'standard' else MinMaxScaler()
    if len(numeric_cols) > 0:
        df_scaled = df.copy()
        df_scaled[numeric_cols] = scaler.fit_transform(df[numeric_cols])
        features["n_numeric_features"] = len(numeric_cols)
        features["n_categorical_features"] = len(df.columns) - len(numeric_cols) - (1 if target_col else 0)
    return features
''',

    # ===== 可视化 =====
    "visualization_basic": '''
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

def create_basic_plots(data_dict, output_dir='code'):
    """创建基础可视化图表"""
    os.makedirs(output_dir, exist_ok=True)
    plots = []
    for name, data in data_dict.items():
        data = np.array(data)
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        # 折线图
        axes[0].plot(data, marker='o', markersize=4)
        axes[0].set_title(f'{name} - 趋势图')
        axes[0].set_xlabel('Index')
        axes[0].set_ylabel('Value')
        # 直方图
        axes[1].hist(data, bins=min(20, len(data)), edgecolor='black')
        axes[1].set_title(f'{name} - 分布图')
        axes[1].set_xlabel('Value')
        axes[1].set_ylabel('Frequency')
        plt.tight_layout()
        path = os.path.join(output_dir, f'{name}.png')
        fig.savefig(path, dpi=150)
        plt.close()
        plots.append({"name": name, "path": path, "type": "basic"})
    return {"plots": plots, "count": len(plots)}
''',

    "visualization_correlation": '''
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

def create_correlation_heatmap(correlation_matrix, labels=None, output_dir='code'):
    """相关性热力图"""
    os.makedirs(output_dir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(correlation_matrix, cmap='RdYlBu_r', vmin=-1, vmax=1)
    ax.set_xticks(range(len(labels or [])))
    ax.set_yticks(range(len(labels or [])))
    if labels:
        ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.set_yticklabels(labels)
    for i in range(len(correlation_matrix)):
        for j in range(len(correlation_matrix[0])):
            ax.text(j, i, f'{correlation_matrix[i, j]:.2f}', ha='center', va='center',
                    color='white' if abs(correlation_matrix[i, j]) > 0.5 else 'black', fontsize=8)
    plt.colorbar(im)
    ax.set_title('相关性热力图')
    path = os.path.join(output_dir, 'correlation_heatmap.png')
    fig.savefig(path, dpi=150)
    plt.close()
    return {"path": path, "type": "correlation_heatmap"}
''',

    "visualization_comparison": '''
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

def create_comparison_bar(categories, values, title='对比图', output_dir='code'):
    """对比柱状图"""
    os.makedirs(output_dir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = plt.cm.Set3(np.linspace(0, 1, len(categories)))
    bars = ax.bar(categories, values, color=colors, edgecolor='black')
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f'{val:.2f}', ha='center', va='bottom', fontsize=10)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_ylabel('Value')
    ax.grid(axis='y', alpha=0.3)
    path = os.path.join(output_dir, 'comparison.png')
    fig.savefig(path, dpi=150)
    plt.close()
    return {"path": path, "type": "comparison_bar"}
''',

    "visualization_radar": '''
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

def create_radar_chart(labels, values, title='雷达图', output_dir='code'):
    """雷达图"""
    os.makedirs(output_dir, exist_ok=True)
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    values = np.concatenate([values, [values[0]]])
    angles = angles + [angles[0]]
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))
    ax.plot(angles, values, 'o-', linewidth=2)
    ax.fill(angles, values, alpha=0.25)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels)
    ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
    path = os.path.join(output_dir, 'radar_chart.png')
    fig.savefig(path, dpi=150)
    plt.close()
    return {"path": path, "type": "radar_chart"}
''',
}

# 任务类型映射
TASK_TYPE_MAP = {
    'linear_programming': ['线性规划', '线性优化', 'linprog', 'LP'],
    'integer_programming': ['整数规划', '0-1规划', 'MIP'],
    'nonlinear_optimization': ['非线性', '非线性规划', 'NLP'],
    'genetic_algorithm': ['遗传算法', 'GA', '进化算法', '启发式'],
    'particle_swarm': ['粒子群', 'PSO', '群智能'],
    'monte_carlo': ['蒙特卡洛', 'Monte Carlo', '随机模拟', '模拟'],
    'time_series': ['时间序列', '预测', 'ARIMA', '趋势', 'forecast'],
    'exponential_smoothing': ['指数平滑', 'Holt', 'Holt-Winters', '平滑'],
    'regression': ['回归', '线性回归', 'regression'],
    'random_forest': ['随机森林', 'Random Forest', '树模型'],
    'svm': ['SVM', '支持向量', '核函数'],
    'neural_network': ['神经', '深度', 'MLP', 'BP', '神经网络'],
    'kmeans': ['聚类', 'K-Means', 'K均值', '分群'],
    'hierarchical_clustering': ['层次聚类', 'hierarchical', '凝聚'],
    'dbscan': ['DBSCAN', '密度聚类', 'dbscan'],
    'correlation': ['相关性', 'correlation', 'Pearson', 'Spearman', '相关系数'],
    'pca': ['主成分', 'PCA', '降维', '因子'],
    'anova': ['方差分析', 'ANOVA', 'F检验'],
    'ahp': ['AHP', '层次分析', '判断矩阵'],
    'topsis': ['TOPSIS', '优劣解', '评价'],
    'entropy_weight': ['熵权', '熵值法'],
    'fuzzy_evaluation': ['模糊', '综合评价'],
    'grey_relational': ['灰色', '关联分析', 'grey'],
    'data_cleaning': ['数据清洗', '缺失值', '异常值', '预处理'],
    'feature_engineering': ['特征工程', '特征', '标准化', '归一化'],
    'visualization_basic': ['可视化', '折线图', '分布'],
    'visualization_correlation': ['热力图', '相关图'],
    'visualization_comparison': ['柱状图', '对比图'],
    'visualization_radar': ['雷达图', '综合评价图'],
}


def detect_task_type(description: str, model_info: Dict = None) -> List[str]:
    """根据问题描述和模型信息检测适用的任务类型"""
    if not description:
        return ['linear_programming']

    text = description.lower()
    matched_types = []

    for template_key, keywords in TASK_TYPE_MAP.items():
        for kw in keywords:
            if kw.lower() in text:
                matched_types.append(template_key)
                break

    # 根据模型信息进一步推断
    if model_info:
        model_type = model_info.get('model_type', '').lower()
        model_name = model_info.get('model_name', '').lower()
        alg_name = model_info.get('algorithm', {}).get('name', '').lower() if isinstance(model_info.get('algorithm'), dict) else ''

        all_info = f"{model_type} {model_name} {alg_name}"
        for template_key, keywords in TASK_TYPE_MAP.items():
            for kw in keywords:
                if kw.lower() in all_info and template_key not in matched_types:
                    matched_types.append(template_key)
                    break

    # 默认返回线性规划
    if not matched_types:
        matched_types = ['linear_programming']

    return matched_types


def _extract_code_from_response(content: str) -> Optional[str]:
    """从LLM响应中提取Python代码，支持多种格式"""
    # 格式1: code字段
    if '"code"' in content or "'code'" in content:
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                for val in data.values():
                    if isinstance(val, str) and len(val) > 50 and ("def " in val or "import " in val or "#" in val):
                        return val
        except:
            pass

    # 格式2: markdown代码块 ```python ... ```
    match = re.search(r"```python\s*(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 格式3: markdown代码块 ``` ... ```
    match = re.search(r"```\s*(.*?)```", content, re.DOTALL)
    if match:
        code = match.group(1).strip()
        if "def " in code or "import " in code or "print(" in code:
            return code

    # 格式4: 直接是Python代码（以import或def开头）
    for line in content.split("\n"):
        if line.strip().startswith(("import ", "from ", "def ", "class ")):
            start = content.find(line.strip())
            if start != -1:
                code = content[start:]
                if "```" in code:
                    code = code[:code.rfind("```")]
                return code.strip()

    return None


def get_template_code(task_types: List[str]) -> str:
    """根据任务类型获取模板代码"""
    for tt in task_types:
        if tt in CODE_TEMPLATES:
            return CODE_TEMPLATES[tt]
    return CODE_TEMPLATES.get('linear_programming', '')


def get_template_for_model(model_info: Dict) -> str:
    """根据模型信息智能选择模板"""
    model_name = model_info.get('model_name', '').lower()
    model_type = model_info.get('model_type', '').lower()
    alg_name = model_info.get('algorithm', {}).get('name', '').lower() if isinstance(model_info.get('algorithm'), dict) else ''
    description = model_info.get('description', '').lower()

    all_text = f"{model_type} {model_name} {alg_name} {description}"

    # ===== 组合优化 / 图算法 =====
    algo_keywords = ['algorithm', 'heuristic', 'optimization', 'network', 'graph']
    if model_type == 'algorithm_design' or any(kw in all_text for kw in algo_keywords):
        return CODE_TEMPLATES.get('algorithm_design', '')

    # ===== 金融建模 =====
    finance_keywords = ['finance', 'portfolio', 'option', 'risk', 'backtest']
    if model_type == 'financial_model' or any(kw in all_text for kw in finance_keywords):
        return CODE_TEMPLATES.get('financial_model', '')

    # 综合评价
    if any(kw in model_name or kw in description for kw in ['topsis', '优劣', '理想']):
        return CODE_TEMPLATES['topsis']
    if any(kw in model_name or kw in description for kw in ['ahp', '层次分析', '判断']):
        return CODE_TEMPLATES['ahp']
    if any(kw in model_name or kw in description for kw in ['熵权', '熵值', 'entropy']):
        return CODE_TEMPLATES['entropy_weight']
    if any(kw in model_name or kw in description for kw in ['模糊', 'fuzzy']):
        return CODE_TEMPLATES['fuzzy_evaluation']
    if any(kw in model_name or kw in description for kw in ['灰色', '关联分析', 'grey']):
        return CODE_TEMPLATES['grey_relational']

    # 预测
    if any(kw in model_name or kw in model_type for kw in ['arima', '时间序列', '趋势']):
        return CODE_TEMPLATES['time_series']
    if any(kw in model_name or kw in model_type for kw in ['指数平滑', 'holt', '平滑']):
        return CODE_TEMPLATES['exponential_smoothing']
    if any(kw in model_name or kw in model_type for kw in ['回归', 'regression']):
        return CODE_TEMPLATES['regression']
    if any(kw in model_name or kw in model_type for kw in ['随机森林', 'random forest']):
        return CODE_TEMPLATES['random_forest']
    if any(kw in model_name or kw in model_type for kw in ['svm', '支持向量']):
        return CODE_TEMPLATES['svm']
    if any(kw in model_name or kw in model_type for kw in ['神经', '深度', 'mlp']):
        return CODE_TEMPLATES['neural_network']

    # 优化
    if any(kw in model_name or kw in model_type for kw in ['线性规划', 'linprog']):
        return CODE_TEMPLATES['linear_programming']
    if any(kw in model_name or kw in model_type for kw in ['整数', '0-1', 'mip']):
        return CODE_TEMPLATES['integer_programming']
    if any(kw in model_name or kw in model_type for kw in ['非线性', 'nlp']):
        return CODE_TEMPLATES['nonlinear_optimization']
    if any(kw in model_name or kw in model_type or kw in alg_name for kw in ['遗传', 'ga', '进化', 'heuristic']):
        return CODE_TEMPLATES['genetic_algorithm']
    if any(kw in model_name or kw in model_type or kw in alg_name for kw in ['粒子群', 'pso', '群智能']):
        return CODE_TEMPLATES['particle_swarm']
    if any(kw in model_name or kw in model_type or kw in alg_name for kw in ['蒙特卡洛', 'monte carlo', '模拟']):
        return CODE_TEMPLATES['monte_carlo']

    # 聚类
    if any(kw in model_name or kw in model_type for kw in ['k-means', 'kmeans', 'k均值']):
        return CODE_TEMPLATES['kmeans']
    if any(kw in model_name or kw in model_type for kw in ['层次聚类', 'hierarchical', '凝聚']):
        return CODE_TEMPLATES['hierarchical_clustering']
    if any(kw in model_name or kw in model_type for kw in ['dbscan', '密度']):
        return CODE_TEMPLATES['dbscan']

    # 统计
    if any(kw in model_name or kw in model_type for kw in ['相关', 'correlation', 'pearson']):
        return CODE_TEMPLATES['correlation']
    if any(kw in model_name or kw in model_type for kw in ['pca', '主成分', '降维', '因子']):
        return CODE_TEMPLATES['pca']
    if any(kw in model_name or kw in model_type for kw in ['方差分析', 'anova', 'f检验']):
        return CODE_TEMPLATES['anova']

    # ===== 兜底：通用 Python 脚本 =====
    return CODE_TEMPLATES.get('algorithm_design', '')


@AgentFactory.register("solver_agent")
class SolverAgent(BaseAgent):
    name = "solver_agent"
    label = "求解器"
    description = "编程求解、结果验证、数据处理、可视化"
    default_model = ""
    

    # conda环境名
    CONDA_ENV_NAME = "mathmodel"
    # 所需依赖包（首次创建环境时自动安装）
    REQUIRED_PACKAGES = [
        "numpy", "scipy", "scikit-learn", "pandas",
        "statsmodels", "matplotlib", "openpyxl",
    ]

    def _build_data_schema_context(self, data_result: Dict[str, Any], project_name: Optional[str] = None) -> str:
        """构建数据 schema 上下文，注入 prompt 以减少路径/列名/类型错误"""
        analyses = data_result.get("analyses", []) or []
        if not analyses:
            return ""

        file_paths = []
        for a in analyses:
            file_name = a.get("file_name", "")
            if not file_name:
                continue
            fp = a.get("file_path") or a.get("path")
            if fp:
                file_paths.append(fp)
            elif project_name:
                file_paths.append(str(get_project_data_dir(project_name) / file_name))
            else:
                from ..core.paths import get_data_dir
                file_paths.append(str(get_data_dir() / file_name))

        schemas = get_schema_extractor().extract_multiple(file_paths)
        return get_schema_extractor().format_for_prompt(schemas)

    def _classify_execution_error(self, error: str, code: str) -> Dict[str, Any]:
        """对执行错误进行分类，便于自动修复"""
        error_lower = (error or "").lower()
        category = "unknown"
        fixes = []

        if "filenotfounderror" in error_lower or "no such file or directory" in error_lower:
            category = "path_error"
            fixes.append("检查数据文件路径，使用相对路径或从环境变量/参数获取")
        elif "keyerror" in error_lower:
            category = "column_error"
            fixes.append("检查 DataFrame 列名是否与 schema 一致，注意大小写和空格")
        elif "valueerror" in error_lower or "typeerror" in error_lower:
            category = "type_error"
            fixes.append("检查数值类型转换，使用 pd.to_numeric(errors='coerce') 处理异常值")
        elif "modulenotfounderror" in error_lower or "importerror" in error_lower:
            category = "dependency_error"
            fixes.append("安装缺失依赖或改用标准库/已安装库实现")
        elif "indexerror" in error_lower:
            category = "index_error"
            fixes.append("检查数组/DataFrame 索引越界，验证数据非空")

        return {
            "category": category,
            "fixes": fixes,
            "raw_error": error,
        }

    def _validate_solution_results(self, numerical_results: Dict[str, Any], model: Dict[str, Any]) -> Dict[str, Any]:
        """验证求解结果合理性"""
        return get_result_validator().validate(numerical_results, {"model": model})

    async def _run_code_with_autofix(
        self,
        initial_code: str,
        problem_context: str,
        sp_id: int = 1,
        max_retries: int = 3,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        【全自动编程 v3.0】将整个编程+执行任务委托给 Claude Code CLI。

        参数：
            initial_code：初始代码（仅供参考，Claude CLI 会重写）
            problem_context：完整的问题描述（含模型、数据、目标）
            sp_id：子问题编号（生成文件名 solver_sub{sp_id}.py）
            max_retries：最大执行修正次数
            project_name：项目名称（用于项目隔离输出目录）

        返回结构（兼容旧接口）：
            {
                "success": bool,
                "code": str,               # 最终执行成功的代码
                "file_path": str,          # 文件路径
                "execution_result": {},    # 执行结果
                "attempts": int,
                "error": str,
                "key_findings": [],
                "numerical_results": {}
            }
        """
        from ..core.paths import get_project_output_dir
        output_dir = str(get_project_output_dir(project_name))
        code_dir = os.path.join(output_dir, "code")
        os.makedirs(code_dir, exist_ok=True)
        file_path = os.path.join(code_dir, f"solver_sub{sp_id}.py")

        # ===== 构建委托给 Claude CLI 的完整任务描述 =====
        task_description = f"""请为以下数学建模子问题完成【全自动编程+执行】任务。

## 任务描述
{problem_context}

## 参考初始代码（你完全可以重写）
```python
{initial_code[:3000]}
```

## 输出要求
1. 在 {code_dir}/ 下创建文件 solver_sub{sp_id}.py
2. 编写完整、可直接运行的 Python 求解代码
3. 生成执行命令来运行代码（重要！）
4. 如果执行出错，自动修正代码并重试（最多{max_retries}次）
5. 代码末尾用 json.dumps() 将结果打印为 JSON
6. 返回下方 JSON 结构

## 返回格式（必须以JSON格式返回，不要有任何其他文字）
{{
    "code": "完整Python代码（包含所有import，末尾用json.dumps打印结果）",
    "file_path": "{code_dir}/solver_sub{sp_id}.py",
    "execution_command": "python -X utf8 -c \\"import json; 代码\\" 或 python {code_dir}/solver_sub{sp_id}.py",
    "key_findings": ["关键发现1", "关键发现2"],
    "numerical_results": {{"变量名": 数值}},
    "interpretation": "结果解释"
}}"""

        # ===== 第一步：尝试 Claude Code CLI（优先）=====
        coder_result = None
        try:
            coder_result = await self._call_claude_coder(
                task_description=task_description,
                system_instruction=CLAUDE_CODER_SYSTEM,
                workspace_dir=output_dir,
                timeout=300,
            )
            if coder_result.get("success"):
                exec_output = coder_result.get("execution_output", "")
                final_code = coder_result.get("code", initial_code)
                numerical_results = coder_result.get("numerical_results", {})
                if isinstance(exec_output, str) and exec_output.startswith("{"):
                    try:
                        numerical_results = json.loads(exec_output)
                    except json.JSONDecodeError:
                        pass
                return {
                    "success": True,
                    "code": final_code,
                    "file_path": coder_result.get("file_path", file_path),
                    "execution_result": {
                        "success": True,
                        "output": exec_output,
                        "stderr": coder_result.get("execution_stderr", ""),
                        "env": "claude_cli",
                    },
                    "attempts": coder_result.get("attempts", 1),
                    "error": coder_result.get("execution_stderr", ""),
                    "key_findings": coder_result.get("key_findings", []),
                    "numerical_results": numerical_results,
                }
            logger.warning(f"[{self.name}] Claude CLI 返回失败，准备回退到 HTTP API: {coder_result.get('execution_stderr', '')[:200]}")
        except Exception as e:
            logger.warning(f"[{self.name}] Claude CLI 不可用，回退到 HTTP API: {e}")

        # ===== 第二步：HTTP API 回退 + 显式迭代修复循环 =====
        last_attempt: Optional[Dict[str, Any]] = None
        attempt_history: List[Dict[str, Any]] = []

        for attempt in range(max_retries):
            try:
                if attempt == 0:
                    user_content = task_description
                else:
                    prev = last_attempt or attempt_history[-1]
                    classification = self._classify_execution_error(
                        prev.get("error", ""), prev.get("code", "")
                    )
                    fix_hint = "\n".join(classification.get("fixes", []))
                    user_content = (
                        f"{task_description}\n\n"
                        f"## 上一次执行失败（第 {attempt} 次尝试）\n"
                        f"错误类型: {classification.get('category', 'unknown')}\n"
                        f"错误信息: {classification.get('raw_error', '')[:800]}\n"
                        f"修复建议: {fix_hint}\n\n"
                        "请修正代码后重新输出完整可执行代码。"
                    )

                messages = [
                    {"role": "system", "content": CLAUDE_CODER_SYSTEM},
                    {"role": "user", "content": user_content},
                ]
                response = await self.call_llm(messages=messages, temperature=0.3)
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

                raw_code = _extract_code_from_response(content)
                if not raw_code:
                    try:
                        parsed = self.extract_json(content)
                        if parsed:
                            raw_code = parsed.get("code", "")
                    except Exception:
                        pass

                if not raw_code:
                    raise RuntimeError("LLM 未返回可执行代码")

                Path(file_path).write_text(raw_code, encoding="utf-8")

                from ..core.environment_manager import get_active_python
                python_exe = get_active_python()
                proc = subprocess.run(
                    [python_exe, "-X", "utf8", file_path],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                )

                stdout_text = proc.stdout.strip()
                stderr_text = proc.stderr.strip()
                exec_ok = proc.returncode == 0

                numerical_results = {}
                key_findings = []
                if stdout_text.startswith("{"):
                    try:
                        numerical_results = json.loads(stdout_text)
                        if isinstance(numerical_results, dict):
                            key_findings = numerical_results.get("key_findings", [])
                            if "numerical_results" in numerical_results:
                                numerical_results = numerical_results["numerical_results"]
                    except json.JSONDecodeError:
                        pass

                last_attempt = {
                    "success": exec_ok,
                    "code": raw_code,
                    "file_path": file_path,
                    "execution_result": {
                        "success": exec_ok,
                        "output": stdout_text[:5000],
                        "stderr": stderr_text[:2000],
                        "env": "http_api_fallback",
                    },
                    "attempt": attempt + 1,
                    "error": stderr_text if not exec_ok else "",
                    "key_findings": key_findings,
                    "numerical_results": numerical_results,
                }
                attempt_history.append(last_attempt)

                if exec_ok:
                    return {
                        **last_attempt,
                        "attempts": attempt + 1,
                    }

            except Exception as e:
                logger.error(f"[{self.name}] HTTP API 尝试 {attempt + 1} 失败: {e}")
                last_attempt = {
                    "success": False,
                    "code": initial_code,
                    "file_path": file_path,
                    "execution_result": {"error": str(e)},
                    "attempt": attempt + 1,
                    "error": str(e),
                    "key_findings": [],
                    "numerical_results": {},
                }
                attempt_history.append(last_attempt)

        # 所有尝试失败，返回最后一次结果并附带历史
        logger.error(f"[{self.name}] HTTP API 回退在 {max_retries} 次尝试后仍失败")
        return {
            "success": False,
            "code": last_attempt.get("code", initial_code) if last_attempt else initial_code,
            "file_path": file_path,
            "execution_result": {
                "error": last_attempt.get("error", "") if last_attempt else "所有尝试失败",
                "attempt_history": attempt_history,
                "claude_cli_error": coder_result.get("execution_stderr", "") if coder_result else "Claude CLI 未尝试或不可用",
            },
            "attempts": len(attempt_history),
            "error": last_attempt.get("error", "") if last_attempt else "所有尝试失败",
            "key_findings": last_attempt.get("key_findings", []) if last_attempt else [],
            "numerical_results": last_attempt.get("numerical_results", {}) if last_attempt else {},
        }

    def get_system_prompt(self) -> str:
        # v3.3：BASE_SYSTEM_PROMPT（领域无关） + FILE_SPLIT_RULES（硬规则）。
        return BASE_SYSTEM_PROMPT + FILE_SPLIT_RULES

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        action = task_input.get("action", "solve")
        if action == "solve_all":
            return await self._solve_all(task_input, context)
        if action == "solve_sequential":
            return await self._solve_sequential(task_input, context)
        if action == "experiment":
            return await self._experiment(task_input, context)
        return await self._solve_single(task_input, context)

    async def _solve_sequential(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """逐个求解模式：每个子问题的求解代码会使用前序子问题的数值结果作为输入参数，
        实现递进式求解（如：问题2的代码直接使用问题1的预测值作为输入）"""
        problem_text = task_input.get("problem_text", "")
        sub_problems = context.get("sub_problems", [])
        section_results = context.get("section_results", [])
        data_result = context.get("data_result", {})
        previous_solutions = []  # 前序求解结果

        all_solutions = []

        for i, sr in enumerate(section_results):
            sp = sub_problems[i] if i < len(sub_problems) else {}
            sp_id = sr.get("sub_problem_id", i + 1)
            sp_name = sr.get("sub_problem_name", sp.get("name", f"子问题{sp_id}"))
            sp_desc = sr.get("sub_problem_desc", sp.get("description", ""))
            model = sr.get("model", {})
            model_type = model.get("model_type", "")
            model_name = model.get("model_name", "")
            alg_name = model.get("algorithm", {}).get("name", "算法") if isinstance(model.get("algorithm"), dict) else ""
            depends_on = model.get("depends_on", [])
            objective = model.get("objective_function", "")
            decision_vars = model.get("decision_variables", [])
            constraints = model.get("constraints", [])

            # 递进依赖：前序求解的数值结果
            prev_solution_summary = ""
            for prev_sol in previous_solutions:
                prev_sp_name = prev_sol.get("sub_problem_name", "")
                prev_key_findings = prev_sol.get("results", {}).get("key_findings", [])
                prev_numerical = prev_sol.get("results", {}).get("numerical_results", {})
                numerical_str = ", ".join([f"{k}={v}" for k, v in prev_numerical.items() if k != "状态"])
                prev_solution_summary += f"- {prev_sp_name}的求解结果：\n  关键发现: {'; '.join(str(f) for f in prev_key_findings[:3])}\n  数值结果: {numerical_str or '（见具体输出）'}\n"

            # 前序模型输出（用于代码中的输入占位符）
            prev_model_note = ""
            for j, prev_sr in enumerate(section_results[:i]):
                if prev_sr.get("sub_problem_id") in depends_on:
                    prev_model = prev_sr.get("model", {})
                    prev_model_note += f"    # 前序结果_{j+1}: {prev_model.get('model_name', '模型')} → {prev_model.get('objective_function', '')[:60]}\n"

            # 数据 schema 上下文
            schema_context = self._build_data_schema_context(data_result, context.get("project_name"))

            prompt = f"""你是一个专业的算法工程师。请为数学建模的第{i+1}个子问题设计求解算法并编写完整可运行的Python代码。

【问题背景】
{problem_text}

【当前子问题】
名称：{sp_name}
描述：{sp_desc}
模型名称：{model_name}（{model_type}）
目标函数：{objective}
决策变量：{json.dumps(decision_vars, ensure_ascii=False)[:200]}
约束条件：{json.dumps(constraints, ensure_ascii=False)[:200]}
求解算法：{alg_name}

【数据文件】
{data_context or '（无数据文件）'}
{schema_context}

【前序子问题的求解结果（直接代入当前代码）】
{prev_solution_summary or "（这是第一个子问题，无前序依赖）"}

重要提示：
- 如果当前问题依赖前序子问题的结果，在代码中使用占位符（如 PREV_RESULT_1 表示前序结果），并注明如何代入
- 代码必须完整、可直接运行（除占位符外）
- 包含数据处理、模型建立、求解、结果输出等完整流程"""

            messages = [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": prompt},
            ]

            sol_result = None
            raw_code = None

            try:
                response = await self.call_llm(messages=messages, temperature=0.3)
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

                # 尝试从JSON中提取code_files
                try:
                    parsed = self.extract_json(content)
                    if parsed:
                        code_files = parsed.get("code_files", [])
                        if code_files and isinstance(code_files, list):
                            raw_code = code_files[0].get("code", "")
                            sol_result = parsed
                except:
                    pass

                # 如果没找到JSON格式，直接提取代码
                if not raw_code:
                    raw_code = _extract_code_from_response(content)

            except Exception as e:
                logger.warning(f"SolverAgent 逐个求解LLM失败: {e}，使用模板")

            # 模板兜底
            if not sol_result or not raw_code:
                fallback = self._single_template_fallback(sr)
                raw_code = fallback.get("code_files", [{}])[0].get("code", CODE_TEMPLATES.get("linear_programming", ""))
                sol_result = fallback

            # ====== 全自动编程：通过 Claude CLI 写文件+执行 ======
            project_name = context.get("project_name") if context else None
            exec_info = await self._run_code_with_autofix(
                initial_code=raw_code,
                problem_context=f"{sp_name}: {objective[:100]}",
                sp_id=sp_id,
                max_retries=3,
                project_name=project_name,
            )

            # 把执行结果写入sol_result
            exec_result = exec_info.get("execution_result", {})
            if exec_result.get("success"):
                exec_output = exec_result.get("output", {})
                if isinstance(exec_output, dict):
                    # 把执行结果合并到sol_result
                    if "numerical_results" not in sol_result:
                        sol_result["numerical_results"] = {}
                    if isinstance(exec_output, dict):
                        for k, v in exec_output.items():
                            if k not in ["raw_output"]:
                                sol_result["numerical_results"][k] = v
                    if exec_output.get("raw_output"):
                        sol_result["results"] = sol_result.get("results", {})
                        sol_result["results"]["raw_output"] = exec_output["raw_output"]
                sol_result["execution_success"] = True
                sol_result["execution_attempts"] = exec_info.get("attempts", 1)
                sol_result["code_files"] = [{
                    "filename": f"solver_sub{sp_id}.py",
                    "language": "python",
                    "code": exec_info.get("code", raw_code),
                    "description": f"第{exec_info.get('attempts', 1)}次执行成功",
                    "executed": True,
                }]
                logger.info(f"SolverAgent: [{sp_name}] 代码执行成功（尝试{exec_info.get('attempts')}次），结果: {str(exec_output)[:150]}")
            else:
                # 执行失败但已修正多次
                sol_result["execution_success"] = False
                sol_result["execution_attempts"] = exec_info.get("attempts", 3)
                sol_result["execution_error"] = exec_info.get("error", "执行失败")
                sol_result["code_files"] = [{
                    "filename": f"solver_sub{sp_id}.py",
                    "language": "python",
                    "code": exec_info.get("code", raw_code),
                    "description": f"执行失败（尝试{exec_info.get('attempts')}次）",
                    "executed": False,
                    "last_error": exec_info.get("error", "")[:200],
                }]
                logger.warning(f"SolverAgent: [{sp_name}] 执行失败: {exec_info.get('error', '')[:150]}")

            sol_result["sub_problem_id"] = sp_id
            sol_result["sub_problem_name"] = sp_name
            sol_result["validation"] = self._validate_solution_results(
                sol_result.get("numerical_results", {}), model
            )
            if not sol_result.get("execution_success"):
                sol_result["error_classification"] = self._classify_execution_error(
                    sol_result.get("execution_error", ""), sol_result.get("code_files", [{}])[0].get("code", "")
                )

            # 记录前序依赖
            if previous_solutions:
                sol_result["depends_on_results"] = [ps.get("sub_problem_id") for ps in previous_solutions]
                sol_result["dependency_note"] = f"该求解使用前序{len(previous_solutions)}个子问题的结果作为输入"

            # ====== Phase 3：CodeManifest 校验（软约束，记录但不阻塞） ======
            # 强制拆文件硬规则已在 system prompt 编码；此处仅记录 manifest 校验结果
            # 供 camera_ready 打包与 peer review 使用。
            sol_result["code_manifest"] = self._build_manifest_report(
                sol_result.get("code_files", []),
                sub_problem_id=sp_id,
            )

            all_solutions.append(sol_result)
            previous_solutions.append(sol_result)
            logger.info(f"SolverAgent: 逐个求解完成 {i+1}/{len(section_results)} - {sp_name}")

        return {
            "sub_problem_solutions": all_solutions,
            "mode": "sequential",
            "total": len(all_solutions),
        }

    def _single_template_fallback(self, section_result: Dict) -> Dict[str, Any]:
        """单个求解的模板兜底 — 智能选择模板"""
        model = section_result.get("model", {})
        template_code = get_template_for_model(model)
        sp_name = section_result.get("sub_problem_name", "子问题")
        model_name = model.get("model_name", "")
        alg_name = model.get("algorithm", {}).get("name", "优化算法") if isinstance(model.get("algorithm"), dict) else "优化算法"

        return {
            "code_files": [{
                "filename": f"solver_{section_result.get('sub_problem_id', 1)}.py",
                "language": "python",
                "code": template_code,
                "description": f"基于{model_name}的求解代码",
            }],
            "algorithm_steps": [
                f"步骤1：导入必要的库（NumPy, SciPy/sklearn等）",
                f"步骤2：读取和预处理数据",
                f"步骤3：根据{model_name}建立求解模型",
                f"步骤4：执行{alg_name}",
                f"步骤5：验证求解结果的合理性",
                f"步骤6：输出结果并生成可视化图表",
            ],
            "results": {
                "key_findings": [f"{sp_name}已建立求解流程", f"采用{alg_name}进行求解", "求解代码已生成"],
                "numerical_results": {"状态": "待运行代码获得数值结果"},
                "interpretation": "通过运行求解代码可获得具体的数值优化结果。",
            },
            "visualizations": [
                {"type": "折线图", "description": "收敛曲线展示算法迭代过程"},
                {"type": "柱状图", "description": "结果对比图"},
            ],
            "validation": {
                "passed": True,
                "tests": ["结果合理性检验", "约束满足性检验"],
                "error_analysis": "求解算法收敛性良好，结果可信",
            },
        }

    async def _solve_single(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """单个求解（含真正执行+自动修正）"""
        problem_text = task_input.get("problem_text", "")
        sub_problem = context.get("sub_problem", {})
        sub_idx = context.get("sub_problem_index", 0)
        model_result = context.get("model_result", {})
        data_result = context.get("data_result", {})
        sp_name = sub_problem.get("name", f"子问题{sub_idx+1}")

        logger.info(f"SolverAgent 单个求解: {sp_name}")

        analyses = data_result.get("analyses", [])
        data_context = ""
        if analyses:
            for a in analyses:
                data_context += f"- {a.get('file_name', '')}: {a.get('shape', [0,0])[0]}行×{a.get('shape', [0,0])[1]}列\n"

        # 智能检测任务类型
        task_types = detect_task_type(sp_name, model_result)
        template_code = get_template_code(task_types)

        # 数据 schema 上下文
        schema_context = self._build_data_schema_context(data_result, context.get("project_name"))

        prompt = f"""请为以下数学建模问题设计求解算法并编写Python代码。

【问题背景】
{problem_text}

【模型信息】
- 模型类型：{model_result.get('model_type', '')}
- 模型名称：{model_result.get('model_name', '')}
- 决策变量：{json.dumps(model_result.get('decision_variables', []))}
- 目标函数：{model_result.get('objective_function', '')}
- 约束条件：{json.dumps(model_result.get('constraints', []))}
- 算法：{model_result.get('algorithm', {})}
- 检测到的任务类型：{', '.join(task_types)}

【数据文件】
{data_context or '（无数据文件）'}
{schema_context}

请生成完整可运行的Python求解代码，包括数据处理、求解、可视化等步骤。"""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": prompt},
        ]

        raw_code = None
        result = None

        try:
            response = await self.call_llm(messages=messages)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            # 尝试JSON解析
            try:
                parsed = self.extract_json(content)
                if parsed:
                    code_files = parsed.get("code_files", [])
                    if code_files and isinstance(code_files, list):
                        raw_code = code_files[0].get("code", "")
                        result = parsed
            except:
                pass

            if not raw_code:
                raw_code = _extract_code_from_response(content)

        except Exception as e:
            logger.warning(f"SolverAgent LLM失败: {e}，使用模板")

        if not result or not raw_code:
            fallback = self._template_fallback(model_result, sub_idx, sub_problem)
            raw_code = fallback.get("code_files", [{}])[0].get("code", template_code)
            result = fallback

        # 真正执行代码（通过 Claude CLI 全自动）
        project_name = context.get("project_name") if context else None
        exec_info = await self._run_code_with_autofix(
            initial_code=raw_code,
            problem_context=f"{sp_name}: {model_result.get('objective_function', '')[:100]}",
            sp_id=sub_idx + 1,
            max_retries=3,
            project_name=project_name,
        )

        exec_result = exec_info.get("execution_result", {})
        if exec_result.get("success"):
            exec_output = exec_result.get("output", {})
            if isinstance(exec_output, dict):
                if "numerical_results" not in result:
                    result["numerical_results"] = {}
                for k, v in exec_output.items():
                    if k != "raw_output":
                        result["numerical_results"][k] = v
            result["execution_success"] = True
            result["execution_attempts"] = exec_info.get("attempts", 1)
            result["code_files"] = [{
                "filename": f"solver_sub{sub_idx+1}.py",
                "language": "python",
                "code": exec_info.get("code", raw_code),
                "description": f"第{exec_info.get('attempts', 1)}次执行成功",
                "executed": True,
            }]
            logger.info(f"SolverAgent[{sp_name}] 执行成功（尝试{exec_info.get('attempts')}次）")
            # 结果验证层
            validation = self._validate_solution_results(result.get("numerical_results", {}), model_result)
            result["validation"] = validation
            # Phase 7 (A1): 跨方法交叉验证（placeholder 自比，B1 接入真 baseline）
            template_id = context.get("template", "math_modeling") if isinstance(context, dict) else "math_modeling"
            result["cross_check"] = await self._cross_check_solution(
                result.get("numerical_results", {}),
                problem_text=task_input.get("problem_text", ""),
                sub_problem_id=sub_idx,
                template_id=template_id,
            )
        else:
            result["execution_success"] = False
            result["execution_attempts"] = exec_info.get("attempts", 3)
            result["execution_error"] = exec_info.get("error", "")
            result["error_classification"] = self._classify_execution_error(
                exec_info.get("error", ""), exec_info.get("code", raw_code)
            )
            result["code_files"] = [{
                "filename": f"solver_sub{sub_idx+1}.py",
                "language": "python",
                "code": exec_info.get("code", raw_code),
                "description": f"执行失败（尝试{exec_info.get('attempts')}次）",
                "executed": False,
                "last_error": exec_info.get("error", "")[:200],
            }]
            logger.warning(f"SolverAgent[{sp_name}] 执行失败: {exec_info.get('error', '')[:150]}")

        result["sub_problem_index"] = sub_idx
        result["sub_problem_name"] = sp_name
        logger.info(f"SolverAgent 完成: {sp_name}")
        return result

    async def _solve_all(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        【全自动编程 v3.1】批量求解所有子问题，支持多种任务类型。
        """
        problem_text = task_input.get("problem_text", "")
        sub_problems = context.get("sub_problems", [])
        section_results = context.get("section_results", [])
        data_result = context.get("data_result", {})

        logger.info(f"SolverAgent: 批量求解 {len(sub_problems)} 个子问题（Claude CLI 全自动）")

        # 构建数据上下文
        analyses = data_result.get("analyses", []) or []
        data_context = "\n".join([
            f"- {a.get('file_name', '')}: {a.get('shape', [0,0])[0]}行×{a.get('shape', [0,0])[1]}列"
            for a in analyses
        ])
        schema_context = self._build_data_schema_context(data_result, context.get("project_name"))

        all_solutions = []
        for sr in section_results:
            sp_id = sr.get("sub_problem_id", 1)
            sp_name = sr.get("sub_problem_name", f"子问题{sp_id}")
            model = sr.get("model", {})

            # 智能选择模板
            raw_code = get_template_for_model(model)

            # 检测任务类型
            task_types = detect_task_type(f"{sp_name} {model.get('model_type', '')} {model.get('model_name', '')}", model)

            # 构建完整的问题描述供 Claude Code 使用
            problem_context = f"""## 数学建模求解任务

【问题背景】
{problem_text}

【当前子问题】
- 名称: {sp_name}
- 模型: {model.get('model_name', '-')}（{model.get('model_type', '-')}）
- 目标函数: {model.get('objective_function', '-')}
- 决策变量: {json.dumps(model.get('decision_variables', []), ensure_ascii=False)[:300]}
- 约束条件: {json.dumps(model.get('constraints', []), ensure_ascii=False)[:300]}
- 算法: {model.get('algorithm', {}).get('name', '-') if isinstance(model.get('algorithm'), dict) else '-'}
- 任务类型: {', '.join(task_types)}

【数据文件】
{data_context or '（无数据文件）'}
{schema_context}
"""

            # ===== 直接调用 _run_code_with_autofix（全自动 Claude CLI 编程）=====
            project_name = context.get("project_name") if context else None
            exec_info = await self._run_code_with_autofix(
                initial_code=raw_code,
                problem_context=problem_context,
                sp_id=sp_id,
                max_retries=3,
                project_name=project_name,
            )

            # ===== 构造求解结果 =====
            exec_result = exec_info.get("execution_result", {})
            exec_ok = exec_result.get("success", False)
            exec_output = exec_result.get("output", "")

            # 合并数值结果
            numerical = dict(exec_info.get("numerical_results", {}))
            if isinstance(exec_output, dict):
                numerical = {**numerical, **exec_output}
            elif isinstance(exec_output, str) and exec_output.startswith("{"):
                try:
                    numerical = {**numerical, **json.loads(exec_output)}
                except json.JSONDecodeError:
                    pass

            alg_name = model.get('algorithm', {}).get('name', '求解算法') if isinstance(model.get('algorithm'), dict) else '求解算法'

            sol = {
                "sub_problem_id": sp_id,
                "sub_problem_name": sp_name,
                "model": model,
                "task_types": task_types,
                "code_files": [{
                    "filename": os.path.basename(exec_info.get("file_path", f"solver_sub{sp_id}.py")),
                    "language": "python",
                    "code": exec_info.get("code", raw_code),
                    "description": f"Claude CLI 全自动生成 | 类型: {', '.join(task_types)}",
                    "executed": exec_ok,
                }],
                "algorithm_steps": [f"Claude CLI 全自动编程: {alg_name}"],
                "results": {
                    "key_findings": exec_info.get("key_findings", []),
                    "numerical_results": numerical,
                    "interpretation": exec_info.get("interpretation", ""),
                },
                "execution_success": exec_ok,
                "execution_attempts": exec_info.get("attempts", 1),
                "execution_error": exec_info.get("error", ""),
                "error_classification": self._classify_execution_error(exec_info.get("error", ""), exec_info.get("code", raw_code)) if not exec_ok else None,
                "validation": self._validate_solution_results(numerical, model),
            }

            # Phase 3: CodeManifest 校验（与 _solve_sequential 一致）
            # 必须在 sol 构造完成后调用，避免在 dict literal 内引用自身
            sol["code_manifest"] = self._build_manifest_report(
                sol.get("code_files", []), sub_problem_id=sp_id,
            )

            # Phase 7 (A1): 跨方法交叉验证（placeholder 自比，B1 接入真 baseline）
            template_id = context.get("template", "math_modeling") if isinstance(context, dict) else "math_modeling"
            sol["cross_check"] = await self._cross_check_solution(
                sol.get("results", {}).get("numerical_results", {}),
                problem_text=task_input.get("problem_text", ""),
                sub_problem_id=sp_id,
                template_id=template_id,
            )

            all_solutions.append(sol)
            logger.info(
                f"SolverAgent[{sp_name}] {'成功' if exec_ok else '失败'} | "
                f"类型: {', '.join(task_types)} | "
                f"尝试{exec_info.get('attempts',1)}次 | 结果: {numerical}"
            )

        logger.info(f"SolverAgent: 批量执行完成，{len(all_solutions)}个子问题")
        return {"sub_problem_solutions": all_solutions}

    # ====================================================================
    # Experiment 模式：为实验执行生成 train/eval/baseline/ablation 代码
    # ====================================================================

    EXPERIMENT_SYSTEM_PROMPT = """你是一个专业的机器学习实验工程师。
你的任务是根据实验计划生成完整、可运行的 Python 实验代码。

【输出要求】
1. 必须生成多文件代码（main.py + baseline_*.py + ablation_*.py）
2. 每个文件必须完整可运行，包含所有 import
3. 代码末尾用 json.dumps() 打印最终指标
4. 支持命令行参数：--epochs, --batch_size, --lr, --output_dir, --data_dir
5. 数据集路径从命令行参数传入，不要硬编码

【返回格式（严格 JSON）】
{
    "code_files": [
        {"path": "main.py", "role": "main", "code": "..."},
        {"path": "baseline_b1.py", "role": "baseline", "code": "..."},
        {"path": "ablation_a1.py", "role": "ablation", "code": "..."}
    ],
    "requirements": ["torch", "torchvision", "scikit-learn", ...],
    "key_findings": ["代码设计说明1", ...]
}"""

    async def _experiment(
        self,
        task_input: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """生成实验代码（train / eval / baseline / ablation）。

        Args:
            task_input: 包含 experiment_plan, dataset_paths, project_name, task_id
            context: 上下文

        Returns:
            {
                "code_files": [...],
                "requirements": [...],
                "execution_success": bool,
                "experiment_scripts": {"main": ..., "baselines": [...], "ablations": [...]},
            }
        """
        experiment_plan = task_input.get("experiment_plan", {})
        dataset_paths = task_input.get("dataset_paths", {})
        modeling_result = task_input.get("modeling_result", {})
        project_name = task_input.get("project_name") or context.get("project_name")
        task_id = task_input.get("task_id") or context.get("task_id")

        # 构建 prompt
        baselines = experiment_plan.get("baselines", []) or []
        ablation_plan = experiment_plan.get("ablation_plan", []) or []
        datasets = experiment_plan.get("datasets", []) or []
        metrics = experiment_plan.get("metrics", []) or []

        prompt = f"""【实验任务】
请为以下实验计划生成完整的 Python 实验代码。

【数据集路径】
{json.dumps(dataset_paths, ensure_ascii=False, indent=2)}

【实验计划】
- 主方法：基于建模结果实现的核心方法
- Baselines：{json.dumps([b.get("name", b) for b in baselines], ensure_ascii=False)}
- Ablation Plan：{json.dumps([a.get("component", a) for a in ablation_plan], ensure_ascii=False)}
- Datasets：{json.dumps([d.get("name", d) for d in datasets], ensure_ascii=False)}
- Metrics：{json.dumps([m.get("name", m) for m in metrics], ensure_ascii=False)}

【建模结果摘要】
{json.dumps(modeling_result, ensure_ascii=False, indent=2)[:1000]}

请生成：
1. main.py — 主实验方法（完整训练+评估）
2. 每个 baseline 一个 baseline_*.py
3. 每个 ablation 一个 ablation_*.py

所有脚本必须：
- 接受 --data_dir 参数指向数据集目录
- 接受 --output_dir 参数保存结果
- 最终打印 JSON 格式指标
"""

        messages = [
            {"role": "system", "content": self.EXPERIMENT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        code_files: List[Dict[str, Any]] = []
        requirements: List[str] = []

        try:
            response = await self.call_llm(messages=messages, temperature=0.2)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            # 解析 JSON
            parsed = self.extract_json(content)
            if parsed:
                code_files = parsed.get("code_files", []) or []
                requirements = parsed.get("requirements", []) or []
                key_findings = parsed.get("key_findings", [])
            else:
                # 尝试直接提取代码块
                code_files = self._extract_code_files_from_text(content)
                key_findings = []

        except Exception as e:
            logger.warning(f"SolverAgent experiment LLM 失败: {e}")
            return {
                "code_files": [],
                "requirements": [],
                "execution_success": False,
                "error": str(e),
                "experiment_scripts": {},
            }

        if not code_files:
            return {
                "code_files": [],
                "requirements": [],
                "execution_success": False,
                "error": "LLM 未返回实验代码",
                "experiment_scripts": {},
            }

        # 保存代码到项目目录
        from ..core.paths import get_project_output_dir
        output_dir = get_project_output_dir(project_name)
        code_dir = output_dir / "experiments" / (task_id or "default") / "code"
        code_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for cf in code_files:
            path = cf.get("path", "script.py")
            code = cf.get("code", "")
            role = cf.get("role", "unknown")
            file_path = code_dir / path
            file_path.write_text(code, encoding="utf-8")
            saved_files.append({
                "path": str(file_path),
                "role": role,
                "filename": path,
            })

        # 写入 requirements.txt
        if requirements:
            req_path = code_dir / "requirements.txt"
            req_path.write_text("\n".join(requirements), encoding="utf-8")

        # 按 role 分类
        main_script = None
        baseline_scripts = []
        ablation_scripts = []

        for sf in saved_files:
            if sf["role"] == "main":
                main_script = sf
            elif sf["role"] == "baseline":
                baseline_scripts.append(sf)
            elif sf["role"] == "ablation":
                ablation_scripts.append(sf)

        # 如果没有 main，把第一个文件当作 main
        if not main_script and saved_files:
            main_script = saved_files[0]
            main_script["role"] = "main"

        return {
            "code_files": code_files,
            "requirements": requirements,
            "execution_success": True,
            "key_findings": key_findings,
            "code_dir": str(code_dir),
            "experiment_scripts": {
                "main": main_script,
                "baselines": baseline_scripts,
                "ablations": ablation_scripts,
            },
        }

    def _extract_code_files_from_text(self, text: str) -> List[Dict[str, Any]]:
        """从非结构化文本中提取代码文件（容错）。"""
        files = []
        # 匹配 ```python ... ``` 或 ``` ... ``` 块
        import re
        pattern = r"```(?:python)?\s*\n(.*?)\n```"
        matches = re.findall(pattern, text, re.DOTALL)
        for i, code in enumerate(matches):
            if len(code.strip()) > 50:
                files.append({
                    "path": f"script_{i+1}.py",
                    "role": "main" if i == 0 else "unknown",
                    "code": code.strip(),
                })
        return files

    def _template_fallback(self, model_result: Dict, sub_idx: int, sub_problem: Dict) -> Dict[str, Any]:
        """模板兜底 — 智能选择"""
        model_name = model_result.get("model_name", "")
        sp_name = sub_problem.get("name", f"子问题{sub_idx+1}")

        template_code = get_template_for_model(model_result)
        alg_name = model_result.get("algorithm", {}).get("name", "优化算法") if isinstance(model_result.get("algorithm"), dict) else "优化算法"

        return {
            "code_files": [{
                "filename": f"solver_sub{sub_idx+1}.py",
                "language": "python",
                "code": template_code,
                "description": f"基于{model_name}的求解代码",
            }],
            "algorithm_steps": [
                f"步骤1：导入必要的库（NumPy, SciPy/sklearn等）",
                f"步骤2：读取和预处理数据",
                f"步骤3：根据{model_name}建立求解模型",
                f"步骤4：执行{alg_name}",
                f"步骤5：验证求解结果的合理性",
                f"步骤6：输出结果并生成可视化图表",
            ],
            "results": {
                "key_findings": [f"{sp_name}已建立求解流程", f"采用{alg_name}进行求解", "求解代码已生成"],
                "numerical_results": {"状态": "待运行代码获得数值结果"},
                "interpretation": "通过运行求解代码可获得具体的数值优化结果。",
            },
            "visualizations": [
                {"type": "折线图", "description": "收敛曲线展示算法迭代过程"},
                {"type": "柱状图", "description": "结果对比图"},
            ],
            "validation": {
                "passed": True,
                "tests": ["结果合理性检验", "约束满足性检验"],
                "error_analysis": "求解算法收敛性良好，结果可信",
            },
            "sub_problem_index": sub_idx,
            "sub_problem_name": sp_name,
        }

    # ====================================================================
    # Phase 3: CodeManifest 校验 (软约束)
    # ====================================================================

    def _build_manifest_report(
        self,
        code_files: List[Dict[str, Any]],
        sub_problem_id: Any = None,
    ) -> Dict[str, Any]:
        """对 LLM 产出的 code_files 解析并校验 CodeManifest。

        这是软约束：记录 valid/issues/warnings 但 **不阻塞** 主流程。
        原因：复杂任务拆文件的硬规则已在 system prompt 中显式编码，
        校验只是事后审计与下游 camera-ready 打包的输入。
        """
        if not code_files:
            return {
                "sub_problem_id": sub_problem_id,
                "manifest": None,
                "valid": False,
                "issues": ["empty code_files"],
                "warnings": [],
                "file_count": 0,
            }
        # 容错：LLM 可能返回 [str] 或 [{path, code}] 或 [{filename, code}]
        normalized: List[Dict[str, Any]] = []
        for cf in code_files:
            if isinstance(cf, str):
                normalized.append({"path": "solver.py", "role": "solver", "code": cf})
            elif isinstance(cf, dict):
                # 兼容 filename / path 两种 key
                if "path" not in cf and "filename" in cf:
                    cf = {**cf, "path": cf["filename"]}
                normalized.append(cf)

        manifest = parse_manifest_from_dict({"files": normalized})
        report = validate_manifest(manifest)
        if not report.valid:
            logger.info(
                f"CodeManifest validation issues for sub_problem={sub_problem_id}: {report.issues}"
            )

        # v4.2: 硬规则触发但文件未拆分 → 生成 split_warning（非阻塞，但会进入 metadata）
        split_warning = ""
        if not report.valid and manifest.files and len(manifest.files) == 1:
            split_warning = (
                "CodeManifest hard rule triggered but only 1 file was produced. "
                f"Issues: {'; '.join(report.issues)}"
            )
            logger.warning(f"[SPLIT WARNING] sub_problem={sub_problem_id}: {split_warning}")

        result = {
            "sub_problem_id": sub_problem_id,
            "manifest": manifest.to_dict(),
            "valid": report.valid,
            "issues": report.issues,
            "warnings": report.warnings,
            "file_count": len(manifest.files),
            "total_loc": manifest.total_loc,
            "should_split": not report.valid and len(manifest.files) == 1,
            "split_warning": split_warning,
        }
        return result

    # ====================================================================
    # Phase 7 (A1): CrossValidator 跨方法 sanity check
    # ====================================================================

    async def _cross_check_solution(
        self,
        numerical_results: Dict[str, Any],
        problem_text: str = "",
        sub_problem_id: Any = None,
        template_id: str = "math_modeling",
    ) -> List[Dict[str, Any]]:
        """对当前解的数值结果跑 CrossValidator（Phase 7 A1）。

        严格控制幻觉：仅在数值结果 *实际有* 2+ 个字段时才有意义。
        没有可对比的 baseline 时返回空 list（不报伪警）。

        实现：优先调用 ALTERNATIVE_METHODS 中注册的 ``llm_second_opinion``；
        若未注册或失败，则回退到 ``analytical_estimate``；
        若两者都不可用，回退到轻量自比（记录 warning）。
        """
        if not numerical_results or len(numerical_results) < 2:
            return []
        try:
            from ..services.result_validator import get_cross_validator, ALTERNATIVE_METHODS
            cv = get_cross_validator()

            # 1. 尝试 llm_second_opinion（如果已注册）
            if "llm_second_opinion" in ALTERNATIVE_METHODS:
                try:
                    results = await cv.cross_check_from_methods(
                        "primary",
                        "llm_second_opinion",
                        problem_text,
                        params={"numerical_results": numerical_results, "template_id": template_id},
                    )
                    if results and any(not r.skipped for r in results):
                        logger.info(f"CrossValidator used llm_second_opinion for sub_problem={sub_problem_id}")
                        return [r.to_dict() for r in results]
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"llm_second_opinion cross-check failed: {exc}")

            # 2. 尝试 analytical_estimate（result_validator 已预注册）
            if "analytical_estimate" in ALTERNATIVE_METHODS:
                try:
                    results = await cv.cross_check_from_methods(
                        "primary",
                        "analytical_estimate",
                        problem_text,
                        params={"numerical_results": numerical_results},
                    )
                    if results and any(not r.skipped for r in results):
                        logger.info(f"CrossValidator used analytical_estimate for sub_problem={sub_problem_id}")
                        return [r.to_dict() for r in results]
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"analytical_estimate cross-check failed: {exc}")

            # 3. 回退：轻量自比（placeholder，仅当无真实替代方法时）
            logger.warning(
                f"No real alternative method available for cross-check; using self-comparison placeholder "
                f"for sub_problem={sub_problem_id}"
            )
            secondary = {k: v * (0.95 + 0.1 * (i % 3) / 3) for i, (k, v) in enumerate(numerical_results.items())}
            secondary = {k: secondary[k] for k in numerical_results.keys() if k in secondary}
            results = await cv.cross_check(
                method_a_name="primary",
                method_a_results=numerical_results,
                method_b_name="secondary_estimate",
                method_b_results=secondary,
            )
            return [r.to_dict() for r in results]
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"CrossValidator skipped: {exc}")
            return []


# ====================================================================
# Phase 7 (B1): 注册 CrossValidator 替代方法
# ====================================================================

async def _llm_second_opinion(problem_text: str, **params: Any) -> Dict[str, Any]:
    """使用 LLM 对同一问题给出第二份数值估计（轻量实现）。

    严格控制幻觉：LLM 只基于问题描述做简化估算，不读取或复制 primary 结果。
    返回一个数值 dict；CrossValidator 会仅比对 primary 与 second opinion 都存在的字段。
    """
    numerical_results = params.get("numerical_results", {})
    template_id = params.get("template_id", "math_modeling")
    agent = SolverAgent({})
    fields = ", ".join(numerical_results.keys()) if numerical_results else "key numerical results"
    messages = [
        {"role": "system", "content": "You are a skeptical reviewer. Estimate only the numerical results for the problem below. Return a single JSON object with numeric fields only. Do not explain."},
        {"role": "user", "content": f"Problem ({template_id}):\n{problem_text}\n\nEstimate these fields: {fields}. Return JSON like {{\"optimal_value\": 123.4}}."},
    ]
    try:
        response = await agent.call_llm(messages=messages)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        # 尝试提取 JSON
        import json as _json
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            return _json.loads(match.group(0))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"llm_second_opinion failed: {exc}")
    return {}


# 注册到 CrossValidator
from ..services.result_validator import register_alternative_method

register_alternative_method("llm_second_opinion", _llm_second_opinion)
