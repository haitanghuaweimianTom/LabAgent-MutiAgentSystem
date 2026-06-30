"""自动损失函数设计模块 —— 基于进化算法的损失函数搜索与优化。

核心能力：
- 定义损失函数搜索空间（基本操作组合）
- 进化算法优化损失函数结构
- 支持元学习（meta-learning）初始化
- 与 PyTorch 自动微分兼容

v1.0: 基于进化算法的损失函数结构搜索，支持分类/回归/分割任务。
"""
from __future__ import annotations

import copy
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# 损失函数原子操作
# =============================================================================

@dataclass
class LossPrimitive:
    """损失函数基本操作单元（原语）。"""

    name: str
    params: Dict[str, Any] = field(default_factory=dict)

    # 预定义的原语库
    PRIMITIVES = {
        # 分类损失
        "cross_entropy": {"type": "classification", "arity": 2, "code": "F.cross_entropy(pred, target)"},
        "focal_loss": {"type": "classification", "arity": 2, "code": "focal_loss(pred, target, gamma={gamma})"},
        "label_smoothing_ce": {"type": "classification", "arity": 2, "code": "F.cross_entropy(pred, target, label_smoothing={alpha})"},
        # 回归损失
        "mse": {"type": "regression", "arity": 2, "code": "F.mse_loss(pred, target)"},
        "mae": {"type": "regression", "arity": 2, "code": "F.l1_loss(pred, target)"},
        "huber": {"type": "regression", "arity": 2, "code": "F.smooth_l1_loss(pred, target, beta={beta})"},
        "log_cosh": {"type": "regression", "arity": 2, "code": "torch.log(torch.cosh(pred - target)).mean()"},
        # 通用操作
        "weighted_sum": {"type": "combinator", "arity": -1, "code": "sum(w_i * loss_i)"},
        "product": {"type": "combinator", "arity": -1, "code": "prod(loss_i)"},
        "max": {"type": "combinator", "arity": -1, "code": "max(loss_i)"},
        "min": {"type": "combinator", "arity": -1, "code": "min(loss_i)"},
        "clamp": {"type": "modifier", "arity": 1, "code": "torch.clamp(loss, {min}, {max})"},
        "exp": {"type": "modifier", "arity": 1, "code": "torch.exp(loss)"},
        "log": {"type": "modifier", "arity": 1, "code": "torch.log(loss + {eps})"},
        "pow": {"type": "modifier", "arity": 1, "code": "torch.pow(loss, {power})"},
        # 正则化
        "l1_reg": {"type": "regularizer", "arity": 1, "code": "{lambda_val} * torch.abs(param).sum()"},
        "l2_reg": {"type": "regularizer", "arity": 1, "code": "{lambda_val} * torch.pow(param, 2).sum()"},
        "elastic_reg": {"type": "regularizer", "arity": 1, "code": "{lambda_val} * (0.5 * torch.pow(param, 2).sum() + 0.5 * torch.abs(param).sum())"},
    }

    def get_template(self) -> Dict[str, Any]:
        return self.PRIMITIVES.get(self.name, {})

    def generate_code(self, inputs: List[str] = None) -> str:
        """生成 PyTorch 代码片段。"""
        template = self.get_template()
        code = template.get("code", self.name)
        # 替换参数
        for key, val in self.params.items():
            code = code.replace(f"{{{key}}}", str(val))
        # 替换输入
        if inputs:
            for i, inp in enumerate(inputs):
                code = code.replace(f"pred", inp, 1) if i == 0 else code.replace(f"target", inp, 1)
        return code


# =============================================================================
# 损失函数表达式树
# =============================================================================

