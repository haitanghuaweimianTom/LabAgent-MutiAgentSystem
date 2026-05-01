#!/usr/bin/env python3
"""
数学建模论文自动生成系统 v2.0
==============================

通用入口点，支持全自动生成完整论文
融合 LLM-MM-Agent + cherry-studio + Claude CLI 架构

支持的论文模板:
- math_modeling: 数学建模竞赛论文（MCM/ICM标准格式）
- coursework: 一般课程作业论文
- financial_analysis: 金融数据分析与投资报告

使用方法:
    python main.py --auto                              # 全自动生成（默认数学建模）
    python main.py --auto --template coursework        # 生成课程作业论文
    python main.py --auto --template financial_analysis # 生成金融分析报告
    python main.py --auto --output-dir work_test       # 指定输出目录
"""

import sys
import os
import argparse
from pathlib import Path

# 禁用输出缓冲，确保日志实时可见
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def main():
    parser = argparse.ArgumentParser(
        description='数学建模论文自动生成系统 v2.0'
    )
    parser.add_argument('--auto', action='store_true',
                       help='全自动生成论文（推荐）')
    parser.add_argument('--template', type=str, default='math_modeling',
                       choices=['math_modeling', 'coursework', 'financial_analysis'],
                       help='论文模板类型（默认: math_modeling）')
    parser.add_argument('--output-dir', type=str, default='work',
                       help='输出目录')
    parser.add_argument('--no-critique', action='store_true',
                       help='禁用 Critique-Improvement（加速模式）')

    args = parser.parse_args()

    print("\n" + "="*70)
    print("数学建模论文自动生成系统 v2.0")
    print("="*70)

    if args.auto:
        run_auto_generation(args.output_dir, args.template, not args.no_critique)
    else:
        print("\n使用方法:")
        print("  python main.py --auto                              # 全自动生成数学建模论文")
        print("  python main.py --auto --template coursework        # 生成课程作业论文")
        print("  python main.py --auto --template financial_analysis # 生成金融分析报告")
        print("\n推荐使用 --auto 模式，系统将自动完成所有工作")


def run_auto_generation(output_dir: str = 'work', template_name: str = 'math_modeling', use_critique: bool = True):
    """全自动论文生成"""
    from src.agent_workflow import UnifiedWorkflow
    from src.workflow import list_templates

    print("\n" + "="*70)
    print(f"模板: {template_name}")
    print(f"可用模板: {list_templates()}")
    print(f"Critique-Improvement: {'启用' if use_critique else '禁用'}")
    print("="*70)

    # 检测数据文件
    data_files = detect_data_files()
    if data_files:
        print(f"\n检测到 {len(data_files)} 个数据文件:")
        for name, path in data_files.items():
            print(f"  - {name}: {path}")
    else:
        print("\n未检测到数据文件")

    # 检测赛题文件
    problem_file = detect_problem_file()
    if problem_file:
        print(f"赛题文件: {problem_file}")
        with open(problem_file, 'r', encoding='utf-8') as f:
            preview = f.read()[:200]
        print(f"赛题预览: {preview}...")
    else:
        print("未检测到赛题文件，将使用默认描述")
        problem_file = "problem.md"

    # 读取问题文本
    problem_text = ""
    if Path(problem_file).exists():
        with open(problem_file, 'r', encoding='utf-8') as f:
            problem_text = f.read()

    # 运行自动生成
    print("\n" + "-"*50)
    print("开始自动生成论文...")
    print("-"*50)

    engine = UnifiedWorkflow(
        output_dir=output_dir,
        template_name=template_name,
        use_critique=use_critique,
    )

    paper = engine.run_full_workflow(
        problem_text=problem_text,
        data_files=data_files,
    )

    # 输出结果
    paper_file = Path(output_dir) / "final" / "MathModeling_Paper.md"

    print("\n" + "="*70)
    print("论文生成完成")
    print("="*70)
    print(f"\n论文文件: {paper_file}")
    print(f"总字符数: {len(paper)}")
    print(f"中文字数: {len(__import__('re').findall(r'[一-鿿]', paper))}")

    return paper


def detect_data_files() -> dict:
    """检测数据文件 - 自动识别所有xlsx文件"""
    data_files = {}
    for filepath in Path('.').glob('*.xlsx'):
        filename = filepath.name
        if filename.lower() not in ['config.xlsx', 'settings.xlsx']:
            display_name = filename.replace('.xlsx', '')
            data_files[display_name] = filename
    return data_files


def detect_problem_file() -> str:
    """检测赛题文件"""
    for filepath in Path('.').glob('*.md'):
        filename = filepath.name.lower()
        if 'problem' in filename or '题目' in filename or '赛题' in filename:
            return filepath.name
    return ""


if __name__ == '__main__':
    main()
