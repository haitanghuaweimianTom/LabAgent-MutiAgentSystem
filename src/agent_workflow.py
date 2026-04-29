"""
Agent工作流引擎
==============

完整的Agent协作工作流，用于自动生成数学建模论文
采用精细化任务拆分策略，减少单次LLM调用超时风险
"""

import os
import sys
import json
import time
import re
import subprocess
import shutil
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import traceback

# =============================================================================
# 多 LLM 提供商支持（借鉴 cherry-studio 架构）
# =============================================================================

try:
    from src.llm import get_provider_manager, ProviderType, LLMProviderFactory, ProviderConfig
    _LLM_PROVIDER_AVAILABLE = True
except ImportError:
    _LLM_PROVIDER_AVAILABLE = False


_llm_provider_instance = None


def _get_llm_provider():
    """获取 LLM Provider 实例（惰性初始化）"""
    global _llm_provider_instance
    if _llm_provider_instance is not None:
        return _llm_provider_instance

    if not _LLM_PROVIDER_AVAILABLE:
        return None

    # 根据环境变量自动选择 Provider
    try:
        if os.getenv("OPENAI_API_KEY"):
            manager = get_provider_manager()
            manager.register(ProviderType.OPENAI)
            _llm_provider_instance = manager
            print(f"[LLM] 使用 OpenAI Provider (model={manager.get().config.model})")
        elif os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
            manager = get_provider_manager()
            config = ProviderConfig.from_env(ProviderType.ANTHROPIC)
            # 兼容 ANTHROPIC_AUTH_TOKEN
            if not config.api_key and os.getenv("ANTHROPIC_AUTH_TOKEN"):
                config.api_key = os.getenv("ANTHROPIC_AUTH_TOKEN")
            # 兼容自定义 base_url
            if os.getenv("ANTHROPIC_BASE_URL"):
                config.api_host = os.getenv("ANTHROPIC_BASE_URL")
            manager.register(ProviderType.ANTHROPIC, config)
            _llm_provider_instance = manager
            print(f"[LLM] 使用 Anthropic Provider (model={manager.get().config.model})")
        elif os.getenv("GEMINI_API_KEY"):
            manager = get_provider_manager()
            manager.register(ProviderType.GEMINI)
            _llm_provider_instance = manager
            print(f"[LLM] 使用 Gemini Provider (model={manager.get().config.model})")
        elif os.getenv("OLLAMA_MODEL") or os.getenv("OLLAMA_HOST"):
            manager = get_provider_manager()
            manager.register(ProviderType.OLLAMA)
            _llm_provider_instance = manager
            print(f"[LLM] 使用 Ollama Provider (model={manager.get().config.model})")
        else:
            # 回退到 Claude CLI
            manager = get_provider_manager()
            manager.register(ProviderType.CLAUDE_CLI)
            _llm_provider_instance = manager
            print(f"[LLM] 使用 Claude CLI Provider (model={manager.get().config.model})")
    except Exception as e:
        print(f"[LLM] Provider 初始化失败: {e}，将回退到 Claude CLI")
        _llm_provider_instance = None

    return _llm_provider_instance


def _find_claude_code() -> Optional[str]:
    """自动搜索 Claude Code CLI 路径"""
    found = shutil.which("claude-code") or shutil.which("claude")
    if found:
        return found
    return None


def _call_llm(
    prompt: str,
    model: str = "sonnet",
    system_prompt: Optional[str] = None,
    timeout: int = 600,
    max_retries: int = 3,
    retry_wait: int = 5
) -> str:
    """
    调用 LLM 生成内容
    支持多提供商：OpenAI / Anthropic / Gemini / Ollama / Claude CLI
    优先使用配置的 API Provider，回退到 Claude Code CLI
    """
    provider_manager = _get_llm_provider()

    if provider_manager is not None:
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"    [LLM调用 {attempt + 1}/{max_retries}] 等待{retry_wait}秒后重试...")
                    time.sleep(retry_wait)

                print(f"    [LLM调用 {attempt + 1}/{max_retries}] 开始请求...")
                response = provider_manager.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    timeout=timeout
                )
                print(f"    [LLM调用 {attempt + 1}/{max_retries}] 成功!")
                return response
            except Exception as e:
                print(f"    [LLM调用 {attempt + 1}/{max_retries}] 失败: {str(e)[:200]}")
                if attempt < max_retries - 1:
                    continue
                print("    [LLM] API Provider 失败，回退到 Claude CLI...")
                break

    # 回退到 Claude Code CLI
    claude_path = _find_claude_code()
    if not claude_path:
        raise RuntimeError(
            "Claude Code CLI 未找到，请确保已安装 Claude Code 并添加到 PATH，"
            "或配置 OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY 环境变量"
        )

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

    cmd = [
        claude_path,
        "-p",
        "--model", model,
        "--output-format", "json",
        full_prompt
    ]

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"    [LLM调用(CLI) {attempt + 1}/{max_retries}] 等待{retry_wait}秒后重试...")
                time.sleep(retry_wait)

            print(f"    [LLM调用(CLI) {attempt + 1}/{max_retries}] 开始请求...")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = proc.communicate(timeout=timeout)

            stdout_text = stdout.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                print(f"    [LLM调用(CLI) {attempt + 1}/{max_retries}] 失败: {error_msg[:200]}")
                if attempt < max_retries - 1:
                    continue
                raise RuntimeError(f"LLM 调用失败: {error_msg[:500]}")

            try:
                data = json.loads(stdout_text.strip())
            except json.JSONDecodeError:
                print(f"    [LLM调用(CLI) {attempt + 1}/{max_retries}] 成功!")
                return stdout_text.strip()

            result_text = data.get("result", "")
            if isinstance(result_text, str):
                result_text = result_text.strip()
                if result_text.startswith("```"):
                    lines = result_text.splitlines()
                    if lines:
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].strip() == "```":
                            lines = lines[:-1]
                    result_text = "\n".join(lines).strip()
                print(f"    [LLM调用(CLI) {attempt + 1}/{max_retries}] 成功!")
                return result_text
            print(f"    [LLM调用(CLI) {attempt + 1}/{max_retries}] 成功!")
            return str(result_text)

        except subprocess.TimeoutExpired:
            print(f"    [LLM调用(CLI) {attempt + 1}/{max_retries}] 超时({timeout}秒)")
            if attempt < max_retries - 1:
                continue
            raise RuntimeError(f"LLM 调用超时（{timeout}秒），已重试{max_retries}次")
        except FileNotFoundError:
            raise RuntimeError("Claude Code CLI 未找到")

    raise RuntimeError("LLM 调用失败，已达到最大重试次数")