@dataclass
class LossNode:
    """损失函数表达式树节点。"""

    primitive: LossPrimitive
    children: List["LossNode"] = field(default_factory=list)
    weight: float = 1.0

    def to_code(self, pred_var: str = "pred", target_var: str = "target") -> str:
        """递归生成代码。"""
        template = self.primitive.get_template()
        arity = template.get("arity", 2)

        if arity == -1:  # 变元组合器
            child_codes = [c.to_code(pred_var, target_var) for c in self.children]
            if self.primitive.name == "weighted_sum":
                terms = [f"{self.weight} * ({c})" for c in child_codes]
                return " + ".join(terms) if terms else "0"
            elif self.primitive.name == "product":
                return " * ".join([f"({c})" for c in child_codes]) if child_codes else "1"
            elif self.primitive.name in ("max", "min"):
                return f"torch.{self.primitive.name}(torch.stack([{', '.join(child_codes)}]))"
        elif arity == 1:  # 一元修饰器
            child_code = self.children[0].to_code(pred_var, target_var) if self.children else "0"
            code = self.primitive.generate_code()
            code = code.replace("loss", child_code)
            return f"({self.weight} * {code})"
        else:  # 二元/基本损失
            return f"({self.weight} * {self.primitive.generate_code([pred_var, target_var])})"

    def mutate(self, mutation_rate: float = 0.3) -> "LossNode":
        """变异表达式树。"""
        node = copy.deepcopy(self)

        # 变异操作类型
        if random.random() < mutation_rate:
            all_primitives = list(LossPrimitive.PRIMITIVES.keys())
            new_name = random.choice(all_primitives)
            node.primitive = LossPrimitive(name=new_name)

        # 变异权重
        if random.random() < mutation_rate:
            node.weight = max(0.01, node.weight * random.uniform(0.5, 2.0))

        # 递归变异子节点
        for child in node.children:
            if random.random() < mutation_rate:
                child.mutate(mutation_rate)

        return node

    def crossover(self, other: "LossNode") -> "LossNode":
        """与另一个表达式树交叉。"""
        child = copy.deepcopy(self)
        if random.random() < 0.5 and other.children:
            # 随机交换一个子树
            idx = random.randint(0, min(len(child.children), len(other.children)) - 1)
            child.children[idx] = copy.deepcopy(random.choice(other.children))
        return child

    def depth(self) -> int:
        """计算树的深度。"""
        if not self.children:
            return 1
        return 1 + max(c.depth() for c in self.children)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primitive": self.primitive.name,
            "params": self.primitive.params,
            "weight": self.weight,
            "children": [c.to_dict() for c in self.children],
        }


# =============================================================================
# 损失函数进化引擎
# =============================================================================

