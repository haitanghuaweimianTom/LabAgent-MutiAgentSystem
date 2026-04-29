"""
Coordinator - 中央调度器
=========================

借鉴 LLM-MM-Agent 的 Coordinator 设计：
- DAG 依赖分析与拓扑排序
- 黑板内存（memory / code_memory）
- 依赖上下文自动拼接
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class DependencyType(str, Enum):
    """任务依赖类型"""
    DATA = "data"              # 数据依赖：需要前置任务的结果数据
    METHODOLOGICAL = "method"  # 方法依赖：需要前置任务的建模方法
    COMPUTATIONAL = "compute"  # 计算依赖：需要前置任务的代码/计算结果
    STRUCTURAL = "struct"      # 结构依赖：逻辑上需要先完成
    CODE = "code"              # 代码依赖：需要前置任务生成的代码文件


@dataclass
class TaskNode:
    """任务节点"""
    task_id: str
    description: str
    dependencies: Dict[str, List[DependencyType]] = field(default_factory=dict)
    # dependencies: {task_id: [dep_type, ...]}
    status: str = "pending"    # pending / running / completed / failed
    result: Any = None
    code_artifacts: Dict[str, Any] = field(default_factory=dict)


class Coordinator:
    """
    中央调度器

    职责：
    1. 维护任务 DAG 并计算拓扑排序
    2. 管理跨任务共享的 memory（结果黑板）
    3. 管理 code_memory（代码结构黑板）
    4. 自动拼接依赖上下文到 prompt
    """

    def __init__(self):
        self.tasks: Dict[str, TaskNode] = {}
        self.memory: Dict[str, Dict[str, Any]] = {}
        self.code_memory: Dict[str, Dict[str, Any]] = {}
        self.dag_order: List[str] = []

    def register_task(
        self,
        task_id: str,
        description: str,
        dependencies: Optional[Dict[str, List[DependencyType]]] = None,
    ) -> TaskNode:
        """注册任务节点"""
        node = TaskNode(
            task_id=task_id,
            description=description,
            dependencies=dependencies or {},
        )
        self.tasks[task_id] = node
        self.memory[task_id] = {}
        self.code_memory[task_id] = {}
        return node

    def analyze_dependencies(self) -> List[str]:
        """
        构建 DAG 并计算拓扑排序（Kahn算法）

        Returns:
            List[str]: 拓扑排序后的任务 ID 列表
        """
        # 计算入度
        in_degree = {tid: 0 for tid in self.tasks}
        adjacency = {tid: [] for tid in self.tasks}

        for tid, node in self.tasks.items():
            for dep_tid in node.dependencies:
                if dep_tid in self.tasks:
                    adjacency[dep_tid].append(tid)
                    in_degree[tid] += 1
                else:
                    print(f"[Coordinator] 警告: 任务 {tid} 依赖不存在的任务 {dep_tid}")

        # Kahn算法
        queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        order = []

        while queue:
            current = queue.popleft()
            order.append(current)
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.tasks):
            # 存在环，按注册顺序回退
            print("[Coordinator] 警告: DAG 存在环，使用注册顺序")
            order = list(self.tasks.keys())

        self.dag_order = order
        print(f"[Coordinator] DAG 拓扑序: {' -> '.join(order)}")
        return order

    def get_dependency_context(
        self,
        task_id: str,
        include_types: Optional[List[DependencyType]] = None,
        max_chars: int = 4000,
    ) -> str:
        """
        获取当前任务的依赖上下文，自动拼接前置任务结果

        Args:
            task_id: 当前任务ID
            include_types: 仅包含指定类型的依赖（None=全部）
            max_chars: 上下文最大字符数

        Returns:
            str: 拼接后的依赖上下文
        """
        node = self.tasks.get(task_id)
        if not node or not node.dependencies:
            return ""

        parts = []
        total_chars = 0

        for dep_tid, dep_types in node.dependencies.items():
            if dep_tid not in self.tasks:
                continue

            # 过滤依赖类型
            if include_types:
                dep_types = [t for t in dep_types if t in include_types]
                if not dep_types:
                    continue

            dep_node = self.tasks[dep_tid]
            dep_mem = self.memory.get(dep_tid, {})

            part = f"【前置任务 {dep_tid} 输出】\n"
            part += f"描述: {dep_node.description}\n"

            # 根据依赖类型选择性拼接
            if DependencyType.DATA in dep_types and "data" in dep_mem:
                part += f"数据结果: {json.dumps(dep_mem['data'], ensure_ascii=False, indent=2)[:800]}\n"
            if DependencyType.METHODOLOGICAL in dep_types and "formulas" in dep_mem:
                part += f"建模公式: {dep_mem['formulas'][:1000]}\n"
            if DependencyType.COMPUTATIONAL in dep_types and "execution_result" in dep_mem:
                part += f"计算结果: {json.dumps(dep_mem['execution_result'], ensure_ascii=False, indent=2)[:800]}\n"
            if DependencyType.CODE in dep_types and dep_tid in self.code_memory:
                code_info = self.code_memory[dep_tid]
                part += f"代码文件: {code_info.get('script_path', 'N/A')}\n"
                part += f"输出文件: {code_info.get('file_outputs', [])}\n"
            if DependencyType.STRUCTURAL in dep_types and "analysis" in dep_mem:
                part += f"分析结果: {dep_mem['analysis'][:1000]}\n"

            # 通用回退：如果有 result 字段
            if dep_node.result and len(part) < 200:
                part += f"结果摘要: {str(dep_node.result)[:1000]}\n"

            part += "\n"

            if total_chars + len(part) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 100:
                    parts.append(part[:remaining])
                break

            parts.append(part)
            total_chars += len(part)

        return "\n".join(parts)

    def save_task_result(
        self,
        task_id: str,
        result: Any,
        key: str = "result",
    ):
        """保存任务结果到黑板内存"""
        if task_id not in self.memory:
            self.memory[task_id] = {}
        self.memory[task_id][key] = result
        if task_id in self.tasks:
            self.tasks[task_id].result = result
            self.tasks[task_id].status = "completed"

    def save_code_result(
        self,
        task_id: str,
        script_path: str,
        file_outputs: List[str],
        code_structure: Optional[Dict] = None,
    ):
        """保存代码执行结果到 code_memory"""
        self.code_memory[task_id] = {
            "script_path": script_path,
            "file_outputs": file_outputs,
            "structure": code_structure or {},
        }

    def get_all_results(self) -> Dict[str, Any]:
        """获取所有任务的聚合结果"""
        return {
            tid: {
                "description": node.description,
                "status": node.status,
                "memory": self.memory.get(tid, {}),
                "code": self.code_memory.get(tid, {}),
            }
            for tid, node in self.tasks.items()
        }

    def export_solution(self, output_path: Path):
        """导出完整解决方案到JSON"""
        solution = self.get_all_results()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(solution, f, ensure_ascii=False, indent=2)
        print(f"[Coordinator] 解决方案已导出: {output_path}")