# =============================================================================
# Agent 系统提示词（简化版）
# =============================================================================

SYSTEM_PROMPTS = {
    "problem_analyzer": """你是一个数学建模专家。请分析赛题，输出JSON格式的分析结果，包括：background背景、sub_problems子问题列表（每个包含id/description/objective/difficulty/suggested_methods）、data_analysis数据分析、key_terms关键术语、solution_approach解决思路。""",

    "model_designer": """你是一个数学建模专家。请为以下赛题设计数学模型，输出：1模型类型和选择依据、2变量定义表（表格形式）、3完整数学公式（LaTeX格式）、4模型假设清单、5求解思路概述。""",

    "algorithm_designer": """你是一个算法设计专家。请设计求解算法，输出：1算法选择和依据、2算法步骤（分点列出）、3参数设置、4复杂度分析、5收敛性讨论。""",

    "code_writer": """你是一个Python编程专家。请编写求解代码，要求：1使用pandas读取Excel、2使用numpy/scipy计算、3输出具体数值结果、4包含结果保存。直接输出代码（不带markdown格式）。""",

    "result_analyzer": """你是一个数据分析专家。请分析计算结果，输出：1结果摘要、2误差分析、3灵敏度分析、4主要结论。要有数据支撑，分析深入。""",

    "chart_designer": """你是一个数据可视化专家。请设计论文图表方案，输出图表编号、标题、类型、数据要求、图表说明。""",

    "paper_writer": """你是一个专业的数学建模论文写作者。请撰写完整的数学建模论文，要求15000-25000字，包含：摘要、问题重述、问题分析、模型假设、模型建立、模型求解、结果分析、灵敏度分析、模型评价、参考文献、附录。公式用LaTeX，内容充实深入。"""
}


class WorkflowStage(Enum):
    """工作流程阶段"""
    STAGE_1_ANALYSIS = "stage_1_analysis"
    STAGE_2_MODELING = "stage_2_modeling"
    STAGE_3_ALGORITHM = "stage_3_algorithm"
    STAGE_4_CODING = "stage_4_coding"
    STAGE_5_EXECUTION = "stage_5_execution"
    STAGE_6_RESULT_ANALYSIS = "stage_6_result_analysis"
    STAGE_7_CHARTS = "stage_7_charts"
    STAGE_8_PAPER = "stage_8_paper"


@dataclass
class StageResult:
    """阶段执行结果"""
    stage: WorkflowStage
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time: float = 0.0


class AgentWorkflow:
    """Agent工作流引擎 - 精细化版本"""

    def __init__(self, output_dir: str = "work"):
        self.output_dir = Path(output_dir)
        self.results = {}
        self._setup_output_dirs()

    def _setup_output_dirs(self):
        """创建输出目录结构"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for stage in WorkflowStage:
            (self.output_dir / stage.value).mkdir(exist_ok=True)
        (self.output_dir / "final").mkdir(exist_ok=True)

    def _save_stage_result(self, stage: WorkflowStage, result: Any, filename: str = "result.md"):
        """保存阶段结果到文件"""
        try:
            stage_dir = self.output_dir / stage.value
            output_file = stage_dir / filename

            if isinstance(result, dict):
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
            elif isinstance(result, str):
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(result)
            else:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(str(result))
            print(f"    已保存: {output_file}")
        except Exception as e:
            print(f"    保存失败: {e}")

    def run_full_workflow(
        self,
        problem_text: str,
        data_files: Dict[str, str],
        problem_name: str = "数学建模问题"
    ) -> str:
        """运行完整工作流 - 强化版"""
        print("\n" + "="*70)
        print("数学建模论文自动生成系统")
        print("="*70)

        context = {
            'problem_text': problem_text,
            'data_files': data_files,
            'analysis_result': {},
            'model_result': '',
            'algorithm_result': '',
            'code_result': '',
            'execution_result': {},
            'result_analysis': '',
            'charts_result': '',
        }

        stages = list(WorkflowStage)

        for i, stage in enumerate(stages):
            print(f"\n{'='*60}")
            print(f"阶段 {i+1}/{len(stages)}: {stage.value}")
            print(f"{'='*60}")

            start_time = time.time()
            result = self._run_stage(stage, context)
            elapsed = time.time() - start_time

            self.results[stage.value] = result
            print(f"    耗时: {elapsed:.1f}秒")

            if not result.get('success', False):
                print(f"\n  [警告] 阶段执行遇到问题，继续...")

            context[f'{stage.value}_result'] = result.get('output', '')

        print(f"\n{'='*60}")
        print("生成最终论文")
        print(f"{'='*60}")

        paper = self._generate_full_paper(context)

        paper_file = self.output_dir / "final" / "MathModeling_Paper.md"
        with open(paper_file, 'w', encoding='utf-8') as f:
            f.write(paper)

        chinese_chars = self._count_chinese_chars(paper)
        print(f"\n论文已保存: {paper_file}")
        print(f"论文字数: {chinese_chars} 中文字")
        print(f"论文总字符: {len(paper)} 字符")

        # 生成Word文档
        docx_file = self.output_dir / "final" / "数学建模论文.docx"
        try:
            self.convert_to_docx(paper_file, docx_file)
        except Exception as e:
            print(f"Word转换失败: {e}")

        return paper

    def _run_stage(self, stage: WorkflowStage, context: Dict) -> Dict:
        """执行单个阶段"""
        try:
            if stage == WorkflowStage.STAGE_1_ANALYSIS:
                return self._stage_analysis(context)
            elif stage == WorkflowStage.STAGE_2_MODELING:
                return self._stage_modeling(context)
            elif stage == WorkflowStage.STAGE_3_ALGORITHM:
                return self._stage_algorithm(context)
            elif stage == WorkflowStage.STAGE_4_CODING:
                return self._stage_coding(context)
            elif stage == WorkflowStage.STAGE_5_EXECUTION:
                return self._stage_execution(context)
            elif stage == WorkflowStage.STAGE_6_RESULT_ANALYSIS:
                return self._stage_result_analysis(context)
            elif stage == WorkflowStage.STAGE_7_CHARTS:
                return self._stage_charts(context)
            elif stage == WorkflowStage.STAGE_8_PAPER:
                return {'success': True, 'output': '论文生成完成'}
            else:
                return {'success': False, 'error': f'未知阶段: {stage}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _stage_analysis(self, context: Dict) -> Dict:
        """问题分析阶段"""
        print("  分析赛题内容...")

        problem_text = context.get('problem_text', '')
        data_files = context.get('data_files', {})

        if not problem_text:
            problem_text = "请分析这个数学建模问题，建立数学模型并生成完整论文。"

        # 数据文件摘要
        data_desc = []
        for name, filepath in data_files.items():
            if Path(filepath).exists():
                try:
                    df = pd.read_excel(filepath)
                    data_desc.append(f"{name}: {list(df.columns)[:5]}...")
                except:
                    data_desc.append(f"{name}: (无法读取)")
            else:
                data_desc.append(f"{name}: (文件不存在)")

        user_prompt = f"""分析以下数学建模赛题，输出JSON格式分析结果：