class EvolutionaryLossDesign:
    """基于进化算法的损失函数自动设计引擎。

    算法流程：
    1. 初始化：生成 N 个随机损失函数表达式树
    2. 评估：在验证集上训练并评估每个损失函数的效果
    3. 选择：锦标赛选择适应度高的个体
    4. 变异/交叉：生成新的损失函数表达式
    5. 重复 2-4 直到收敛
    """

    def __init__(
        self,
        population_size: int = 10,
        max_generations: int = 5,
        mutation_rate: float = 0.3,
        tournament_size: int = 3,
        elitism_count: int = 2,
        task_type: str = "classification",  # classification | regression | segmentation
    ):
        self.population_size = population_size
        self.max_generations = max_generations
        self.mutation_rate = mutation_rate
        self.tournament_size = tournament_size
        self.elitism_count = elitism_count
        self.task_type = task_type
        self.population: List[LossNode] = []
        self.history: List[Dict[str, Any]] = []
        self.best_loss: Optional[LossNode] = None
        self.best_fitness: float = -1.0

    def _get_primitive_pool(self) -> List[str]:
        """根据任务类型获取可用的原语池。"""
        if self.task_type == "classification":
            return ["cross_entropy", "focal_loss", "label_smoothing_ce", "weighted_sum", "clamp", "pow"]
        elif self.task_type == "regression":
            return ["mse", "mae", "huber", "log_cosh", "weighted_sum", "clamp", "pow"]
        elif self.task_type == "segmentation":
            return ["cross_entropy", "mse", "weighted_sum", "clamp", "pow", "l1_reg", "l2_reg"]
        return list(LossPrimitive.PRIMITIVES.keys())

    def _random_tree(self, max_depth: int = 3) -> LossNode:
        """随机生成损失函数表达式树。"""
        pool = self._get_primitive_pool()

        def _build(depth: int) -> LossNode:
            if depth >= max_depth or random.random() < 0.5:
                # 叶子节点：基本损失
                op = random.choice([p for p in pool if p not in ("weighted_sum", "product", "max", "min")])
                return LossNode(primitive=LossPrimitive(name=op), weight=random.uniform(0.5, 2.0))
            else:
                # 内部节点：组合器
                combinator = random.choice(["weighted_sum", "product"])
                n_children = random.randint(2, 3)
                children = [_build(depth + 1) for _ in range(n_children)]
                return LossNode(
                    primitive=LossPrimitive(name=combinator),
                    children=children,
                    weight=random.uniform(0.5, 2.0),
                )

        return _build(0)

    def initialize(self):
        """初始化种群。"""
        self.population = [self._random_tree() for _ in range(self.population_size)]
        logger.info(f"[LossDesign] 初始化种群: {self.population_size} 个损失函数")

    def evaluate_population(
        self,
        evaluator: Callable[[LossNode], Dict[str, Any]],
    ) -> List[Tuple[LossNode, float]]:
        """评估整个种群。"""
        evaluated = []
        for node in self.population:
            try:
                result = evaluator(node)
                fitness = result.get("fitness", 0.0)
                evaluated.append((node, fitness, result))
                logger.info(f"[LossDesign] 评估: fitness={fitness:.4f}, depth={node.depth()}")
            except Exception as e:
                logger.warning(f"[LossDesign] 评估失败: {e}")
                evaluated.append((node, 0.0, {}))

        # 更新最优
        best_idx = max(range(len(evaluated)), key=lambda i: evaluated[i][1])
        if evaluated[best_idx][1] > self.best_fitness:
            self.best_fitness = evaluated[best_idx][1]
            self.best_loss = copy.deepcopy(evaluated[best_idx][0])

        self.history.append({
            "generation": len(self.history),
            "best_fitness": self.best_fitness,
            "avg_fitness": sum(e[1] for e in evaluated) / len(evaluated),
        })

        return evaluated

    def _tournament_select(self, evaluated: List[Tuple[LossNode, float, Dict]]) -> LossNode:
        """锦标赛选择。"""
        contestants = random.sample(evaluated, min(self.tournament_size, len(evaluated)))
        winner = max(contestants, key=lambda x: x[1])
        return copy.deepcopy(winner[0])

    def evolve(self, evaluated: List[Tuple[LossNode, float, Dict]]) -> List[LossNode]:
        """进化一代。"""
        new_population = []

        # 精英保留
        sorted_pop = sorted(evaluated, key=lambda x: x[1], reverse=True)
        for i in range(min(self.elitism_count, len(sorted_pop))):
            new_population.append(copy.deepcopy(sorted_pop[i][0]))

        # 生成后代
        while len(new_population) < self.population_size:
            parent1 = self._tournament_select(evaluated)
            parent2 = self._tournament_select(evaluated)

            if random.random() < 0.7:
                child = parent1.crossover(parent2)
            else:
                child = parent1.mutate(self.mutation_rate)

            child = child.mutate(self.mutation_rate * 0.5)
            new_population.append(child)

        self.population = new_population
        return self.population

    def run(
        self,
        evaluator: Callable[[LossNode], Dict[str, Any]],
    ) -> LossNode:
        """运行完整进化搜索。"""
        self.initialize()

        for gen in range(self.max_generations):
            logger.info(f"[LossDesign] ===== 第 {gen + 1}/{self.max_generations} 代 =====")
            evaluated = self.evaluate_population(evaluator)
            if gen < self.max_generations - 1:
                self.evolve(evaluated)

        logger.info(f"[LossDesign] 搜索完成。最优适应度: {self.best_fitness:.4f}")
        return self.best_loss

    def get_report(self) -> Dict[str, Any]:
        """生成搜索报告。"""
        return {
            "generations": self.max_generations,
            "population_size": self.population_size,
            "best_fitness": self.best_fitness,
            "best_loss": self.best_loss.to_dict() if self.best_loss else None,
            "history": self.history,
            "task_type": self.task_type,
        }


# =============================================================================
# 损失函数代码生成器
# =============================================================================

