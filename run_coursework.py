import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import argparse
from pathlib import Path
from src.agent_workflow import UnifiedWorkflow


def discover_problems(root_dir: Path = Path('.')):
    """扫描根目录下所有 *func3* 文件夹，提取课程作业素材。"""
    problems = []
    for folder in sorted(root_dir.iterdir()):
        if not folder.is_dir():
            continue
        if 'func3' not in folder.name:
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
    print(f'[CourseworkRun] 处理作业: {folder.name}')
    print(f'[CourseworkRun] 描述文件: {problem["problem_file"].name}')
    print(f'[CourseworkRun] 数据文件: {list(problem["data_files"].keys())}')
    print(f'[CourseworkRun] 输出目录: {output_dir}')
    print(f'{"="*60}\n')

    engine = UnifiedWorkflow(
        output_dir=output_dir,
        template_name='coursework',
        use_critique=use_critique,
    )

    paper = engine.run_full_workflow(
        problem_text=problem['problem_text'],
        data_files=problem['data_files'],
    )

    paper_file = Path(output_dir) / 'final' / 'MathModeling_Paper.md'
    print(f'\n[CourseworkRun] 论文已生成: {paper_file}')
    print(f'[CourseworkRun] 总字符数: {len(paper)}')
    return paper


def main():
    parser = argparse.ArgumentParser(description='课程作业报告全自动生成')
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
        print('[CourseworkRun] 未找到任何 *func3* 文件夹。')
        print('  期望结构: <名称>func3/')
        print('            ├── *.md')
        print('            ├── *.xlsx / *.csv')
        sys.exit(1)

    print(f'[CourseworkRun] 发现 {len(problems)} 个作业')
    for p in problems:
        try:
            run_problem(p, use_critique=not args.no_critique)
        except Exception as e:
            print(f'[CourseworkRun] {p["folder"].name} 失败: {e}')
            continue

    print('\n[CourseworkRun] 全部任务执行完毕。')


if __name__ == '__main__':
    main()