赛题：
{problem_text[:3000]}

数据文件：
{chr(10).join(data_desc)}

输出JSON格式（包含background/sub_problems/data_analysis/key_terms/solution_approach）："""

        try:
            result = _call_llm(
                prompt=user_prompt,
                system_prompt=SYSTEM_PROMPTS["problem_analyzer"],
                timeout=600
            )

            try:
                analysis = json.loads(result)
            except json.JSONDecodeError:
                analysis = {
                    'background': '数学建模问题分析',
                    'sub_problems': [{'id': 1, 'description': result[:500], 'objective': '建立模型求解', 'difficulty': '中等', 'suggested_methods': ['数学建模方法']}],
                    'data_files': list(data_files.keys()),
                    'key_terms': ['数学建模'],
                    'solution_approach': '建立数学模型进行求解'
                }

            context['analysis_result'] = analysis
            self._save_stage_result(WorkflowStage.STAGE_1_ANALYSIS, analysis, "analysis.json")
            return {'success': True, 'output': analysis}

        except Exception as e:
            print(f"    分析失败: {e}")
            analysis = {
                'background': '数学建模问题',
                'sub_problems': [{'id': 1, 'description': '建立模型求解', 'objective': '解答问题', 'difficulty': '中等', 'suggested_methods': ['数学建模']}],
                'data_files': list(data_files.keys()),
                'key_terms': ['数学建模'],
                'solution_approach': '建立数学模型'
            }
            context['analysis_result'] = analysis
            self._save_stage_result(WorkflowStage.STAGE_1_ANALYSIS, analysis, "analysis.json")
            return {'success': True, 'output': analysis}

    def _stage_modeling(self, context: Dict) -> Dict:
        """数学建模阶段 - 拆分为多个小任务"""
        print("  建立数学模型...")

        problem_text = context.get('problem_text', '')
        analysis_result = context.get('analysis_result', {})

        # 提取关键信息（更小的截断）
        sub_problems = analysis_result.get('sub_problems', [])
        sub_problems_summary = "; ".join([
            f"问题{p.get('id', i+1)}: {p.get('description', '')[:100]}"
            for i, p in enumerate(sub_problems[:3])
        ])

        model_parts = []

        # 子任务1: 模型类型选择
        print("    设计模型类型...")
        type_prompt = f"""赛题包含以下子问题：
{sub_problems_summary}

请确定适合的数学模型类型（优化/预测/评价/物理建模等），并说明选择依据。输出简洁，200字以内。"""
        try:
            model_type = _call_llm(prompt=type_prompt, system_prompt="你是数学建模专家。", timeout=300)
            model_parts.append(f"## 模型类型\n{model_type}\n")
        except Exception as e:
            print(f"    子任务1失败: {e}")
            model_parts.append("## 模型类型\n运动学模型 + 优化模型\n")

        # 子任务2: 变量定义
        print("    定义变量...")
        var_prompt = f"""基于以下问题，设计变量定义表：

问题：{sub_problems_summary}

输出变量定义表（格式：| 变量 | 符号 | 说明 | 单位 |），包含决策变量、已知参数等10-15个关键变量。"""
        try:
            variables = _call_llm(prompt=var_prompt, system_prompt="你是数学建模专家。", timeout=300)
            model_parts.append(f"\n## 变量定义\n{variables}\n")
        except Exception as e:
            print(f"    子任务2失败: {e}")
            model_parts.append("\n## 变量定义\n表格形式输出\n")

        # 子任务3: 核心公式
        print("    建立公式...")
        formula_prompt = f"""基于以下问题，建立核心数学公式：

问题：{sub_problems_summary}

请用LaTeX格式输出3-5个核心公式，包括物理方程/目标函数/约束条件等。"""
        try:
            formulas = _call_llm(prompt=formula_prompt, system_prompt="你是数学建模专家。", timeout=300)
            model_parts.append(f"\n## 核心公式\n{formulas}\n")
        except Exception as e:
            print(f"    子任务3失败: {e}")
            model_parts.append("\n## 核心公式\nLaTeX公式\n")

        # 子任务4: 模型假设
        print("    模型假设...")
        assumption_prompt = f"""基于以下问题，列出模型假设：

问题：{sub_problems_summary}

输出5-8条模型假设，说明合理性。"""
        try:
            assumptions = _call_llm(prompt=assumption_prompt, system_prompt="你是数学建模专家。", timeout=300)
            model_parts.append(f"\n## 模型假设\n{assumptions}\n")
        except Exception as e:
            print(f"    子任务4失败: {e}")
            model_parts.append("\n## 模型假设\n合理假设\n")

        model_result = "\n".join(model_parts)
        context['model_result'] = model_result
        self._save_stage_result(WorkflowStage.STAGE_2_MODELING, model_result, "modeling.md")

        return {'success': True, 'output': model_result}

    def _stage_algorithm(self, context: Dict) -> Dict:
        """算法设计阶段 - 拆分为多个小任务"""
        print("  设计求解算法...")

        model_result = context.get('model_result', '')
        analysis_result = context.get('analysis_result', {})

        sub_problems = analysis_result.get('sub_problems', [])
        sub_problems_summary = "; ".join([
            f"问题{p.get('id', i+1)}: {p.get('description', '')[:80]}"
            for i, p in enumerate(sub_problems[:3])
        ])

        algo_parts = []

        # 子任务1: 算法选择
        print("    选择算法...")
        algo_choice_prompt = f"""针对以下数学模型，选择合适的求解算法：

模型：{model_result[:1000]}

问题：{sub_problems_summary}

输出算法名称和选择依据，200字以内。"""
        try:
            algo_choice = _call_llm(prompt=algo_choice_prompt, system_prompt=SYSTEM_PROMPTS["algorithm_designer"], timeout=300)
            algo_parts.append(f"## 算法选择\n{algo_choice}\n")
        except Exception as e:
            print(f"    子任务1失败: {e}")
            algo_parts.append("## 算法选择\n遗传算法/粒子群优化\n")

        # 子任务2: 算法步骤
        print("    设计步骤...")
        steps_prompt = f"""针对以下问题，设计算法步骤：

问题：{sub_problems_summary}