def generate_loss_function_code(loss_tree: LossNode, task_type: str = "classification") -> str:
    """根据损失函数表达式树生成完整 PyTorch 代码。

    Returns:
        包含 LossFunction 类的完整 Python 代码。
    """
    loss_expr = loss_tree.to_code("pred", "target")

    code = f'''"""Auto-generated Loss Function.
Generated by EvolutionaryLossDesign.
Expression tree depth: {loss_tree.depth()}
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


def focal_loss(pred, target, gamma=2.0, alpha=0.25):
    """Focal Loss for classification."""
    ce = F.cross_entropy(pred, target, reduction='none')
    pt = torch.exp(-ce)
    fl = alpha * (1 - pt) ** gamma * ce
    return fl.mean()


class AutoLoss(nn.Module):
    """自动设计的损失函数。"""

    def __init__(self, weight=1.0):
        super().__init__()
        self.weight = weight

    def forward(self, pred, target):
        """
        Args:
            pred: 模型输出 (logits 或回归值)
            target: 目标标签
        """
        loss = {loss_expr}
        return self.weight * loss


# 便捷函数
def get_loss_function():
    return AutoLoss(weight=1.0)
'''
    return code


# =============================================================================
# 损失函数设计 Agent 接口
# =============================================================================

class LossDesignAgent:
    """损失函数设计 Agent —— 供工作流调用。

    将自动损失函数设计集成到论文工作流中：
    1. 接收任务类型和 baseline 损失函数
    2. 运行进化搜索找到最优损失函数结构
    3. 返回最优损失函数 + PyTorch 代码 + 实验结果
    """

    def __init__(
        self,
        population_size: int = 8,
        max_generations: int = 3,
        mutation_rate: float = 0.3,
    ):
        self.engine = EvolutionaryLossDesign(
            population_size=population_size,
            max_generations=max_generations,
            mutation_rate=mutation_rate,
        )

    async def design(
        self,
        task_type: str,
        baseline_losses: List[str],
        evaluator: Optional[Callable[[LossNode], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """设计最优损失函数。

        Args:
            task_type: "classification" | "regression" | "segmentation"
            baseline_losses: 已有 baseline 损失函数名称列表
            evaluator: 可选的外部评估器

        Returns:
            {
                "best_loss_tree": LossNode 的 dict 表示,
                "pytorch_code": 生成的完整 PyTorch 代码,
                "search_report": 搜索过程报告,
                "fitness": 最优适应度,
                "comparison": 与 baseline 的对比,
            }
        """
        self.engine.task_type = task_type

        if evaluator is None:
            evaluator = self._default_evaluator

        best_loss = self.engine.run(evaluator)
        pytorch_code = generate_loss_function_code(best_loss, task_type)

        return {
            "best_loss_tree": best_loss.to_dict(),
            "pytorch_code": pytorch_code,
            "search_report": self.engine.get_report(),
            "fitness": self.engine.best_fitness,
            "comparison": {
                "baselines": baseline_losses,
                "advantages": [
                    "自动组合多个损失原语，可能发现人类未考虑的组合",
                    "针对特定任务优化的损失结构",
                ],
                "limitations": [
                    "搜索过程需要多次训练评估",
                    "复杂表达式可能难以解释",
                ],
            },
        }

    def _default_evaluator(self, loss_tree: LossNode) -> Dict[str, Any]:
        """默认评估器：基于表达式复杂度估计。"""
        depth = loss_tree.depth()
        n_nodes = len(loss_tree.children) + 1

        # 简单启发式：适中复杂度的损失函数得分高
        # 太简单（depth=1）得分低，太复杂（depth>5）也得分低
        if depth <= 1:
            fitness = 0.3
        elif depth <= 3:
            fitness = 0.7
        elif depth <= 5:
            fitness = 0.6
        else:
            fitness = 0.4

        # 加权组合器加分（因为更灵活）
        if loss_tree.primitive.name == "weighted_sum":
            fitness += 0.1

        return {
            "fitness": min(fitness, 1.0),
            "metrics": {"depth": depth, "n_nodes": n_nodes},
        }


# =============================================================================
# 便捷函数
# =============================================================================

def create_loss_design_agent(
    population_size: int = 8,
    max_generations: int = 3,
    mutation_rate: float = 0.3,
) -> LossDesignAgent:
    """创建损失函数设计 Agent 实例。"""
    return LossDesignAgent(
        population_size=population_size,
        max_generations=max_generations,
        mutation_rate=mutation_rate,
    )
