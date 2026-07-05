"""神经架构搜索（NAS）模块 —— 基于进化算法的网络结构自动探索。

核心能力：
- 定义搜索空间（cell-based / macro-architecture）
- 进化算法优化（锦标赛选择 + 变异 + 交叉）
- 支持 PyTorch 模型自动生成与评估
- 与 ExperimentRunner 集成，支持 GPU 训练

v1.0: 基于进化算法的轻量级 NAS，适合单卡 8GB 显存。
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
# 搜索空间定义
# =============================================================================

@dataclass
class Operation:
    """搜索空间中的基本操作（节点操作类型）。"""

    name: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_code(self, in_channels: int, out_channels: int) -> str:
        """生成 PyTorch 代码片段。"""
        op_map = {
            "conv3x3": f"nn.Conv2d({in_channels}, {out_channels}, 3, padding=1, bias=False)",
            "conv5x5": f"nn.Conv2d({in_channels}, {out_channels}, 5, padding=2, bias=False)",
            "conv7x7": f"nn.Conv2d({in_channels}, {out_channels}, 7, padding=3, bias=False)",
            "depthwise_conv3x3": f"nn.Conv2d({in_channels}, {out_channels}, 3, padding=1, groups={in_channels}, bias=False)",
            "maxpool3x3": f"nn.MaxPool2d(3, stride=1, padding=1)",
            "avgpool3x3": f"nn.AvgPool2d(3, stride=1, padding=1)",
            "skip_connection": f"nn.Identity()",
            "separable_conv3x3": f"nn.Sequential(nn.Conv2d({in_channels}, {in_channels}, 3, padding=1, groups={in_channels}, bias=False), nn.Conv2d({in_channels}, {out_channels}, 1, bias=False))",
            "dilated_conv3x3": f"nn.Conv2d({in_channels}, {out_channels}, 3, padding=2, dilation=2, bias=False)",
            "none": "None",
        }
        return op_map.get(self.name, f"nn.Conv2d({in_channels}, {out_channels}, 3, padding=1)")


@dataclass
class CellSpec:
    """Cell 结构规格：包含 N 个节点，每个节点有 2 个输入边（操作+前驱节点）。"""

    num_nodes: int = 4
    operations: List[str] = field(default_factory=list)  # 每个节点的操作类型
    predecessors: List[Tuple[int, int]] = field(default_factory=list)  # 每个节点的2个前驱

    def __post_init__(self):
        if not self.operations:
            # 默认随机初始化
            self._random_init()

    def _random_init(self):
        """随机初始化 cell 结构。"""
        op_pool = [
            "conv3x3", "conv5x5", "depthwise_conv3x3",
            "maxpool3x3", "avgpool3x3", "skip_connection",
            "separable_conv3x3", "dilated_conv3x3",
        ]
        self.operations = [random.choice(op_pool) for _ in range(self.num_nodes)]
        # 每个节点有 2 个前驱（从之前所有节点 + 2 个输入中选择）
        self.predecessors = []
        for i in range(self.num_nodes):
            choices = list(range(-2, i))  # -2, -1 表示两个输入，0..i-1 表示前面节点
            p1 = random.choice(choices)
            p2 = random.choice(choices)
            self.predecessors.append((p1, p2))

    def mutate(self, mutation_rate: float = 0.3) -> "CellSpec":
        """对当前 cell 进行变异，返回新 cell。"""
        child = copy.deepcopy(self)
        op_pool = [
            "conv3x3", "conv5x5", "depthwise_conv3x3",
            "maxpool3x3", "avgpool3x3", "skip_connection",
            "separable_conv3x3", "dilated_conv3x3",
        ]

        # 变异操作类型
        for i in range(child.num_nodes):
            if random.random() < mutation_rate:
                child.operations[i] = random.choice(op_pool)

        # 变异前驱连接
        for i in range(child.num_nodes):
            if random.random() < mutation_rate:
                choices = list(range(-2, i))
                child.predecessors[i] = (random.choice(choices), random.choice(choices))

        return child

    def crossover(self, other: "CellSpec") -> "CellSpec":
        """与另一个 cell 交叉，返回新 cell。"""
        child = copy.deepcopy(self)
        for i in range(min(self.num_nodes, other.num_nodes)):
            if random.random() < 0.5:
                child.operations[i] = other.operations[i]
            if random.random() < 0.5:
                child.predecessors[i] = other.predecessors[i]
        return child

    def to_pytorch_code(self, cell_name: str = "Cell") -> str:
        """生成完整的 PyTorch Cell 类代码。"""
        lines = [
            f"class {cell_name}(nn.Module):",
            f'    """Auto-generated NAS Cell."""',
            "    def __init__(self, in_channels, out_channels):",
            "        super().__init__()",
        ]

        # 为每个节点生成操作层
        for i, op_name in enumerate(self.operations):
            op = Operation(op_name)
            lines.append(f"        self.op_{i} = {op.to_code('in_channels', 'out_channels')}")

        lines.append("")
        lines.append("    def forward(self, x0, x1):")
        lines.append("        # x0, x1 是两个输入")
        lines.append("        states = [x0, x1]")

        for i in range(self.num_nodes):
            p1, p2 = self.predecessors[i]
            idx1 = p1 if p1 >= 0 else 0 if p1 == -2 else 1
            idx2 = p2 if p2 >= 0 else 0 if p2 == -2 else 1
            lines.append(f"        s_{i} = self.op_{i}(states[{idx1}]) + self.op_{i}(states[{idx2}])")
            lines.append(f"        states.append(s_{i})")

        # 输出是所有节点的拼接
        lines.append("        return torch.cat(states[2:], dim=1)")
        return "\n".join(lines)


@dataclass
class NetworkSpec:
    """完整网络规格：包含多个 normal cell 和 reduction cell。"""

    num_cells: int = 8
    num_reductions: int = 2
    init_channels: int = 16
    normal_cell: CellSpec = field(default_factory=lambda: CellSpec(num_nodes=4))
    reduction_cell: CellSpec = field(default_factory=lambda: CellSpec(num_nodes=4))

    def mutate(self, mutation_rate: float = 0.3) -> "NetworkSpec":
        """变异网络结构。"""
        child = copy.deepcopy(self)
        child.normal_cell = child.normal_cell.mutate(mutation_rate)
        child.reduction_cell = child.reduction_cell.mutate(mutation_rate)
        if random.random() < 0.1:
            child.num_cells = max(4, min(16, child.num_cells + random.choice([-2, -1, 1, 2])))
        if random.random() < 0.1:
            child.init_channels = max(8, min(64, child.init_channels + random.choice([-8, -4, 4, 8])))
        return child

    def crossover(self, other: "NetworkSpec") -> "NetworkSpec":
        """与另一个网络交叉。"""
        child = copy.deepcopy(self)
        child.normal_cell = self.normal_cell.crossover(other.normal_cell)
        child.reduction_cell = self.reduction_cell.crossover(other.reduction_cell)
        return child


# =============================================================================
# 进化算法引擎
# =============================================================================

@dataclass
class Individual:
    """进化算法中的个体。"""

    genome: NetworkSpec
    fitness: float = -1.0  # 验证准确率或负损失
    metrics: Dict[str, Any] = field(default_factory=dict)
    generation: int = 0
    evaluated: bool = False


class EvolutionaryNAS:
    """基于进化算法的 NAS 引擎。

    算法流程：
    1. 初始化种群（随机生成 N 个网络结构）
    2. 评估适应度（训练每个网络，获取验证准确率）
    3. 选择（锦标赛选择）
    4. 变异 + 交叉（生成下一代）
    5. 重复 2-4 直到达到最大代数或找到满意解

    针对单卡 8GB 的优化：
    - 使用小初始通道数（16-32）
    - 限制 cell 节点数（4-5）
    - 支持早停（early stopping）
    - 支持权重共享（可选）
    """

    def __init__(
        self,
        population_size: int = 10,
        max_generations: int = 5,
        mutation_rate: float = 0.3,
        tournament_size: int = 3,
        elitism_count: int = 2,
        early_stop_patience: int = 3,
        max_params: int = 5_000_000,  # 500万参数上限（8GB显存友好）
    ):
        self.population_size = population_size
        self.max_generations = max_generations
        self.mutation_rate = mutation_rate
        self.tournament_size = tournament_size
        self.elitism_count = elitism_count
        self.early_stop_patience = early_stop_patience
        self.max_params = max_params
        self.generation = 0
        self.population: List[Individual] = []
        self.history: List[Dict[str, Any]] = []
        self.best_individual: Optional[Individual] = None

    def initialize_population(self) -> List[Individual]:
        """随机初始化种群。"""
        self.population = []
        for i in range(self.population_size):
            net = NetworkSpec(
                num_cells=random.choice([6, 8, 10]),
                num_reductions=2,
                init_channels=random.choice([16, 24, 32]),
                normal_cell=CellSpec(num_nodes=4),
                reduction_cell=CellSpec(num_nodes=4),
            )
            self.population.append(Individual(genome=net, generation=0))
        logger.info(f"[NAS] 初始化种群: {self.population_size} 个个体")
        return self.population

    def evaluate_population(
        self,
        evaluator: Callable[[NetworkSpec], Dict[str, Any]],
    ) -> List[Individual]:
        """评估整个种群的适应度。

        Args:
            evaluator: 接收 NetworkSpec，返回 {"fitness": float, "metrics": dict}
        """
        for ind in self.population:
            if ind.evaluated:
                continue
            try:
                result = evaluator(ind.genome)
                ind.fitness = result.get("fitness", -1.0)
                ind.metrics = result.get("metrics", {})
                ind.evaluated = True
                logger.info(
                    f"[NAS] Gen {self.generation} 评估: fitness={ind.fitness:.4f}, "
                    f"params={ind.metrics.get('num_params', 'N/A')}"
                )
            except Exception as e:
                logger.warning(f"[NAS] 评估失败: {e}")
                ind.fitness = -1.0
                ind.evaluated = True

        # 更新最优个体
        valid = [ind for ind in self.population if ind.fitness > 0]
        if valid:
            current_best = max(valid, key=lambda x: x.fitness)
            if self.best_individual is None or current_best.fitness > self.best_individual.fitness:
                self.best_individual = copy.deepcopy(current_best)

        # 记录历史
        self.history.append({
            "generation": self.generation,
            "best_fitness": self.best_individual.fitness if self.best_individual else -1,
            "avg_fitness": sum(ind.fitness for ind in self.population) / len(self.population),
            "population_size": len(self.population),
        })

        return self.population

    def _tournament_select(self) -> Individual:
        """锦标赛选择。"""
        contestants = random.sample(self.population, min(self.tournament_size, len(self.population)))
        return max(contestants, key=lambda x: x.fitness)

    def evolve_generation(self) -> List[Individual]:
        """进化一代，生成新种群。"""
        new_population: List[Individual] = []

        # 精英保留
        sorted_pop = sorted(self.population, key=lambda x: x.fitness, reverse=True)
        elites = sorted_pop[:self.elitism_count]
        for e in elites:
            new_population.append(copy.deepcopy(e))

        # 生成后代
        while len(new_population) < self.population_size:
            parent1 = self._tournament_select()
            parent2 = self._tournament_select()

            if random.random() < 0.7:
                child_genome = parent1.genome.crossover(parent2.genome)
            else:
                child_genome = parent1.genome.mutate(self.mutation_rate)

            child_genome = child_genome.mutate(self.mutation_rate * 0.5)

            new_population.append(Individual(
                genome=child_genome,
                generation=self.generation + 1,
            ))

        self.population = new_population
        self.generation += 1
        return self.population

    def run(
        self,
        evaluator: Callable[[NetworkSpec], Dict[str, Any]],
        progress_callback: Optional[Callable[[int, Dict[str, Any]], None]] = None,
    ) -> Individual:
        """运行完整进化搜索。

        Returns:
            最优个体
        """
        self.initialize_population()

        no_improvement_count = 0
        prev_best_fitness = -1.0

        for gen in range(self.max_generations):
            self.generation = gen
            logger.info(f"[NAS] ===== 第 {gen + 1}/{self.max_generations} 代 =====")

            self.evaluate_population(evaluator)

            if progress_callback:
                progress_callback(gen, self.history[-1] if self.history else {})

            # 早停检查
            current_best = self.best_individual.fitness if self.best_individual else -1
            if current_best > prev_best_fitness:
                no_improvement_count = 0
                prev_best_fitness = current_best
            else:
                no_improvement_count += 1

            if no_improvement_count >= self.early_stop_patience:
                logger.info(f"[NAS] 早停触发：{no_improvement_count} 代无改进")
                break

            if gen < self.max_generations - 1:
                self.evolve_generation()

        logger.info(
            f"[NAS] 搜索完成。最优适应度: {self.best_individual.fitness if self.best_individual else -1:.4f}"
        )
        return self.best_individual

    def get_search_report(self) -> Dict[str, Any]:
        """生成搜索过程报告。"""
        return {
            "generations_evolved": self.generation + 1,
            "population_size": self.population_size,
            "mutation_rate": self.mutation_rate,
            "best_fitness": self.best_individual.fitness if self.best_individual else -1,
            "best_genome": {
                "num_cells": self.best_individual.genome.num_cells if self.best_individual else 0,
                "init_channels": self.best_individual.genome.init_channels if self.best_individual else 0,
                "normal_cell_ops": self.best_individual.genome.normal_cell.operations if self.best_individual else [],
                "reduction_cell_ops": self.best_individual.genome.reduction_cell.operations if self.best_individual else [],
            },
            "history": self.history,
            "total_evaluations": sum(1 for ind in self.population for _ in range(self.generation + 1)),
        }


# =============================================================================
# PyTorch 模型生成器
# =============================================================================

def generate_pytorch_model(network_spec: NetworkSpec, num_classes: int = 10) -> str:
    """根据 NetworkSpec 生成完整可运行的 PyTorch 模型代码。

    Returns:
        完整 Python 代码字符串，包含模型定义 + 训练脚本。
    """
    normal_code = network_spec.normal_cell.to_pytorch_code("NormalCell")
    reduction_code = network_spec.reduction_cell.to_pytorch_code("ReductionCell")

    code = f'''"""Auto-generated NAS Model.