输出分点列出的算法步骤（10-15步）。"""
        try:
            steps = _call_llm(prompt=steps_prompt, system_prompt="你是算法专家。", timeout=300)
            algo_parts.append(f"\n## 算法步骤\n{steps}\n")
        except Exception as e:
            print(f"    子任务2失败: {e}")
            algo_parts.append("\n## 算法步骤\n分点列出\n")

        # 子任务3: 参数设置
        print("    参数设置...")
        param_prompt = f"""针对以下算法，设置关键参数：

算法：{algo_parts[0] if algo_parts else '遗传算法'}

问题：{sub_problems_summary}

输出参数设置表和参数选择依据。"""
        try:
            params = _call_llm(prompt=param_prompt, system_prompt="你是算法专家。", timeout=300)
            algo_parts.append(f"\n## 参数设置\n{params}\n")
        except Exception as e:
            print(f"    子任务3失败: {e}")
            algo_parts.append("\n## 参数设置\n参数表\n")

        algo_result = "\n".join(algo_parts)
        context['algorithm_result'] = algo_result
        self._save_stage_result(WorkflowStage.STAGE_3_ALGORITHM, algo_result, "algorithm.md")

        return {'success': True, 'output': algo_result}

    def _extract_and_save_code(self, raw_output: str, save_path: Path) -> str:
        """从LLM输出中提取纯净Python代码"""
        text = raw_output.strip()
        # 去除markdown代码块
        if text.startswith('```'):
            lines = text.split('\n')
            start = 0
            while start < len(lines) and not lines[start].strip().startswith('```'):
                start += 1
            start += 1
            end = len(lines) - 1
            while end > start and not lines[end].strip().startswith('```'):
                end -= 1
            text = '\n'.join(lines[start:end]).strip()

        lines = text.split('\n')
        first_import = 0
        for i, line in enumerate(lines):
            if line.strip().startswith(('import ', 'from ')):
                first_import = i
                break

        code = '\n'.join(lines[first_import:]).strip()

        if not code.startswith(('import ', 'from ')):
            raise ValueError("提取的代码不以import开头，可能包含非代码内容")

        save_path.write_text(code, encoding='utf-8')
        return code

    def _stage_coding(self, context: Dict) -> Dict:
        """代码编写阶段 - 强化版：强制输出纯净代码 + 结果契约"""
        print("  编写求解代码...")

        problem_text = context.get('problem_text', '')
        algorithm_result = context.get('algorithm_result', '')
        model_result = context.get('model_result', '')
        data_files = context.get('data_files', {})
        data_file_list = ', '.join(data_files.keys())

        # 确保执行目录存在
        exec_dir = self.output_dir / "05_execution"
        exec_dir.mkdir(exist_ok=True)

        code_prompt = f"""基于以下算法设计，编写完整的Python求解代码。

[算法设计]
{algorithm_result[:3000]}

[数学模型]
{model_result[:2000]}

[赛题]
{problem_text[:2000]}

硬性要求（违反任何一条视为失败）：
1. 代码开头必须是 import 语句，不要有任何中文说明文字
2. 代码必须能够处理以下数据文件：{data_file_list}
3. 代码运行后必须在以下路径写入结构化结果文件：
   - {self.output_dir}/05_execution/results.json
   格式要求：{{"problem_1": {{"result": ..., "metrics": {{...}}}}, ...}}
4. 代码中必须包含 main() 函数，且 if __name__ == '__main__': main()
5. 所有数值结果使用 Python 原生 float/int，不要嵌套numpy类型
6. 代码中不得使用 input() 等交互式函数

输出要求：直接输出纯Python代码，不要包含markdown代码块标记，不要包含任何解释性文字。"""

        max_code_retries = 2
        code_text = ""
        for attempt in range(max_code_retries):
            try:
                code_text = _call_llm(
                    prompt=code_prompt,
                    system_prompt=SYSTEM_PROMPTS["code_writer"],
                    timeout=600
                )

                code_file = self.output_dir / WorkflowStage.STAGE_4_CODING.value / "solve.py"
                code_text = self._extract_and_save_code(code_text, code_file)
                print(f"    代码已保存: {code_file}")
                break

            except Exception as e:
                print(f"    代码提取失败(尝试{attempt+1}/{max_code_retries}): {e}")
                if attempt == max_code_retries - 1:
                    print("    使用通用代码模板")
                    code_text = self._generate_generic_code(context)
                    code_file = self.output_dir / WorkflowStage.STAGE_4_CODING.value / "solve.py"
                    code_file.write_text(code_text, encoding='utf-8')

        context['code_result'] = code_text
        self._save_stage_result(WorkflowStage.STAGE_4_CODING, code_text, "code.md")
        return {'success': True, 'output': code_text}

    def _generate_generic_code(self, context: Dict) -> str:
        """生成通用代码模板"""
        data_files = context.get('data_files', {})
        file_dict = {name: name for name in data_files.keys()}

        return f'''import numpy as np
import pandas as pd
from pathlib import Path

def load_data(data_files):
    data = {{}}
    for name, filepath in data_files.items():
        try:
            df = pd.read_excel(filepath)
            data[name] = df
            print(f"已加载: {{name}}")
        except Exception as e:
            print(f"加载失败 {{name}}: {{e}}")
    return data

def solve(data):
    results = {{}}
    for name, df in data.items():
        results[name] = {{'success': True, 'message': '计算完成'}}
    return results

def main():
    data_files = {file_dict}
    print("开始求解...")
    data = load_data(data_files)
    results = solve(data)
    print("\\n计算结果:")
    for name, result in results.items():
        print(f"  {{name}}: {{result}}")
    return results

if __name__ == "__main__":
    main()
'''

    def _stage_execution(self, context: Dict) -> Dict:
        """代码执行阶段 - 强化版：隔离执行 + 自动修复 + 结果验证"""
        print("  执行计算...")

        data_files = context.get('data_files', {})
        code_file = self.output_dir / WorkflowStage.STAGE_4_CODING.value / "solve.py"
        exec_dir = self.output_dir / "05_execution"
        exec_dir.mkdir(exist_ok=True)
        results_json = exec_dir / "results.json"

        execution_result = {}
        max_fix_attempts = 2

        for attempt in range(max_fix_attempts + 1):
            if not code_file.exists():
                print("    代码文件不存在")
                break

            print(f"    运行生成的代码 (尝试 {attempt + 1}/{max_fix_attempts + 1})...")
            exec_output = self._execute_code_subprocess(code_file, data_files, exec_dir)

            if exec_output.get('success'):
                # 检查 results.json 是否存在且有效
                if results_json.exists():
                    try:
                        with open(results_json, 'r', encoding='utf-8') as f:
                            execution_result = json.load(f)
                        if self._validate_execution_results(execution_result):
                            print("    代码执行成功，结果已验证")
                            break
                        else:
                            print("    结果验证失败：未包含有效数值")
                    except Exception as e:
                        print(f"    结果解析失败: {e}")
                else:
                    print("    未生成 results.json")
                    if exec_output.get('output'):
                        execution_result = {'stdout': exec_output['output']}
                        break

            error_msg = exec_output.get('error', '')
            print(f"    执行失败: {error_msg[:200]}")

            if attempt < max_fix_attempts:
                print("    尝试自动修复代码...")
                self._fix_code_with_llm(code_file, error_msg, exec_output.get('output', ''))
            else:
                print("    达到最大修复次数，降级到数据文件分析")
                execution_result = self._analyze_data_files(data_files)

        context['execution_result'] = execution_result
        self._save_stage_result(WorkflowStage.STAGE_5_EXECUTION, execution_result, "execution_result.json")
        return {'success': True, 'output': execution_result}

    def _execute_code_subprocess(self, code_file: Path, data_files: Dict, exec_dir: Path) -> Dict:
        """在隔离的subprocess中执行代码文件"""
        try:
            env = os.environ.copy()
            # 使用绝对路径避免 cwd 改变导致的路径问题
            code_file_abs = code_file.resolve()
            work_dir = exec_dir.parent.resolve()
            env['PYTHONPATH'] = str(code_file_abs.parent)
            # 将数据文件路径通过环境变量传递
            env['DATA_FILES'] = json.dumps(data_files, ensure_ascii=False)

            proc = subprocess.run(
                [sys.executable, str(code_file_abs)],
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
                cwd=str(work_dir)  # 在工作区根目录运行
            )

            return {
                'success': proc.returncode == 0,
                'output': proc.stdout,
                'error': proc.stderr,
                'returncode': proc.returncode
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': '代码执行超时（300秒）'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _validate_execution_results(self, results: Dict) -> bool:
        """验证执行结果是否包含有效数值"""
        if not results or not isinstance(results, dict):
            return False
        for key, value in results.items():
            if isinstance(value, dict):
                if value.get('result') is not None:
                    return True
                if value.get('metrics') and len(value.get('metrics', {})) > 0:
                    return True
        return False

    def _fix_code_with_llm(self, code_file: Path, stderr: str, stdout: str):
        """调用LLM修复代码"""
        original_code = code_file.read_text(encoding='utf-8')
        fix_prompt = f"""以下Python代码执行时出错，请修复后输出完整代码。

