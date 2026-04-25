#!/usr/bin/env python3
"""
数学建模论文自动生成系统
========================

通用入口点，支持全自动生成15000-25000字的完整数学建模论文

使用方法:
    python main.py --auto                    # 全自动生成论文
    python main.py --stepwise                # 分步骤工作流程（调试用）
"""

import sys
import os
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description='数学建模论文自动生成系统'
    )
    parser.add_argument('--auto', action='store_true',
                       help='全自动生成论文（推荐）')
    parser.add_argument('--stepwise', action='store_true',
                       help='分步骤工作流程（调试用）')
    parser.add_argument('--output-dir', type=str, default='work',
                       help='输出目录')

    args = parser.parse_args()

    print("\n" + "="*70)
    print("数学建模论文自动生成系统")
    print("="*70)

    if args.auto:
        run_auto_generation(args.output_dir)
    elif args.stepwise:
        run_stepwise_workflow(args.output_dir)
    else:
        print("\n使用方法:")
        print("  python main.py --auto                    # 全自动生成论文（推荐）")
        print("  python main.py --stepwise                # 分步骤工作流程")
        print("\n推荐使用 --auto 模式，系统将自动完成所有工作")


def run_auto_generation(output_dir: str = 'work'):
    """
    全自动论文生成

    使用Agent工作流自动完成：
    1. 问题分析
    2. 数学建模
    3. 算法设计
    4. 代码编写
    5. 代码执行
    6. 结果分析
    7. 图表设计
    8. 论文撰写

    生成15000-25000字的完整论文
    """
    from agent_workflow import run_auto_paper_generation

    print("\n" + "="*70)
    print("全自动论文生成模式")
    print("="*70)

    # 检测数据文件
    data_files = detect_data_files()
    if data_files:
        print(f"\n检测到 {len(data_files)} 个数据文件")
    else:
        print("\n未检测到数据文件，将使用模拟数据")

    # 检测赛题文件
    problem_file = detect_problem_file()
    if problem_file:
        print(f"使用赛题文件: {problem_file}")
    else:
        print("未检测到赛题文件，将使用默认问题描述")

    # 运行自动生成
    print("\n" + "-"*50)
    print("开始自动生成论文...")
    print("-"*50)

    paper = run_auto_paper_generation(
        problem_file=problem_file if problem_file else "problem.md",
        data_files=data_files,
        output_dir=output_dir
    )

    # 输出结果
    paper_file = Path(output_dir) / "final" / "MathModeling_Paper.md"

    print("\n" + "="*70)
    print("论文生成完成")
    print("="*70)
    print(f"\n论文文件: {paper_file}")
    print(f"论文字数: 约 {len(paper)} 字")
    print(f"页数估算: 约 {len(paper)//800 + 1} 页（正文字数/800 + 摘要等）")


def run_stepwise_workflow(output_dir: str = 'work'):
    """分步骤工作流程（用于调试）"""
    from workflow import StepByStepFramework, WorkStage

    print("\n" + "="*70)
    print("分步骤工作流程（调试模式）")
    print("="*70)

    framework = StepByStepFramework(base_work_dir=output_dir)

    # 注册问题
    for i in range(1, 4):
        framework.register_problem(f"problem_{i}", f"问题{i}")

    # 检测数据
    attachment_data = _load_data_files()

    # 读取问题
    problem_text = _load_problem_text()

    # 依次完成各问题
    previous_results = None
    for problem_id in [f"problem_{i}" for i in range(1, 4)]:
        print(f"\n{'='*60}")
        print(f"Processing: {problem_id}")
        print(f"{'='*60}")

        unit = framework.work_units[problem_id]

        for stage in [WorkStage.ANALYSIS, WorkStage.MODELING,
                      WorkStage.SOLVING, WorkStage.VISUALIZATION, WorkStage.PAPER_WRITING]:
            result = framework._run_stage(stage, unit, problem_text,
                                         attachment_data, previous_results)
            if result is not None:
                unit.save_stage_result(stage, result)

        previous_results = unit.load_previous_results()

    # 整合论文
    framework.assemble_final_paper(f"{output_dir}/final/MathModeling_Paper.md")

    print("\n" + "="*70)
    print("完成")
    print("="*70)


def detect_data_files() -> dict:
    """检测数据文件"""
    data_files = {}

    candidates = [
        ('附件1.xlsx', '附件1'),
        ('附件2.xlsx', '附件2'),
        ('附件3.xlsx', '附件3'),
        ('附件4.xlsx', '附件4'),
        ('attachment1.xlsx', '附件1'),
        ('attachment2.xlsx', '附件2'),
    ]

    for filename, display_name in candidates:
        if Path(filename).exists():
            data_files[display_name] = filename

    return data_files


def detect_problem_file() -> str:
    """检测赛题文件"""
    candidates = [
        '2025B-Problem.md',
        'problem.md',
        '题目.md',
        '赛题.md'
    ]

    for filename in candidates:
        if Path(filename).exists():
            return filename

    return ""


def _load_data_files() -> list:
    """加载数据文件"""
    from data import SpectrumLoader

    attachment_data = []
    data_files = [
        '附件1.xlsx', '附件2.xlsx', '附件3.xlsx', '附件4.xlsx',
        'attachment1.xlsx', 'attachment2.xlsx', 'attachment3.xlsx', 'attachment4.xlsx'
    ]

    for filename in data_files:
        if Path(filename).exists():
            try:
                data = SpectrumLoader.load_from_excel(filename, filename.replace('.xlsx', ''))
                attachment_data.append(data)
            except:
                attachment_data.append(None)
        else:
            if '附件' in filename:
                pass  # 不显示中文附件的not found
            else:
                pass

    return attachment_data


def _load_problem_text() -> str:
    """加载问题文本"""
    candidates = ['2025B-Problem.md', 'problem.md', '题目.md']

    for filename in candidates:
        if Path(filename).exists():
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                pass

    return ""


if __name__ == '__main__':
    main()
