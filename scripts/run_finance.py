import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import argparse
from pathlib import Path
from src.agent_workflow import UnifiedWorkflow


def discover_problems(root_dir: Path = Path('.')):
    """扫描根目录下所有 *func2* 文件夹，提取金融分析报告素材。"""
    problems = []
    for folder in sorted(root_dir.iterdir()):
        if not folder.is_dir():
            continue
        if 'func2' not in folder.name:
            continue

        md_files = list(folder.glob('*.md'))
        if not md_files:
            print(f'[Skip] {folder.name}: 未找到 .md 描述文件')
            continue

        problem_file = max(md_files, key=lambda p: p.stat().st_size)
        problem_text = problem_file.read_text(encoding='utf-8')

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


def run_problem(problem: dict, use_critique: bool = True):
    folder = problem['folder']
    output_dir = f'work_{folder.name}'

    print(f'\n{"="*60}')
    print(f'[FinanceRun] 处理任务: {folder.name}')
    print(f'[FinanceRun] 描述文件: {problem["problem_file"].name}')
    print(f'[FinanceRun] 数据文件: {list(problem["data_files"].keys())}')
    print(f'[FinanceRun] 输出目录: {output_dir}')
    print(f'{"="*60}\n')

    engine = UnifiedWorkflow(
        output_dir=output_dir,
        template_name='financial_analysis',
        use_critique=use_critique,
    )

    paper = engine.run_full_workflow(
        problem_text=problem['problem_text'],
        data_files=problem['data_files'],
    )

    paper_file = Path(output_dir) / 'final' / 'MathModeling_Paper.md'
    print(f'\n[FinanceRun] 报告已生成: {paper_file}')
    print(f'[FinanceRun] 总字符数: {len(paper)}')
    return paper


def main():
    parser = argparse.ArgumentParser(description='金融分析报告全自动生成')
    parser.add_argument('--root', default='.', help='扫描根目录')
    parser.add_argument('--no-critique', action='store_true', help='关闭 Critique-Improvement')
    parser.add_argument('--provider', default='claude_cli',
                        choices=['claude_cli', 'anthropic', 'openai', 'gemini', 'ollama'],
                        help='默认 LLM Provider')
    args = parser.parse_args()

    os.environ['DEFAULT_LLM_PROVIDER'] = args.provider

    root = Path(args.root)
    problems = discover_problems(root)

    if not problems:
        print('[FinanceRun] 未找到任何 *func2* 文件夹。')
        print('  期望结构: <名称>func2/')
        print('            ├── *.md')
        print('            ├── *.xlsx / *.csv')
        sys.exit(1)

    print(f'[FinanceRun] 发现 {len(problems)} 个任务')
    for p in problems:
        try:
            run_problem(p, use_critique=not args.no_critique)
        except Exception as e:
            print(f'[FinanceRun] {p["folder"].name} 失败: {e}')
            continue

    print('\n[FinanceRun] 全部任务执行完毕。')


if __name__ == '__main__':
    main()