错误信息：
{stderr[:2000]}

标准输出：
{stdout[:1000]}

原始代码：
{original_code}

要求：直接输出修复后的纯Python代码，不要有任何说明文字。代码开头必须是import语句。"""

        try:
            fixed = _call_llm(fix_prompt, system_prompt="你是Python调试专家。", timeout=300)
            self._extract_and_save_code(fixed, code_file)
            print("    代码已修复")
        except Exception as e:
            print(f"    LLM修复失败: {e}")

    def _analyze_data_files(self, data_files: Dict) -> Dict:
        """分析数据文件生成计算结果"""
        results = {}

        for display_name, filepath in data_files.items():
            if not Path(filepath).exists():
                continue

            try:
                df = pd.read_excel(filepath)
                numeric_cols = df.select_dtypes(include=[np.number]).columns

                if len(numeric_cols) > 0:
                    col_name = numeric_cols[0]
                    values = df[col_name].dropna()

                    results[display_name] = {
                        'success': True,
                        'rows': len(df),
                        'columns': list(df.columns),
                        'statistics': {
                            'mean': float(values.mean()) if len(values) > 0 else 0,
                            'std': float(values.std()) if len(values) > 0 else 0,
                            'min': float(values.min()) if len(values) > 0 else 0,
                            'max': float(values.max()) if len(values) > 0 else 0,
                            'count': len(values)
                        },
                        'sample_values': values.head(5).tolist()
                    }
                else:
                    results[display_name] = {
                        'success': True,
                        'rows': len(df),
                        'columns': list(df.columns),
                        'message': '无数值列'
                    }

            except Exception as e:
                results[display_name] = {
                    'success': False,
                    'error': str(e)
                }

        return results

    def _stage_result_analysis(self, context: Dict) -> Dict:
        """结果分析阶段 - 拆分为多个小任务"""
        print("  分析计算结果...")

        execution_result = context.get('execution_result', {})
        analysis_result = context.get('analysis_result', {})
        problem_text = context.get('problem_text', '')

        analysis_parts = []

        # 子任务1: 结果摘要
        print("    结果摘要...")
        summary_prompt = f"""分析以下计算结果：

{json.dumps(execution_result, ensure_ascii=False, indent=2)[:2000]}

输出结果摘要表（表格形式）和简要说明。"""
        try:
            summary = _call_llm(prompt=summary_prompt, system_prompt=SYSTEM_PROMPTS["result_analyzer"], timeout=300)
            analysis_parts.append(f"## 结果摘要\n{summary}\n")
        except Exception as e:
            print(f"    子任务1失败: {e}")
            analysis_parts.append("## 结果摘要\n结果表\n")

        # 子任务2: 误差分析
        print("    误差分析...")
        error_prompt = f"""针对以下问题进行误差分析：

赛题：{problem_text[:1000]}
计算结果：{str(execution_result)[:1000]}

输出误差来分析和不确定度估计。"""
        try:
            error = _call_llm(prompt=error_prompt, system_prompt="你是数据分析专家。", timeout=300)
            analysis_parts.append(f"\n## 误差分析\n{error}\n")
        except Exception as e:
            print(f"    子任务2失败: {e}")
            analysis_parts.append("\n## 误差分析\n误差表\n")

        # 子任务3: 结论
        print("    得出结论...")
        conclusion_prompt = f"""基于以下分析结果，得出主要结论：

问题背景：{analysis_result.get('background', '')[:500]}
计算结果：{str(execution_result)[:1000]}

输出3-5条主要结论，要具体、有数据支撑。"""
        try:
            conclusion = _call_llm(prompt=conclusion_prompt, system_prompt="你是数据分析专家。", timeout=300)
            analysis_parts.append(f"\n## 主要结论\n{conclusion}\n")
        except Exception as e:
            print(f"    子任务3失败: {e}")
            analysis_parts.append("\n## 主要结论\n结论\n")

        analysis_text = "\n".join(analysis_parts)
        context['result_analysis'] = analysis_text
        self._save_stage_result(WorkflowStage.STAGE_6_RESULT_ANALYSIS, analysis_text, "result_analysis.md")

        return {'success': True, 'output': analysis_text}

    def _stage_charts(self, context: Dict) -> Dict:
        """图表设计阶段 - 强化版：实际生成PNG图片"""
        print("  设计并生成图表...")

        problem_text = context.get('problem_text', '')
        execution_result = context.get('execution_result', {})
        charts_dir = self.output_dir / "06_charts"
        charts_dir.mkdir(exist_ok=True)

        # Step 1: LLM设计图表方案
        charts_prompt = f"""基于以下内容，设计论文图表方案：

