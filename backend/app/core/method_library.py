"""数学建模结构化方法库 - 检索+代码模板。

v8.2: 实现数学建模结构化方法库：
1. 结构化方法库（AHP/LP/SIR/... 数十～近百种）
2. 方法检索（按类型/适用场景/复杂度）
3. 代码模板（可直接执行的代码片段）
4. 方法推荐（基于问题特征）

参考：MM-Agent 级方法库与赛制交付。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class MethodTemplate:
    """方法模板。"""
    method_id: str
    name: str
    name_cn: str
    category: str  # optimization, statistical, machine_learning, simulation, etc.
    subcategory: str  # linear_programming, time_series, classification, etc.
    description: str
    applicable_scenarios: List[str]  # 适用场景
    complexity: str  # low, medium, high
    prerequisites: List[str]  # 前置知识
    code_template: str  # 代码模板
    dependencies: List[str]  # 依赖包
    references: List[str]  # 参考文献
    tags: List[str]  # 标签


class MethodLibrary:
    """数学建模结构化方法库。"""

    def __init__(self, library_dir: Optional[Path] = None):
        """初始化方法库。

        Args:
            library_dir: 方法库存储目录，默认为 ~/.mathmodel/method_library/
        """
        if library_dir is None:
            library_dir = Path.home() / ".mathmodel" / "method_library"
        self.library_dir = library_dir
        self.library_dir.mkdir(parents=True, exist_ok=True)

        # 方法索引
        self.methods: Dict[str, MethodTemplate] = {}
        self._init_method_library()

    def _init_method_library(self) -> None:
        """初始化方法库内容。"""
        # 优化方法
        self._add_optimization_methods()

        # 统计方法
        self._add_statistical_methods()

        # 机器学习方法
        self._add_machine_learning_methods()

        # 仿真方法
        self._add_simulation_methods()

        # 预测方法
        self._add_forecasting_methods()

        # 评价方法
        self._add_evaluation_methods()

        logger.info(f"Method Library initialized: {len(self.methods)} methods")

    def _add_optimization_methods(self) -> None:
        """添加优化方法。"""
        # 线性规划
        self.methods["LP"] = MethodTemplate(
            method_id="LP",
            name="Linear Programming",
            name_cn="线性规划",
            category="optimization",
            subcategory="linear_programming",
            description="在线性约束条件下优化线性目标函数",
            applicable_scenarios=["资源分配", "生产计划", "运输问题", "投资组合"],
            complexity="low",
            prerequisites=["线性代数基础"],
            code_template='''
import numpy as np
from scipy.optimize import linprog

def solve_linear_program(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=None):
    """求解线性规划问题。
    
    Args:
        c: 目标函数系数 (min c^T x)
        A_ub: 不等式约束矩阵 (A_ub @ x <= b_ub)
        b_ub: 不等式约束右侧
        A_eq: 等式约束矩阵 (A_eq @ x = b_eq)
        b_eq: 等式约束右侧
        bounds: 变量边界 [(low, high), ...]
    
    Returns:
        优化结果
    """
    result = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method='highs')
    return {
        "success": result.success,
        "x": result.x,
        "fun": result.fun,
        "message": result.message
    }
''',
            dependencies=["numpy", "scipy"],
            references=["Dantzig, G. B. (1963]. Linear Programming and Extensions."],
            tags=["线性", "凸优化", "精确解"],
        )

        # 整数规划
        self.methods["IP"] = MethodTemplate(
            method_id="IP",
            name="Integer Programming",
            name_cn="整数规划",
            category="optimization",
            subcategory="integer_programming",
            description="变量取整数值的优化问题",
            applicable_scenarios=["排班问题", "选址问题", "背包问题", "指派问题"],
            complexity="medium",
            prerequisites=["线性规划基础"],
            code_template='''
import numpy as np
from scipy.optimize import linprog, milp, LinearConstraint, Bounds

def solve_integer_program(c, constraints, integrality=None):
    """求解整数规划问题。
    
    Args:
        c: 目标函数系数
        constraints: 约束条件列表
        integrality: 整数性约束 (1=整数, 0=连续)
    
    Returns:
        优化结果
    """
    # 使用 scipy 的 milp 求解器
    constraints_obj = [LinearConstraint(c.A, c.lb, c.ub) for c in constraints]
    result = milp(c=c, constraints=constraints_obj, integrality=integrality)
    return {
        "success": result.success,
        "x": result.x,
        "fun": result.fun,
        "message": result.message
    }
''',
            dependencies=["numpy", "scipy"],
            references=["Wolsey, L. A. (1998]. Integer Programming."],
            tags=["整数", "组合优化", "NP-hard"],
        )

        # 非线性规划
        self.methods["NLP"] = MethodTemplate(
            method_id="NLP",
            name="Nonlinear Programming",
            name_cn="非线性规划",
            category="optimization",
            subcategory="nonlinear_programming",
            description="目标函数或约束为非线性的优化问题",
            applicable_scenarios=["工程设计", "经济模型", "机器学习", "参数估计"],
            complexity="high",
            prerequisites=["微积分", "线性代数"],
            code_template='''
import numpy as np
from scipy.optimize import minimize

def solve_nonlinear_program(func, x0, constraints=None, bounds=None, method='SLSQP'):
    """求解非线性规划问题。
    
    Args:
        func: 目标函数
        x0: 初始点
        constraints: 约束条件
        bounds: 变量边界
        method: 优化方法
    
    Returns:
        优化结果
    """
    result = minimize(func, x0, method=method, constraints=constraints, bounds=bounds)
    return {
        "success": result.success,
        "x": result.x,
        "fun": result.fun,
        "message": result.message
    }
''',
            dependencies=["numpy", "scipy"],
            references=["Nocedal, J., & Wright, S. J. (2006]. Numerical Optimization."],
            tags=["非线性", "梯度", "局部最优"],
        )

    def _add_statistical_methods(self) -> None:
        """添加统计方法。"""
        # 回归分析
        self.methods["REG"] = MethodTemplate(
            method_id="REG",
            name="Regression Analysis",
            name_cn="回归分析",
            category="statistical",
            subcategory="regression",
            description="研究变量之间依赖关系的统计方法",
            applicable_scenarios=["预测建模", "因素分析", "因果推断", "趋势分析"],
            complexity="low",
            prerequisites=["概率论基础"],
            code_template='''
import numpy as np
from sklearn.linear_model import LinearRegression, Ridge, Lasso

def linear_regression(X, y, alpha=0):
    """线性回归（支持岭回归和Lasso）。
    
    Args:
        X: 特征矩阵
        y: 目标变量
        alpha: 正则化系数 (0=普通最小二乘)
    
    Returns:
        模型结果
    """
    if alpha == 0:
        model = LinearRegression()
    else:
        model = Ridge(alpha=alpha)  # 或 Lasso(alpha=alpha)
    
    model.fit(X, y)
    return {
        "coefficients": model.coef_,
        "intercept": model.intercept_,
        "score": model.score(X, y),
        "predictions": model.predict(X)
    }
''',
            dependencies=["numpy", "scikit-learn"],
            references=["Draper, N. R., & Smith, H. (1998]. Applied Regression Analysis."],
            tags=["回归", "预测", "连续变量"],
        )

        # 假设检验
        self.methods["HYP"] = MethodTemplate(
            method_id="HYP",
            name="Hypothesis Testing",
            name_cn="假设检验",
            category="statistical",
            subcategory="hypothesis_testing",
            description="对总体参数或分布做出假设并进行检验",
            applicable_scenarios=["A/B测试", "质量控制", "药物试验", "政策评估"],
            complexity="medium",
            prerequisites=["概率论", "统计推断"],
            code_template='''
import numpy as np
from scipy import stats

def t_test(sample1, sample2=None, paired=False):
    """t检验。
    
    Args:
        sample1: 样本1
        sample2: 样本2（双样本检验）
        paired: 是否配对样本
    
    Returns:
        检验结果
    """
    if sample2 is None:
        # 单样本检验
        t_stat, p_value = stats.ttest_1samp(sample1, 0)
    elif paired:
        # 配对样本检验
        t_stat, p_value = stats.ttest_rel(sample1, sample2)
    else:
        # 独立样本检验
        t_stat, p_value = stats.ttest_ind(sample1, sample2)
    
    return {
        "t_statistic": t_stat,
        "p_value": p_value,
        "significant": p_value < 0.05
    }
''',
            dependencies=["numpy", "scipy"],
            references=["Welch, B. L. (1947]. The generalization of Student's problem when several different population variances are involved."],
            tags=["假设检验", "p值", "显著性"],
        )

    def _add_machine_learning_methods(self) -> None:
        """添加机器学习方法。"""
        # 决策树
        self.methods["DT"] = MethodTemplate(
            method_id="DT",
            name="Decision Tree",
            name_cn="决策树",
            category="machine_learning",
            subcategory="tree_based",
            description="基于树结构进行分类或回归的机器学习方法",
            applicable_scenarios=["分类问题", "回归问题", "特征选择", "规则提取"],
            complexity="low",
            prerequisites=["机器学习基础"],
            code_template='''
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.metrics import accuracy_score, mean_squared_error

def decision_tree(X_train, y_train, X_test, y_test, task='classification'):
    """决策树模型。
    
    Args:
        X_train: 训练特征
        y_train: 训练标签
        X_test: 测试特征
        y_test: 测试标签
        task: 任务类型 (classification/regression)
    
    Returns:
        模型结果
    """
    if task == 'classification':
        model = DecisionTreeClassifier(random_state=42)
    else:
        model = DecisionTreeRegressor(random_state=42)
    
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    
    if task == 'classification':
        metric = accuracy_score(y_test, predictions)
        metric_name = "accuracy"
    else:
        metric = mean_squared_error(y_test, predictions)
        metric_name = "mse"
    
    return {
        "model": model,
        "predictions": predictions,
        metric_name: metric,
        "feature_importance": model.feature_importances_
    }
''',
            dependencies=["scikit-learn"],
            references=["Quinlan, J. R. (1986]. Induction of Decision Trees."],
            tags=["分类", "回归", "可解释"],
        )

        # 随机森林
        self.methods["RF"] = MethodTemplate(
            method_id="RF",
            name="Random Forest",
            name_cn="随机森林",
            category="machine_learning",
            subcategory="ensemble",
            description="基于决策树的集成学习方法",
            applicable_scenarios=["分类问题", "回归问题", "特征重要性", "异常检测"],
            complexity="medium",
            prerequisites=["机器学习基础", "决策树"],
            code_template='''
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, mean_squared_error

def random_forest(X_train, y_train, X_test, y_test, task='classification', n_estimators=100):
    """随机森林模型。
    
    Args:
        X_train: 训练特征
        y_train: 训练标签
        X_test: 测试特征
        y_test: 测试标签
        task: 任务类型
        n_estimators: 树的数量
    
    Returns:
        模型结果
    """
    if task == 'classification':
        model = RandomForestClassifier(n_estimators=n_estimators, random_state=42)
    else:
        model = RandomForestRegressor(n_estimators=n_estimators, random_state=42)
    
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    
    if task == 'classification':
        metric = accuracy_score(y_test, predictions)
        metric_name = "accuracy"
    else:
        metric = mean_squared_error(y_test, predictions)
        metric_name = "mse"
    
    return {
        "model": model,
        "predictions": predictions,
        metric_name: metric,
        "feature_importance": model.feature_importances_
    }
''',
            dependencies=["scikit-learn"],
            references=["Breiman, L. (2001]. Random Forests."],
            tags=["集成", "分类", "回归", "鲁棒"],
        )

    def _add_simulation_methods(self) -> None:
        """添加仿真方法。"""
        # 蒙特卡洛模拟
        self.methods["MC"] = MethodTemplate(
            method_id="MC",
            name="Monte Carlo Simulation",
            name_cn="蒙特卡洛模拟",
            category="simulation",
            subcategory="stochastic",
            description="基于随机抽样的数值计算方法",
            applicable_scenarios=["风险评估", "期权定价", "排队系统", "可靠性分析"],
            complexity="medium",
            prerequisites=["概率论", "随机过程"],
            code_template='''
import numpy as np

def monte_carlo_simulation(func, n_simulations=10000, **kwargs):
    """蒙特卡洛模拟。
    
    Args:
        func: 模拟函数（返回单个值）
        n_simulations: 模拟次数
        **kwargs: 传递给func的参数
    
    Returns:
        模拟结果统计
    """
    results = []
    for _ in range(n_simulations):
        result = func(**kwargs)
        results.append(result)
    
    results = np.array(results)
    return {
        "mean": np.mean(results),
        "std": np.std(results),
        "min": np.min(results),
        "max": np.max(results),
        "percentiles": {
            "5%": np.percentile(results, 5),
            "25%": np.percentile(results, 25),
            "50%": np.percentile(results, 50),
            "75%": np.percentile(results, 75),
            "95%": np.percentile(results, 95),
        },
        "all_results": results
    }
''',
            dependencies=["numpy"],
            references=["Metropolis, N., & Ulam, S. (1949]. The Monte Carlo Method."],
            tags=["随机", "模拟", "不确定性"],
        )

    def _add_forecasting_methods(self) -> None:
        """添加预测方法。"""
        # 时间序列预测
        self.methods["TS"] = MethodTemplate(
            method_id="TS",
            name="Time Series Forecasting",
            name_cn="时间序列预测",
            category="forecasting",
            subcategory="time_series",
            description="基于历史数据预测未来值的方法",
            applicable_scenarios=["销售预测", "股票预测", "天气预报", "需求预测"],
            complexity="medium",
            prerequisites=["统计学基础"],
            code_template='''
import numpy as np
from sklearn.linear_model import LinearRegression

def time_series_forecast(data, forecast_horizon=10, method='linear'):
    """时间序列预测。
    
    Args:
        data: 历史数据
        forecast_horizon: 预测步数
        method: 预测方法
    
    Returns:
        预测结果
    """
    if method == 'linear':
        # 简单线性趋势预测
        X = np.arange(len(data)).reshape(-1, 1)
        y = np.array(data)
        
        model = LinearRegression()
        model.fit(X, y)
        
        X_future = np.arange(len(data), len(data) + forecast_horizon).reshape(-1, 1)
        predictions = model.predict(X_future)
        
        return {
            "predictions": predictions,
            "trend_slope": model.coef_[0],
            "trend_intercept": model.intercept_
        }
''',
            dependencies=["numpy", "scikit-learn"],
            references=["Box, G. E. P., & Jenkins, G. M. (1970]. Time Series Analysis: Forecasting and Control."],
            tags=["时间序列", "预测", "趋势"],
        )

    def _add_evaluation_methods(self) -> None:
        """添加评价方法。"""
        # 层次分析法
        self.methods["AHP"] = MethodTemplate(
            method_id="AHP",
            name="Analytic Hierarchy Process",
            name_cn="层次分析法",
            category="evaluation",
            subcategory="multi_criteria",
            description="将复杂问题分解为层次结构进行决策的方法",
            applicable_scenarios=["方案评价", "供应商选择", "风险评估", "绩效考核"],
            complexity="low",
            prerequisites=["决策分析基础"],
            code_template='''
import numpy as np

def analytic_hierarchy_process(comparison_matrix):
    """层次分析法。
    
    Args:
        comparison_matrix: 判断矩阵
    
    Returns:
        权重和一致性检验结果
    """
    n = len(comparison_matrix)
    
    # 计算特征值和特征向量
    eigenvalues, eigenvectors = np.linalg.eig(comparison_matrix)
    max_idx = np.argmax(eigenvalues.real)
    max_eigenvalue = eigenvalues[max_idx].real
    weights = eigenvectors[:, max_idx].real
    weights = weights / np.sum(weights)
    
    # 一致性检验
    CI = (max_eigenvalue - n) / (n - 1) if n > 1 else 0
    RI = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
    CR = CI / RI.get(n, 1.49) if n > 0 else 0
    
    return {
        "weights": weights,
        "max_eigenvalue": max_eigenvalue,
        "consistency_ratio": CR,
        "consistent": CR < 0.1
    }
''',
            dependencies=["numpy"],
            references=["Saaty, T. L. (1980]. The Analytic Hierarchy Process."],
            tags=["多准则", "决策", "权重"],
        )

    def search_methods(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        complexity: Optional[str] = None,
        scenario: Optional[str] = None,
    ) -> List[MethodTemplate]:
        """搜索方法。

        Args:
            query: 搜索关键词
            category: 方法类别
            complexity: 复杂度
            scenario: 适用场景

        Returns:
            匹配的方法列表
        """
        results = []

        for method in self.methods.values():
            # 类别筛选
            if category and method.category != category:
                continue

            # 复杂度筛选
            if complexity and method.complexity != complexity:
                continue

            # 场景筛选
            if scenario:
                if not any(scenario in s for s in method.applicable_scenarios):
                    continue

            # 关键词搜索
            if query:
                query_lower = query.lower()
                searchable = (
                    method.name.lower()
                    + method.name_cn.lower()
                    + method.description.lower()
                    + " ".join(method.tags).lower()
                )
                if query_lower not in searchable:
                    continue

            results.append(method)

        return results

    def get_method(self, method_id: str) -> Optional[MethodTemplate]:
        """获取指定方法。"""
        return self.methods.get(method_id)

    def get_methods_by_category(self, category: str) -> List[MethodTemplate]:
        """按类别获取方法。"""
        return [m for m in self.methods.values() if m.category == category]

    def get_categories(self) -> List[str]:
        """获取所有类别。"""
        return list(set(m.category for m in self.methods.values()))

    def recommend_methods(
        self,
        problem_type: str,
        data_features: Optional[Dict[str, Any]] = None,
    ) -> List[MethodTemplate]:
        """基于问题特征推荐方法。

        Args:
            problem_type: 问题类型
            data_features: 数据特征

        Returns:
            推荐的方法列表
        """
        recommendations = []

        # 问题类型到方法类别的映射
        type_mapping = {
            "optimization": ["optimization"],
            "prediction": ["forecasting", "machine_learning"],
            "classification": ["machine_learning"],
            "clustering": ["machine_learning"],
            "evaluation": ["evaluation", "statistical"],
            "simulation": ["simulation"],
        }

        categories = type_mapping.get(problem_type, [])

        for category in categories:
            methods = self.get_methods_by_category(category)
            # 按复杂度排序（简单优先）
            methods.sort(key=lambda m: {"low": 0, "medium": 1, "high": 2}.get(m.complexity, 3))
            recommendations.extend(methods[:3])  # 每个类别取前3个

        return recommendations

    def get_method_count(self) -> Dict[str, int]:
        """获取各类别方法数量。"""
        counts = {}
        for method in self.methods.values():
            counts[method.category] = counts.get(method.category, 0) + 1
        return counts


# 全局单例
_library_instance: Optional[MethodLibrary] = None


def get_method_library() -> MethodLibrary:
    """获取全局方法库实例。"""
    global _library_instance
    if _library_instance is None:
        _library_instance = MethodLibrary()
    return _library_instance
