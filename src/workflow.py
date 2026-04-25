"""
Step-by-Step Workflow Framework
================================

通用分步骤工作流程框架 - 支持任意数学建模问题

核心设计思想：
1. 问题无关的阶段划分：分析→建模→求解→可视化→论文
2. 各阶段成果保存到文件，后续阶段读取使用（减少上下文依赖）
3. 支持渐进式完成：先完成第一问，再完成第二问...
4. 模块化设计，可扩展

工作流程:
1. 问题分析阶段 - 理解问题，分解任务
2. 数学建模阶段 - 建立模型，设计算法
3. 计算求解阶段 - 编程实现，求解模型
4. 可视化阶段 - 生成图表，展示结果
5. 论文撰写阶段 - 各问题单独写
6. 最终整合阶段 - 拼接完整论文
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import shutil

# 确保src在路径中（从main.py调用时已设置，从独立运行时需要设置）
_current_file = Path(__file__).resolve()
if _current_file.parent.parent not in [Path(p).resolve() for p in sys.path]:
    _project_root = _current_file.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))


class WorkStage(Enum):
    """工作阶段枚举"""
    ANALYSIS = "analysis"        # 问题分析
    MODELING = "modeling"        # 数学建模
    SOLVING = "solving"          # 计算求解
    VISUALIZATION = "visual"     # 可视化
    PAPER_WRITING = "paper"      # 论文撰写
    ASSEMBLY = "assembly"        # 整合


@dataclass
class WorkUnit:
    """工作单元 - 每个问题的独立工作成果"""
    problem_id: str
    problem_name: str
    work_dir: Path

    # 各阶段成果
    analysis_result: Dict[str, Any] = field(default_factory=dict)
    model_result: Dict[str, Any] = field(default_factory=dict)
    solve_result: Dict[str, Any] = field(default_factory=dict)
    visual_result: Dict[str, Any] = field(default_factory=dict)
    paper_section: str = ""

    # 状态跟踪
    completed_stages: List[WorkStage] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    def is_stage_completed(self, stage: WorkStage) -> bool:
        return stage in self.completed_stages

    def mark_completed(self, stage: WorkStage):
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)

    def save_stage_result(self, stage: WorkStage, result: Any, filename: Optional[str] = None):
        """保存阶段成果到文件"""
        self.mark_completed(stage)

        if filename is None:
            filename = f"{stage.value}.json"

        filepath = self.work_dir / stage.value / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(result, (dict, list)):
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        elif isinstance(result, str):
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(result)
        else:
            with open(filepath, 'wb') as f:
                f.write(result)

        # 同时保存到unit对象
        if stage == WorkStage.ANALYSIS:
            self.analysis_result = result if isinstance(result, dict) else {}
        elif stage == WorkStage.MODELING:
            self.model_result = result if isinstance(result, dict) else {}
        elif stage == WorkStage.SOLVING:
            self.solve_result = result if isinstance(result, dict) else {}
        elif stage == WorkStage.VISUALIZATION:
            self.visual_result = result if isinstance(result, dict) else {}

    def load_stage_result(self, stage: WorkStage, filename: Optional[str] = None) -> Any:
        """加载阶段成果"""
        if filename is None:
            filename = f"{stage.value}.json"

        filepath = self.work_dir / stage.value / filename
        if not filepath.exists():
            return None

        if filepath.suffix == '.json':
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()

    def load_previous_results(self) -> Dict[str, Any]:
        """加载前一问题的成果（用于渐进式改进）"""
        return {
            'analysis': self.analysis_result,
            'model': self.model_result,
            'solve': self.solve_result,
            'visual': self.visual_result
        }


class StepByStepFramework:
    """
    通用分步骤工作框架

    核心思想：每个问题分步骤完成，各智能体先完成自己的任务，
    将成果保存到文件夹，后续智能体读取使用，减少上下文依赖

    特点：
    1. 问题无关的阶段设计
    2. 文件系统作为智能体间的通信机制
    3. 支持渐进式完成
    4. 可插拔的智能体实现
    """

    def __init__(self, base_work_dir: str = "work"):
        self.base_work_dir = Path(base_work_dir)
        self.work_units: Dict[str, WorkUnit] = {}
        self.global_context: Dict[str, Any] = {}  # 全局上下文

        # 创建工作目录结构
        self._setup_work_dirs()

    def _setup_work_dirs(self):
        """设置工作目录结构"""
        self.base_work_dir.mkdir(parents=True, exist_ok=True)

        # 创建问题子目录
        for problem_id in ["problem_1", "problem_2", "problem_3"]:
            problem_dir = self.base_work_dir / problem_id
            for stage in [s.value for s in WorkStage]:
                (problem_dir / stage).mkdir(parents=True, exist_ok=True)

        # 创建最终整合目录
        (self.base_work_dir / "final").mkdir(exist_ok=True)

    def register_problem(self, problem_id: str, problem_name: str) -> WorkUnit:
        """注册一个问题"""
        work_dir = self.base_work_dir / problem_id
        unit = WorkUnit(
            problem_id=problem_id,
            problem_name=problem_name,
            work_dir=work_dir
        )
        self.work_units[problem_id] = unit
        return unit

    def get_work_unit(self, problem_id: str) -> Optional[WorkUnit]:
        return self.work_units.get(problem_id)

    def get_all_results(self) -> Dict[str, WorkUnit]:
        """获取所有工作单元的结果"""
        return self.work_units

    def run_problem_workflow(
        self,
        problem_id: str,
        problem_text: str,
        attachments: Optional[List[Any]] = None,
        run_stages: Optional[List[WorkStage]] = None,
        previous_problem_results: Optional[Dict[str, Any]] = None
    ) -> WorkUnit:
        """
        运行单个问题的工作流程

        Args:
            problem_id: 问题ID
            problem_text: 问题描述
            attachments: 附件数据
            run_stages: 指定要运行的阶段，None表示全部运行
            previous_problem_results: 前一问题的成果（用于渐进式改进）

        Returns:
            WorkUnit: 完成的工作单元
        """
        unit = self.work_units.get(problem_id)
        if unit is None:
            raise ValueError(f"Problem {problem_id} not registered")

        if run_stages is None:
            run_stages = [
                WorkStage.ANALYSIS,
                WorkStage.MODELING,
                WorkStage.SOLVING,
                WorkStage.VISUALIZATION,
                WorkStage.PAPER_WRITING
            ]

        if attachments is None:
            attachments = []

        # 按顺序执行各阶段
        for stage in run_stages:
            if unit.is_stage_completed(stage):
                print(f"  [{stage.value}] Already completed, skipping...")
                continue

            print(f"\n  === Stage: {stage.value} ===")
            result = self._run_stage(
                stage, unit, problem_text, attachments,
                previous_problem_results
            )

            # 保存结果
            if result is not None:
                unit.save_stage_result(stage, result)

        return unit

    def _run_stage(
        self,
        stage: WorkStage,
        unit: WorkUnit,
        problem_text: str,
        attachments: List[Any],
        previous_results: Optional[Dict[str, Any]] = None
    ) -> Any:
        """执行单个阶段 - 使用策略模式"""
        if stage == WorkStage.ANALYSIS:
            return self._run_analysis_stage(unit, problem_text)
        elif stage == WorkStage.MODELING:
            return self._run_modeling_stage(unit, problem_text, previous_results)
        elif stage == WorkStage.SOLVING:
            return self._run_solving_stage(unit, attachments)
        elif stage == WorkStage.VISUALIZATION:
            return self._run_visualization_stage(unit, attachments)
        elif stage == WorkStage.PAPER_WRITING:
            return self._run_paper_writing_stage(unit)
        else:
            return None

    def _run_analysis_stage(self, unit: WorkUnit, problem_text: str) -> Dict[str, Any]:
        """问题分析阶段 - 通用的文本分析"""
        # 通用关键词提取
        analysis = {
            "problem_id": unit.problem_id,
            "problem_name": unit.problem_name,
            "problem_type": self._detect_problem_type(problem_text),
            "has_attachments": '附件' in problem_text or 'attachment' in problem_text.lower(),
            "requirements": self._extract_requirements(problem_text),
            "keywords": self._extract_keywords(problem_text),
            "problem_text_length": len(problem_text)
        }

        print(f"    Problem type: {analysis['problem_type']}")
        print(f"    Keywords: {', '.join(analysis['keywords'][:5])}")
        return analysis

    def _detect_problem_type(self, text: str) -> str:
        """检测问题类型"""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ['优化', 'optimal', 'minimize', 'maximize']):
            return "optimization"
        elif any(kw in text_lower for kw in ['预测', 'predict', 'forecast']):
            return "prediction"
        elif any(kw in text_lower for kw in ['分类', 'classif']):
            return "classification"
        elif any(kw in text_lower for kw in ['测量', 'measurement', '厚度', 'thickness']):
            return "measurement"
        elif any(kw in text_lower for kw in ['评价', 'evaluat', 'assess']):
            return "evaluation"
        return "analysis"

    def _extract_requirements(self, text: str) -> List[str]:
        """提取任务要求"""
        requirements = []
        text_lower = text.lower()

        if '论文' in text or 'paper' in text_lower:
            requirements.append("generate_paper")
        if any(kw in text_lower for kw in ['图表', 'figure', 'plot', '可视化']):
            requirements.append("generate_figures")
        if any(kw in text_lower for kw in ['计算', 'calculat', '求解', 'solve']):
            requirements.append("numerical_calculation")
        if any(kw in text_lower for kw in ['分析', 'analys']):
            requirements.append("detailed_analysis")

        return requirements

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 简单实现，实际可用NLP
        keywords = []
        text_lower = text.lower()

        # 技术关键词
        tech_keywords = ['ftir', 'interference', 'spectroscopy', 'infrared', 'semiconductor',
                        'epitaxial', 'thickness', 'measurement', 'laser', 'optical']
        for kw in tech_keywords:
            if kw in text_lower:
                keywords.append(kw)

        # 数学关键词
        math_keywords = ['equation', 'model', 'algorithm', 'optimization', 'regression',
                        'fourier', 'transform', 'interference', 'fringe']
        for kw in math_keywords:
            if kw in text_lower:
                keywords.append(kw)

        return list(set(keywords))

    def _run_modeling_stage(
        self,
        unit: WorkUnit,
        problem_text: str,
        previous_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        数学建模阶段

        可参考前一问题的模型进行渐进式改进
        """
        # 检查是否可以参考前一问题的模型
        prev_model = {}
        if previous_results and 'model' in previous_results:
            prev_model = previous_results['model']
            print(f"    Using previous problem model as reference...")

        # 根据问题类型构建模型
        problem_type = unit.analysis_result.get('problem_type', 'analysis')

        if problem_type == 'measurement':
            model = self._build_measurement_model(prev_model)
        elif problem_type == 'optimization':
            model = self._build_optimization_model(prev_model)
        elif problem_type == 'prediction':
            model = self._build_prediction_model(prev_model)
        else:
            model = self._build_generic_model(prev_model)

        model['problem_type'] = problem_type
        model['based_on_previous'] = bool(prev_model)

        unit.model_result = model
        return model

    def _build_measurement_model(self, base_model: Dict) -> Dict[str, Any]:
        """构建测量类问题的通用模型"""
        model = base_model.copy() if base_model else {}

        # 测量问题的通用元素
        measurement_elements = {
            "variables": [
                {"name": "x", "description": "自变量", "unit": "varies"},
                {"name": "y", "description": "因变量", "unit": "varies"},
                {"name": "d", "description": "测量值", "unit": "varies"}
            ],
            "formulas": [
                "d = f(x; parameters)"
            ],
            "assumptions": [
                "测量误差服从正态分布",
                "仪器精度已知",
                "测量条件稳定"
            ]
        }

        model.update(measurement_elements)
        return model

    def _build_optimization_model(self, base_model: Dict) -> Dict[str, Any]:
        """构建优化类问题的通用模型"""
        model = base_model.copy() if base_model else {}

        optimization_elements = {
            "variables": [
                {"name": "x", "description": "决策变量", "unit": "varies"},
                {"name": "objective", "description": "目标函数", "unit": "varies"},
                {"name": "constraint", "description": "约束条件", "unit": "varies"}
            ],
            "formulas": [
                "min/max f(x)",
                "s.t. g(x) <= 0",
                "h(x) = 0"
            ],
            "assumptions": [
                "目标函数凸性",
                "约束条件可行性",
                "解的存在性"
            ]
        }

        model.update(optimization_elements)
        return model

    def _build_prediction_model(self, base_model: Dict) -> Dict[str, Any]:
        """构建预测类问题的通用模型"""
        model = base_model.copy() if base_model else {}

        prediction_elements = {
            "variables": [
                {"name": "X", "description": "特征变量", "unit": "varies"},
                {"name": "Y", "description": "预测目标", "unit": "varies"},
                {"name": "t", "description": "时间变量", "unit": "varies"}
            ],
            "formulas": [
                "Y = f(X; theta)",
                "Y_t = f(Y_{t-1}, Y_{t-2}, ...)"
            ],
            "assumptions": [
                "数据独立性",
                "分布平稳性",
                "模型可解释性"
            ]
        }

        model.update(prediction_elements)
        return model

    def _build_generic_model(self, base_model: Dict) -> Dict[str, Any]:
        """构建通用模型"""
        model = base_model.copy() if base_model else {}
        model.update({
            "variables": [],
            "formulas": [],
            "assumptions": []
        })
        return model

    def _run_solving_stage(self, unit: WorkUnit, attachments: List[Any]) -> Dict[str, Any]:
        """
        计算求解阶段

        通用的求解框架，实际求解逻辑由具体问题决定
        """
        solve_result = {
            "solver": "GenericSolver",
            "problem_id": unit.problem_id,
            "status": "pending"
        }

        # 检查是否有附件数据
        if attachments:
            solve_result["has_data"] = True
            solve_result["data_count"] = len(attachments)
        else:
            solve_result["has_data"] = False

        # 保存求解代码模板
        self._save_generic_solve_code(unit)

        unit.solve_result = solve_result
        return solve_result

    def _save_generic_solve_code(self, unit: WorkUnit):
        """保存通用的求解代码模板"""
        code = f'''
"""
求解代码 - {unit.problem_name}
问题ID: {unit.problem_id}

请在此模板基础上实现具体求解逻辑
"""

import numpy as np
from typing import Dict, Any, List, Tuple

def solve_{unit.problem_id.replace("-", "_")}(
    problem_text: str,
    attachments: List[Any],
    model: Dict[str, Any]
) -> Dict[str, Any]:
    """
    求解函数

    Args:
        problem_text: 问题描述
        attachments: 附件数据列表
        model: 数学模型

    Returns:
        求解结果字典
    """
    results = {{
        "problem_id": "{unit.problem_id}",
        "status": "success",
        "solution": {{}},
        "metrics": {{}}
    }}

    # TODO: 实现具体求解逻辑

    return results


if __name__ == "__main__":
    # 测试代码
    print("请实现具体求解逻辑")
'''

        code_path = unit.work_dir / "code" / "solve.py"
        code_path.parent.mkdir(parents=True, exist_ok=True)
        with open(code_path, 'w', encoding='utf-8') as f:
            f.write(code)

    def _run_visualization_stage(self, unit: WorkUnit, attachments: List[Any]) -> Dict[str, Any]:
        """可视化阶段"""
        visual_result = {
            "problem_id": unit.problem_id,
            "charts": [],
            "status": "pending"
        }

        # 保存可视化代码模板
        self._save_generic_visualization_code(unit)

        unit.visual_result = visual_result
        return visual_result

    def _save_generic_visualization_code(self, unit: WorkUnit):
        """保存通用的可视化代码模板"""
        code = f'''
"""
可视化代码 - {unit.problem_name}
问题ID: {unit.problem_id}

请在此模板基础上实现具体可视化逻辑
"""

import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, Any, List

def visualize_{unit.problem_id.replace("-", "_")}(
    results: Dict[str, Any],
    output_dir: str = "."
) -> List[str]:
    """
    生成可视化图表

    Args:
        results: 求解结果
        output_dir: 输出目录

    Returns:
        生成的图表文件路径列表
    """
    output_paths = []

    # TODO: 实现具体可视化逻辑

    return output_paths


if __name__ == "__main__":
    print("请实现具体可视化逻辑")
'''

        code_path = unit.work_dir / "visual" / "visualize.py"
        code_path.parent.mkdir(parents=True, exist_ok=True)
        with open(code_path, 'w', encoding='utf-8') as f:
            f.write(code)

    def _run_paper_writing_stage(self, unit: WorkUnit) -> str:
        """论文撰写阶段 - 通用模板"""
        from paper.generic_section import write_generic_section

        paper_text = write_generic_section(unit)

        # 保存论文部分
        section_path = unit.work_dir / "paper" / "section.md"
        with open(section_path, 'w', encoding='utf-8') as f:
            f.write(paper_text)

        unit.paper_section = paper_text
        return paper_text

    def assemble_final_paper(
        self,
        output_path: str = "work/final/Final_Paper.md",
        title: str = "数学建模论文",
        authors: str = "数学建模团队"
    ) -> str:
        """整合所有问题的论文部分为完整论文"""
        from paper.generic_merger import merge_generic_sections

        final_path = Path(output_path)
        final_path.parent.mkdir(parents=True, exist_ok=True)

        merged_paper = merge_generic_sections(
            self.work_units,
            title=title,
            authors=authors
        )

        with open(final_path, 'w', encoding='utf-8') as f:
            f.write(merged_paper)

        print(f"\n  Final paper saved to: {final_path}")
        return merged_paper


# 便捷函数
def create_workflow(base_dir: str = "work") -> StepByStepFramework:
    """创建分步骤工作流程"""
    return StepByStepFramework(base_dir)