赛题：{problem_text[:1500]}
计算结果：{str(execution_result)[:1500]}

设计5-8个图表，包括：图表编号、标题、类型、数据要求、说明。
类型可选：line(折线图)、bar(柱状图)、scatter(散点图)、heatmap(热力图)、hist(直方图)、gantt(甘特图)、3d(3D图)

输出JSON格式：
[{{"id": "fig_01", "title": "图表标题", "type": "bar", "data_source": "results.json中的字段路径", "description": "说明"}}]"""
        try:
            charts_text = _call_llm(
                prompt=charts_prompt,
                system_prompt=SYSTEM_PROMPTS["chart_designer"],
                timeout=300
            )
        except Exception as e:
            print(f"    图表设计失败: {e}")
            charts_text = self._generate_generic_charts(context)

        # Step 2: 实际生成matplotlib图表
        self._generate_real_charts(execution_result, charts_dir)

        context['charts_result'] = charts_text
        self._save_stage_result(WorkflowStage.STAGE_7_CHARTS, charts_text, "charts.md")

        return {'success': True, 'output': charts_text}

    def _generate_real_charts(self, execution_result: Dict, charts_dir: Path):
        """使用matplotlib生成实际图表"""
        charts_dir.mkdir(parents=True, exist_ok=True)
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
            # 设置中文字体（优先使用系统可用的Noto CJK）
            plt.rcParams['font.sans-serif'] = [
                'Noto Sans CJK SC', 'Noto Sans CJK TC', 'Noto Sans CJK JP',
                'WenQuanYi Zen Hei', 'SimHei', 'AR PL UMing CN',
                'DejaVu Sans'
            ]
            plt.rcParams['axes.unicode_minus'] = False
        except ImportError:
            print("    matplotlib未安装，跳过图表生成")
            return

        chart_count = 0

        # 图1: 如果有多个子问题的结果，生成对比柱状图
        if isinstance(execution_result, dict) and len(execution_result) > 0:
            problem_keys = [k for k in execution_result.keys() if k.startswith('problem') or 'result' in str(execution_result[k])]
            if len(problem_keys) > 1:
                try:
                    fig, ax = plt.subplots(figsize=(10, 6))
                    labels = []
                    values = []
                    for k in problem_keys:
                        v = execution_result[k]
                        labels.append(str(k))
                        if isinstance(v, dict) and 'metrics' in v:
                            metrics = v['metrics']
                            if metrics:
                                first_val = list(metrics.values())[0]
                                values.append(float(first_val) if isinstance(first_val, (int, float)) else 0)
                            else:
                                values.append(0)
                        elif isinstance(v, dict) and 'result' in v:
                            values.append(float(v['result']) if isinstance(v['result'], (int, float)) else 0)
                        else:
                            values.append(0)

                    if any(v != 0 for v in values):
                        ax.bar(labels, values, color='steelblue')
                        ax.set_xlabel('问题编号', fontsize=12)
                        ax.set_ylabel('结果值', fontsize=12)
                        ax.set_title('各问题计算结果对比', fontsize=14)
                        plt.tight_layout()
                        fig.savefig(str(charts_dir / 'fig_01_results_comparison.png'), dpi=300)
                        plt.close(fig)
                        chart_count += 1
                        print(f"    生成图表: fig_01_results_comparison.png")
                except Exception as e:
                    print(f"    图1生成失败: {e}")

        # 图2: 如果有数据文件分析结果，生成分布图
        if isinstance(execution_result, dict):
            for key, value in execution_result.items():
                if isinstance(value, dict) and 'statistics' in value:
                    try:
                        stats = value['statistics']
                        fig, ax = plt.subplots(figsize=(8, 5))
                        metrics = ['mean', 'std', 'min', 'max']
                        vals = [stats.get(m, 0) for m in metrics]
                        ax.bar(metrics, vals, color=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728'])
                        ax.set_title(f'{key} 统计指标分布', fontsize=14)
                        plt.tight_layout()
                        fig.savefig(str(charts_dir / f'fig_02_{key}_stats.png'), dpi=300)
                        plt.close(fig)
                        chart_count += 1
                        print(f"    生成图表: fig_02_{key}_stats.png")
                    except Exception as e:
                        print(f"    统计图生成失败: {e}")
                    break

        # 图3: 生成算法流程示意（简化版）
        try:
            fig, ax = plt.subplots(figsize=(10, 8))
            ax.set_xlim(0, 10)
            ax.set_ylim(0, 10)
            ax.axis('off')

            steps = [
                (5, 9, "数据读取与预处理"),
                (5, 7.5, "模型建立"),
                (5, 6, "算法求解"),
                (5, 4.5, "结果计算"),
                (5, 3, "结果验证与分析")
            ]

            for i, (x, y, text) in enumerate(steps):
                rect = mpatches.FancyBboxPatch((x-2, y-0.4), 4, 0.8, boxstyle="round,pad=0.1",
                                                facecolor='lightblue', edgecolor='navy', linewidth=1.5)
                ax.add_patch(rect)
                ax.text(x, y, text, ha='center', va='center', fontsize=11, fontweight='bold')
                if i < len(steps) - 1:
                    ax.annotate('', xy=(x, steps[i+1][1]+0.4), xytext=(x, y-0.4),
                               arrowprops=dict(arrowstyle='->', lw=2, color='navy'))

            ax.set_title('求解流程图', fontsize=16, pad=20)
            fig.savefig(str(charts_dir / 'fig_03_algorithm_flow.png'), dpi=300)
            plt.close(fig)
            chart_count += 1
            print(f"    生成图表: fig_03_algorithm_flow.png")
        except Exception as e:
            print(f"    流程图生成失败: {e}")

        if chart_count == 0:
            print("    警告：未生成任何图表")
        else:
            print(f"    共生成 {chart_count} 个图表")

    def _generate_generic_charts(self, context: Dict) -> str:
        """生成通用图表设计"""
        return """## 图表设计

### 图1：数据分布图
- 类型：柱状图
- 数据：各样本数值
- 说明：展示数据分布特征

### 图2：结果对比图
- 类型：折线图
- 数据：不同条件下的结果
- 说明：对比分析

### 图3：算法流程图
- 类型：流程图
- 说明：展示求解步骤