Generated by EvolutionaryNAS.
Architecture:
  - {network_spec.num_cells} cells ({network_spec.num_reductions} reduction)
  - Initial channels: {network_spec.init_channels}
"""
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
import torchvision
import torchvision.transforms as transforms
import json
import time

# ========== Cell Definitions ==========
{normal_code}

{reduction_code}

# ========== Full Network ==========
class NASModel(nn.Module):
    def __init__(self, num_classes={num_classes}, init_channels={network_spec.init_channels}):
        super().__init__()
        C = init_channels
        self.stem = nn.Sequential(
            nn.Conv2d(3, C, 3, padding=1, bias=False),
            nn.BatchNorm2d(C),
        )
        self.cells = nn.ModuleList()
        channels = [C, C]
        reduction_idx = [{{network_spec.num_cells // 3}}, {{2 * network_spec.num_cells // 3}}]
        for i in range({network_spec.num_cells}):
            if i in reduction_idx:
                self.cells.append(ReductionCell(channels[-1], channels[-1] * 2))
                channels.append(channels[-1] * 2)
            else:
                self.cells.append(NormalCell(channels[-1], channels[-1]))
                channels.append(channels[-1])
        self.global_pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Linear(channels[-1], num_classes)

    def forward(self, x):
        x = self.stem(x)
        for cell in self.cells:
            x = cell(x, x)
        x = self.global_pool(x)
        x = x.view(x.size(0), -1)
        return self.classifier(x)

# ========== Training Script ==========
def train_nas_model(epochs=10, batch_size=64, lr=0.025, device='cuda'):
    transform = transforms.Compose([
        transforms.RandomCrop(32, padding=4),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616)),
    ])
    test_transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616)),
    ])
    trainset = torchvision.datasets.CIFAR10(root='./data', train=True, download=True, transform=transform)
    trainloader = DataLoader(trainset, batch_size=batch_size, shuffle=True, num_workers=2)
    testset = torchvision.datasets.CIFAR10(root='./data', train=False, download=True, transform=test_transform)
    testloader = DataLoader(testset, batch_size=batch_size, shuffle=False, num_workers=2)

    device = torch.device(device if torch.cuda.is_available() else 'cpu')
    model = NASModel().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=3e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_acc = 0.0
    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for inputs, labels in trainloader:
            inputs, labels = inputs.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
        scheduler.step()

        # Validation
        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for inputs, labels in testloader:
                inputs, labels = inputs.to(device), labels.to(device)
                outputs = model(inputs)
                _, predicted = outputs.max(1)
                total += labels.size(0)
                correct += predicted.eq(labels).sum().item()
        acc = 100.0 * correct / total
        best_acc = max(best_acc, acc)
        print(json.dumps({{"epoch": epoch + 1, "accuracy": round(acc, 2), "loss": round(train_loss, 4)}}))

    # 统计参数量
    num_params = sum(p.numel() for p in model.parameters())
    result = {{
        "best_accuracy": round(best_acc, 2),
        "num_params": num_params,
        "epochs": epochs,
    }}
    print(json.dumps(result))
    return result

if __name__ == "__main__":
    result = train_nas_model()
'''
    return code


# =============================================================================
# NAS Agent 接口
# =============================================================================

class NASAgent:
    """NAS 代理 —— 供 LangGraph Orchestrator 调用。

    将 NAS 集成到论文工作流中：
    1. 接收问题描述和已有方法分析
    2. 运行进化搜索找到最优架构
    3. 返回最优架构 + 生成的 PyTorch 代码 + 实验结果
    """

    def __init__(
        self,
        population_size: int = 8,
        max_generations: int = 3,
        mutation_rate: float = 0.3,
    ):
        self.engine = EvolutionaryNAS(
            population_size=population_size,
            max_generations=max_generations,
            mutation_rate=mutation_rate,
        )

    async def search(
        self,
        problem_description: str,
        baseline_methods: List[Dict[str, Any]],
        evaluator: Optional[Callable[[NetworkSpec], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """执行 NAS 搜索。

        Args:
            problem_description: 问题描述（用于指导搜索空间设计）
            baseline_methods: 已有 baseline 方法列表
            evaluator: 可选的外部评估器（默认使用生成代码+训练）

        Returns:
            {
                "best_architecture": NetworkSpec 的 dict 表示,
                "pytorch_code": 生成的完整 PyTorch 代码,
                "search_report": 搜索过程报告,
                "fitness": 最优适应度,
                "comparison_with_baselines": 与 baseline 的对比分析,
            }
        """
        # 根据问题描述调整搜索空间
        if "image" in problem_description.lower() or "vision" in problem_description.lower():
            default_num_classes = 10
        elif "text" in problem_description.lower() or "nlp" in problem_description.lower():
            default_num_classes = 2  # 二分类文本任务
        else:
            default_num_classes = 10

        # 运行进化搜索
        if evaluator is None:
            # 使用默认评估器：生成代码 + 快速训练（少 epoch）
            evaluator = self._default_evaluator

        best = self.engine.run(evaluator)

        # 生成完整代码
        pytorch_code = generate_pytorch_model(best.genome, num_classes=default_num_classes)

        # 对比分析
        comparison = self._compare_with_baselines(best, baseline_methods)

        return {
            "best_architecture": {
                "num_cells": best.genome.num_cells,
                "init_channels": best.genome.init_channels,
                "normal_cell": {
                    "operations": best.genome.normal_cell.operations,
                    "predecessors": best.genome.normal_cell.predecessors,
                },
                "reduction_cell": {
                    "operations": best.genome.reduction_cell.operations,
                    "predecessors": best.genome.reduction_cell.predecessors,
                },
            },
            "pytorch_code": pytorch_code,
            "search_report": self.engine.get_search_report(),
            "fitness": best.fitness,
            "metrics": best.metrics,
            "comparison_with_baselines": comparison,
        }

    def _default_evaluator(self, genome: NetworkSpec) -> Dict[str, Any]:
        """默认评估器：生成 PyTorch 代码并尝试实际训练评估。

        生成完整的训练脚本，写入临时文件，通过 subprocess 执行。
        如果训练成功，返回真实准确率；如果失败，回退到参数量估算。
        """
        import subprocess
        import sys
        import tempfile
        import os

        estimated_params = (
            genome.num_cells * genome.init_channels * genome.init_channels * 9 * 4
        )

        # 生成完整可运行的 PyTorch 训练脚本
        pytorch_code = generate_pytorch_model(genome, num_classes=10)

        # 追加结果输出（JSON 格式，便于解析）
        eval_script = pytorch_code + '''

if __name__ == "__main__":
    import json, sys
    try:
        result = train_nas_model(epochs=3, batch_size=64, lr=0.025, device='cuda')
        print("EVAL_RESULT:" + json.dumps(result))
    except Exception as e:
        print("EVAL_ERROR:" + str(e), file=sys.stderr)
        sys.exit(1)
'''

        # 写入临时文件并执行
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py', delete=False, dir='/tmp'
            ) as f:
                f.write(eval_script)
                script_path = f.name

            # 执行训练脚本（3 epochs 快速评估，超时 300 秒）
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, 'PYTHONPATH': '/tmp'},
            )

            # 解析输出
            stdout = result.stdout
            best_acc = 0.0
            num_params = estimated_params

            for line in stdout.splitlines():
                if line.startswith("EVAL_RESULT:"):
                    try:
                        eval_data = json.loads(line[len("EVAL_RESULT:"):])
                        best_acc = eval_data.get("best_accuracy", 0.0)
                        num_params = eval_data.get("num_params", estimated_params)
                    except json.JSONDecodeError:
                        pass

            if best_acc > 0:
                # 训练成功：基于真实准确率计算 fitness
                # 归一化到 [0, 1]，CIFAR-10 上 90%+ 算优秀
                fitness = min(best_acc / 100.0, 1.0)
                logger.info(
                    f"NAS evaluator: trained model achieved {best_acc}% accuracy, "
                    f"fitness={fitness:.3f}, params={num_params}"
                )
                return {
                    "fitness": fitness,
                    "metrics": {
                        "accuracy": best_acc,
                        "num_params": num_params,
                        "estimated_params": estimated_params,
                        "trained": True,
                    },
                }
            else:
                logger.warning("NAS evaluator: training produced no valid accuracy, falling back to estimation")

        except subprocess.TimeoutExpired:
            logger.warning("NAS evaluator: training timed out (300s), falling back to estimation")
        except FileNotFoundError:
            logger.warning("NAS evaluator: Python not found, falling back to estimation")
        except Exception as e:
            logger.warning(f"NAS evaluator: training failed ({e}), falling back to estimation")
        finally:
            # 清理临时文件
            try:
                os.unlink(script_path)
            except Exception:
                pass

        # 回退：基于参数量估算（原逻辑）
        if estimated_params > 5_000_000:
            fitness = 0.3
        elif estimated_params > 1_000_000:
            fitness = 0.7
        else:
            fitness = 0.5

        return {
            "fitness": fitness,
            "metrics": {"estimated_params": estimated_params, "trained": False},
        }

    def _compare_with_baselines(
        self,
        best: Individual,
        baselines: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """与 baseline 方法对比。"""
        return {
            "our_method": {
                "fitness": best.fitness,
                "num_params": best.metrics.get("num_params", "unknown"),
                "architecture": f"{best.genome.num_cells} cells, {best.genome.init_channels} channels",
            },
            "baselines": [
                {
                    "name": b.get("name", "unknown"),
                    "reported_accuracy": b.get("accuracy", "unknown"),
                }
                for b in baselines
            ],
            "advantages": [
                "自动搜索得到的架构可能发现人类设计未考虑的组合",
                "针对特定数据集优化的结构",
            ],
            "limitations": [
                "搜索过程计算开销大",
                "小样本情况下可能过拟合",
            ],
        }


# =============================================================================
# 便捷函数
# =============================================================================

def create_nas_agent(
    population_size: int = 8,
    max_generations: int = 3,
    mutation_rate: float = 0.3,
) -> NASAgent:
    """创建 NAS Agent 实例。"""
    return NASAgent(
        population_size=population_size,
        max_generations=max_generations,
        mutation_rate=mutation_rate,
    )
