import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import re
import argparse
from pathlib import Path
from src.agent_workflow import UnifiedWorkflow


def discover_problems(root_dir: Path = Path('.')):
    """扫描根目录下所有 *USETHIS* 文件夹，提取赛题和数据文件。"""
    problems = []
    for folder in sorted(root_dir.iterdir()):
        if not folder.is_dir():
            continue
        if 'USETHIS' not in folder.name:
            continue

        md_files = list(folder.glob('*.md'))
        if not md_files:
            print(f'[Skip] {folder.name}: 未找到 .md 赛题文件')
            continue

        # 选择最大的 md 文件作为赛题（通常赛题最长）
        problem_file = max(md_files, key=lambda p: p.stat().st_size)
        problem_text = problem_file.read_text(encoding='utf-8')

        # 收集数据文件
        data_files = {}
        for ext in ('*.xlsx', '*.xls', '*.csv'):
            for fp in folder.glob(ext):
                key = fp.stem
                data_files[key] = str(fp)

        problems.append({
            'folder': folder,
            'problem_file': problem_file,
            'problem_text': problem_text,
            'data_files': data_files,
        })

    return problems


def run_problem(problem: dict, template_name: str = 'math_modeling', use_critique: bool = True):
    """对单个赛题运行完整工作流。"""
    folder = problem['folder']
    output_dir = f'work_{folder.name}'

    print(f'\n{"="*60}')
    print(f'[AutoRun] 处理赛题: {folder.name}')
    print(f'[AutoRun] 赛题文件: {problem["problem_file"].name}')
    print(f'[AutoRun] 数据文件: {list(problem["data_files"].keys())}')
    print(f'[AutoRun] 输出目录: {output_dir}')
    print(f'{"="*60}\n')

    engine = UnifiedWorkflow(
        output_dir=output_dir,
        template_name=template_name,
        use_critique=use_critique,
    )

    paper = engine.run_full_workflow(
        problem_text=problem['problem_text'],
        data_files=problem['data_files'],
    )

    paper_file = Path(output_dir) / 'final' / 'MathModeling_Paper.md'
    print(f'\n[AutoRun] 论文已生成: {paper_file}')
    print(f'[AutoRun] 总字符数: {len(paper)}')
    return paper


def main():
    parser = argparse.ArgumentParser(description='全自动数学建模论文生成')
    parser.add_argument('--root', default='.', help='扫描根目录 (默认: 当前目录)')
    parser.add_argument('--template', default='math_modeling',
                       choices=['math_modeling', 'coursework', 'financial_analysis',
                                'neurips_2024', 'ieee_conference', 'acm_sigconf',
                                'springer_lncs', 'research_survey'],
                       help='论文模板名称（可选: math_modeling, coursework, financial_analysis, neurips_2024, ieee_conference, acm_sigconf, springer_lncs, research_survey）')
    parser.add_argument('--no-critique', action='store_true', help='关闭 Critique-Improvement 循环')
    parser.add_argument('--provider', default='claude_cli',
                        choices=['claude_cli', 'anthropic', 'openai', 'gemini', 'ollama'],
                        help='默认 LLM Provider (默认: claude_cli)')
    args = parser.parse_args()

    # 设置默认 Provider
    if args.provider == 'claude_cli':
        os.environ['DEFAULT_LLM_PROVIDER'] = 'claude_cli'
    else:
        os.environ['DEFAULT_LLM_PROVIDER'] = args.provider

    root = Path(args.root)
    problems = discover_problems(root)

    if not problems:
        print('[AutoRun] 未找到任何 *USETHIS* 赛题文件夹，请确认目录结构。')
        print('  期望结构: <年份><题目>-USETHIS/')
        print('            ├── *.md      (赛题描述)')
        print('            ├── *.xlsx    (数据文件)')
        print('            └── *.csv     (数据文件)')
        sys.exit(1)

    print(f'[AutoRun] 发现 {len(problems)} 个赛题任务')

    for p in problems:
        try:
            run_problem(p, template_name=args.template, use_critique=not args.no_critique)
        except Exception as e:
            print(f'[AutoRun] {p["folder"].name} 处理失败: {e}')
            continue

    print('\n[AutoRun] 全部任务执行完毕。')


if __name__ == '__main__':
    main()