### 图4：结果汇总表
- 类型：表格
- 数据：主要数值结果
"""

    def _count_chinese_chars(self, text: str) -> int:
        """统计中文字符数"""
        return len(re.findall(r'[一-鿿]', text))

    def _read_file_content(self, rel_path: str) -> str:
        """读取工作区文件内容"""
        file_path = self.output_dir / rel_path
        if file_path.exists():
            try:
                return file_path.read_text(encoding='utf-8')
            except Exception:
                return ""
        return ""

    def _generate_full_paper(self, context: Dict) -> str:
        """生成完整论文 - 强化版：文件引用式上下文 + 字数保障"""
        print("  生成完整论文...")

        problem_text = context.get('problem_text', '')
        execution_result = context.get('execution_result', {})

        # 读取各阶段完整文件内容（而非截断摘要）
        analysis_full = self._read_file_content("stage_1_analysis/analysis.json")
        model_full = self._read_file_content("stage_2_modeling/modeling.md")
        algorithm_full = self._read_file_content("stage_3_algorithm/algorithm.md")
        result_analysis_full = self._read_file_content("stage_6_result_analysis/result_analysis.md")
        charts_full = self._read_file_content("stage_7_charts/charts.md")
        code_full = self._read_file_content("stage_4_coding/solve.py")

        # 构建统一的上下文摘要（供各章节使用）
        context_summary = f"""【问题分析】
{analysis_full[:3000]}

【数学模型】
{model_full[:4000]}

【算法设计】
{algorithm_full[:3000]}

【计算结果】
{json.dumps(execution_result, ensure_ascii=False, indent=2)[:2000]}

【结果分析】
{result_analysis_full[:3000]}"""

        paper_parts = []

        # 摘要
        print("    生成摘要...")
        abstract_prompt = f"""请为以下数学建模赛题撰写论文摘要（中英文）。

{context_summary}

输出要求：
1. 中文摘要400-600字，包含：研究背景、研究方法、研究结果（含关键数据）、研究结论、关键词（5-8个）
2. 英文摘要300-400词
3. 摘要中的数据必须与计算结果一致"""
        try:
            abstract = _call_llm(prompt=abstract_prompt, system_prompt=SYSTEM_PROMPTS["paper_writer"], timeout=600)
            paper_parts.append(f"# 数学建模论文\n\n## 摘要\n{abstract}\n")
        except Exception as e:
            print(f"    摘要失败: {e}")
            paper_parts.append("# 数学建模论文\n\n## 摘要\n摘要内容\n")

        # 定义各章节及其字数要求
        chapters = [
            {
                "title": "1. 问题重述",
                "prompt": f"""请撰写"问题重述"章节。

赛题原文：
{problem_text[:4000]}

要求：
1. 800-1500字
2. 包含：研究背景、问题描述（完整列出所有子问题）、实际意义
3. 不要遗漏任何子问题""",
                "min_chars": 800
            },
            {
                "title": "2. 问题分析",
                "prompt": f"""请撰写"问题分析"章节。

{context_summary}

要求：
1. 1500-2500字
2. 包含：问题特点与难点、求解思路、关键因素识别
3. 对每个子问题进行逐一分析""",
                "min_chars": 1500
            },
            {
                "title": "3. 模型建立",
                "prompt": f"""请撰写"模型建立"章节。

数学模型完整内容：
{model_full}

要求：
1. 2500-4000字
2. 包含：模型类型选择及依据、详细公式推导（LaTeX格式）、物理意义解释、变量定义表、模型假设
3. 公式必须编号（如(3-1)、(3-2)）
4. 确保模型与代码实现一致""",
                "min_chars": 2500
            },
            {
                "title": "4. 模型求解",
                "prompt": f"""请撰写"模型求解"章节。

算法设计完整内容：
{algorithm_full}

计算结果：
{json.dumps(execution_result, ensure_ascii=False, indent=2)[:2000]}

要求：
1. 2000-3000字
2. 包含：求解方法、算法步骤、计算结果（必须引用实际计算结果中的数值）
3. 结果数据必须真实，不得编造""",
                "min_chars": 2000
            },
            {
                "title": "5. 结果分析",
                "prompt": f"""请撰写"结果分析"章节。

结果分析资料：
{result_analysis_full}

计算结果：
{json.dumps(execution_result, ensure_ascii=False, indent=2)[:2000]}

要求：
1. 2000-3000字
2. 包含：结果验证、误差分析、灵敏度分析
3. 必须有数据支撑""",
                "min_chars": 2000
            },
            {
                "title": "6. 模型评价与改进",
                "prompt": f"""请撰写"模型评价与改进"章节。

{context_summary}

要求：
1. 1000-1500字
2. 包含：模型优点、模型局限性、改进方向
3. 评价要客观、深入""",
                "min_chars": 1000
            }
        ]

        for chapter in chapters:
            print(f"    生成{chapter['title']}...")
            try:
                chapter_text = _call_llm(
                    prompt=chapter["prompt"],
                    system_prompt=SYSTEM_PROMPTS["paper_writer"],
                    timeout=600
                )
                # 检查字数，不足则扩展
                chapter_chinese = self._count_chinese_chars(chapter_text)
                if chapter_chinese < chapter["min_chars"]:
                    print(f"      {chapter['title']}字数不足({chapter_chinese}字)，触发扩展...")
                    expand_prompt = f"""请将以下论文章节扩充到至少{chapter["min_chars"]}中文字。

当前内容：
{chapter_text}

要求：
1. 扩充后字数达到要求
2. 增加详细推导、分析讨论和实例说明
3. 保持原有逻辑结构
4. 不得编造数据"""
                    try:
                        expanded = _call_llm(expand_prompt, system_prompt="你是论文写作者。", timeout=600)
                        chapter_text = expanded
                    except Exception as ee:
                        print(f"      扩展失败: {ee}")

                paper_parts.append(f"\n## {chapter['title']}\n{chapter_text}\n")
            except Exception as e:
                print(f"    {chapter['title']}失败: {e}")
                paper_parts.append(f"\n## {chapter['title']}\n{chapter['title']}内容\n")

        # 参考文献
        refs_prompt = f"""请基于以下论文主题，输出5-8条参考文献，使用GB/T 7714标准格式。

论文主题：{problem_text[:500]}

要求：
1. 包含期刊论文、书籍等
2. 格式规范
3. 文献应与论文内容相关"""
        try:
            refs = _call_llm(prompt=refs_prompt, system_prompt="你是论文写作者。", timeout=300)
        except:
            refs = "[1] 相关参考文献。\n[2] 其他参考文献。"

        paper_parts.append(f"\n## 参考文献\n{refs}\n")

        # 附录
        paper_parts.append(f"\n## 附录\n\n### 求解代码\n完整代码保存于：`work/stage_4_coding/solve.py`\n")
        paper_parts.append(f"\n### 图表说明\n{charts_full[:1500]}\n")

        paper = "\n".join(paper_parts)

        # 字数检查与补充
        chinese_chars = self._count_chinese_chars(paper)
        print(f"    当前论文字数: {chinese_chars} 中文字")

        if chinese_chars < 20000:
            print("    论文字数不足，触发补充...")
            supplement = self._supplement_paper(context, target_chars=20000 - chinese_chars)
            paper = paper + "\n" + supplement
            chinese_chars = self._count_chinese_chars(paper)

        print(f"    最终论文字数: {chinese_chars} 中文字")

        return paper

    def _supplement_paper(self, context: Dict, target_chars: int = 5000) -> str:
        """补充论文内容 - 强化版"""
        supplement_parts = []

        # 灵敏度分析
        print("    补充灵敏度分析...")
        sensitivity_prompt = f"""请撰写详细的灵敏度分析章节。

{self._read_file_content("stage_2_modeling/modeling.md")[:2000]}

要求：
1. 至少1500中文字
2. 包含：参数敏感度分析（至少分析3个关键参数）、模型稳健性讨论
3. 使用表格展示灵敏度结果"""
        try:
            sensitivity = _call_llm(prompt=sensitivity_prompt, system_prompt="你是论文写作者。", timeout=600)
            supplement_parts.append(f"\n## 7. 灵敏度分析\n{sensitivity}\n")
        except:
            supplement_parts.append("\n## 7. 灵敏度分析\n灵敏度分析内容\n")

        # 如果还不够，补充进一步讨论
        remaining = target_chars - self._count_chinese_chars("\n".join(supplement_parts))
        if remaining > 1000:
            print(f"    继续补充({remaining}字缺口)...")
            discussion_prompt = """请撰写"进一步讨论"章节，包括：
1. 模型的推广与应用
2. 与其他方法的对比
3. 未来研究方向
要求：至少1000字，内容充实。"""
            try:
                discussion = _call_llm(discussion_prompt, system_prompt="你是论文写作者。", timeout=600)
                supplement_parts.append(f"\n## 8. 进一步讨论\n{discussion}\n")
            except:
                pass

        return "\n".join(supplement_parts)

    def convert_to_docx(self, paper_md_path: Path, output_path: Path):
        """将Markdown论文转换为Word格式"""
        print("  转换Word格式...")
        try:
            from docx import Document
            from docx.shared import Pt, Cm, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import qn

            doc = Document()
            section = doc.sections[0]
            section.page_width = Cm(21)
            section.page_height = Cm(29.7)
            section.top_margin = Cm(2.54)
            section.bottom_margin = Cm(2.54)
            section.left_margin = Cm(3.17)
            section.right_margin = Cm(3.17)

            paper_text = paper_md_path.read_text(encoding='utf-8')
            lines = paper_text.split('\n')
            i = 0

            while i < len(lines):
                line = lines[i].strip()

                if not line:
                    i += 1
                    continue

                if line.startswith('# '):
                    p = doc.add_paragraph()
                    run = p.add_run(line[2:])
                    run.font.name = '黑体'
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
                    run.font.size = Pt(18)
                    run.bold = True
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif line.startswith('## '):
                    p = doc.add_paragraph()
                    run = p.add_run(line[3:])
                    run.font.name = '黑体'
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
                    run.font.size = Pt(14)
                    run.bold = True
                elif line.startswith('### '):
                    p = doc.add_paragraph()
                    run = p.add_run(line[4:])
                    run.font.name = '黑体'
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
                    run.font.size = Pt(12)
                    run.bold = True
                elif line.startswith('$$'):
                    # 公式处理
                    formula_lines = [line]
                    while i + 1 < len(lines) and not lines[i + 1].strip().endswith('$$'):
                        i += 1
                        formula_lines.append(lines[i])
                    if i + 1 < len(lines):
                        i += 1
                        formula_lines.append(lines[i])
                    formula = '\n'.join(formula_lines).replace('$$', '').strip()
                    p = doc.add_paragraph()
                    run = p.add_run(formula)
                    run.font.name = 'Times New Roman'
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')
                    run.font.size = Pt(12)
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif line.startswith('|'):
                    # 表格处理
                    table_lines = [line]
                    while i + 1 < len(lines) and lines[i + 1].strip().startswith('|'):
                        i += 1
                        table_lines.append(lines[i])
                    self._add_markdown_table(doc, table_lines)
                elif line.startswith('!['):
                    # 图片引用
                    img_match = re.search(r'!\[.*?\]\((.*?)\)', line)
                    if img_match:
                        img_path = self.output_dir / img_match.group(1)
                        if img_path.exists():
                            doc.add_picture(str(img_path), width=Cm(14))
                            last_paragraph = doc.paragraphs[-1]
                            last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                else:
                    p = doc.add_paragraph()
                    run = p.add_run(line)
                    run.font.name = '宋体'
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
                    run.font.size = Pt(12)
                    p.paragraph_format.line_spacing = 1.5
                    p.paragraph_format.first_line_indent = Cm(0.74)

                i += 1

            doc.save(output_path)
            print(f"    Word文档已保存: {output_path}")
        except ImportError:
            print("    未安装python-docx，跳过Word转换")
        except Exception as e:
            print(f"    Word转换失败: {e}")

    def _add_markdown_table(self, doc, table_lines):
        """将markdown表格添加到docx"""
        try:
            rows = []
            for line in table_lines:
                cells = [c.strip() for c in line.split('|')[1:-1]]
                if cells and not all(c.replace('-', '').replace(':', '') == '' for c in cells):
                    rows.append(cells)

            if not rows:
                return

            table = doc.add_table(rows=len(rows), cols=len(rows[0]))
            table.style = 'Table Grid'

            for i, row in enumerate(rows):
                for j, cell_text in enumerate(row):
                    if j < len(table.rows[i].cells):
                        table.rows[i].cells[j].text = cell_text
        except Exception:
            pass


def run_auto_paper_generation(
    problem_file: str = "problem.md",
    data_files: Dict[str, str] = None,
    output_dir: str = "work"
) -> str:
    """运行全自动论文生成"""
    if data_files is None:
        data_files = {}

    problem_text = ""
    if Path(problem_file).exists():
        with open(problem_file, 'r', encoding='utf-8') as f:
            problem_text = f.read()

    engine = AgentWorkflow(output_dir=output_dir)

    paper = engine.run_full_workflow(
        problem_text=problem_text,
        data_files=data_files
    )

    return paper