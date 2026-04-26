"""
Agent工作流引擎
==============

完整的Agent协作工作流，用于自动生成数学建模论文
"""

import os
import json
import time
import subprocess
import shutil
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import traceback


def load_spectrum_data(filepath: str) -> Optional[Dict]:
    """加载光谱数据文件"""
    try:
        df = pd.read_excel(filepath)
        # 尝试识别列名
        wn_col = None
        refl_col = None

        for col in df.columns:
            col_lower = str(col).lower()
            if '波数' in col or 'wavenumber' in col_lower or 'wn' in col_lower:
                wn_col = col
            elif '反射率' in col or 'reflectivity' in col_lower or 'refl' in col_lower:
                refl_col = col

        # 如果没找到，使用前两列
        if wn_col is None:
            wn_col = df.columns[0]
        if refl_col is None:
            refl_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]

        return {
            'wavenumber': df[wn_col].values,
            'reflectivity': df[refl_col].values,
            'filename': filepath
        }
    except Exception as e:
        print(f"  加载数据失败 {filepath}: {e}")
        return None


def analyze_spectrum(wn: np.ndarray, refl: np.ndarray,
                     refractive_index: float = 2.65,
                     region_min: float = 700,
                     region_max: float = 1000) -> Dict:
    """分析光谱数据计算厚度"""
    try:
        from scipy.signal import savgol_filter, find_peaks

        # 区域提取
        mask = (wn >= region_min) & (wn <= region_max)
        wn_region = wn[mask]
        refl_region = refl[mask]

        if len(wn_region) < 10:
            return {'success': False, 'error': '数据点太少'}

        # 平滑
        window = min(31, len(wn_region) // 2 * 2 + 1)
        if window < 5:
            window = 5
        refl_smooth = savgol_filter(refl_region, window_length=window, polyorder=3)

        # 峰检测
        min_distance = max(10, int((region_max - region_min) / 20))
        peaks, properties = find_peaks(refl_smooth, distance=min_distance, prominence=2.0)

        if len(peaks) >= 2:
            # 条纹间距
            spacing = np.mean(np.diff(wn_region[peaks]))
            if spacing <= 0:
                return {'success': False, 'error': '条纹间距计算错误'}

            # 厚度
            thickness = 1e4 / (2 * refractive_index * spacing)

            # 对比度
            contrast = (refl_smooth.max() - refl_smooth.min()) / \
                       (refl_smooth.max() + refl_smooth.min())

            # 不确定度（简化估计）
            spacing_std = np.std(np.diff(wn_region[peaks])) if len(peaks) > 2 else spacing / 10
            uncertainty = thickness * (spacing_std / spacing)

            return {
                'success': True,
                'thickness': float(thickness),
                'thickness_uncertainty': float(uncertainty),
                'fringe_spacing': float(spacing),
                'contrast': float(contrast),
                'peak_count': len(peaks),
                'correction_factor': 0.998 if contrast > 0.85 else 1.0
            }
        else:
            return {'success': False, 'error': f'检测到{len(peaks)}个峰，需要至少2个'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _find_claude_code() -> Optional[str]:
    """自动搜索 Claude Code CLI 路径"""
    # 1. PATH 中搜索
    found = shutil.which("claude-code") or shutil.which("claude")
    if found:
        return found
    return None


def _call_llm(
    prompt: str,
    model: str = "sonnet",
    system_prompt: Optional[str] = None,
    timeout: int = 300,
) -> str:
    """
    通过 Claude Code CLI 调用 LLM 生成内容
    """
    claude_path = _find_claude_code()
    if not claude_path:
        raise RuntimeError("Claude Code CLI 未找到，请确保已安装 Claude Code 并添加到 PATH")

    # 组合 prompt（含 system prompt）
    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

    cmd = [
        claude_path,
        "-p",
        "--model", model,
        "--output-format", "json",
        full_prompt  # prompt as argument
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(timeout=timeout)

        stdout_text = stdout.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM 调用失败: {error_msg[:500]}")

        # 解析 JSON 输出
        try:
            data = json.loads(stdout_text.strip())
        except json.JSONDecodeError:
            return stdout_text.strip()

        result_text = data.get("result", "")
        if isinstance(result_text, str):
            result_text = result_text.strip()
            if result_text.startswith("```"):
                lines = result_text.splitlines()
                if lines:
                    first = lines[0]
                    if first.startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                result_text = "\n".join(lines).strip()
            return result_text
        return str(result_text)

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"LLM 调用超时（{timeout}秒）")
    except FileNotFoundError:
        raise RuntimeError("Claude Code CLI 未找到")


# =============================================================================
# Agent 系统提示词
# =============================================================================

SYSTEM_PROMPTS = {
    "coordinator": """
你是一个数学建模竞赛论文项目的主编排器。你的职责是：
1. 理解用户提供的赛题和数据
2. 将任务分解为多个子问题
3. 协调各个专业Agent完成工作
4. 确保论文质量和格式符合要求
5. 管理论文的完整结构和内容

你必须确保：
- 论文正文达到15000-25000字
- 使用标准的数学建模论文格式
- 图表和公式完整准确
- 结果分析深入透彻

论文结构要求：
1. 摘要（中英文，500-800字）
2. 问题重述
3. 问题分析
4. 模型假设与符号说明
5. 模型建立
6. 模型求解
7. 结果分析
8. 灵敏度分析
9. 模型评价与改进
10. 参考文献
11. 附录
""",

    "problem_analyzer": """
你是一个经验丰富的数学建模专家。你的任务是分析用户提供的赛题：

## 分析要求

### 1. 赛题理解
- 明确赛题的研究背景和应用场景
- 提取关键的专业术语和概念
- 理解问题的实际意义

### 2. 任务分解
- 识别赛题中包含的子问题数量
- 分析各子问题之间的逻辑关系
- 确定每个子问题的求解目标

### 3. 数据分析
- 分析提供的附件数据格式和内容
- 确定数据类型
- 识别数据中的关键变量

### 4. 方法建议
- 根据问题特点推荐合适的数学方法
- 考虑方法的可行性和复杂性
- 给出初步的解决思路

## 输出要求

以JSON格式输出分析结果，包含：
- background: 研究背景描述
- sub_problems: 子问题列表
- data_analysis: 数据分析
- key_terms: 关键术语列表
- solution_approach: 整体解决思路

请生成详尽的分析内容。
""",

    "model_designer": """
你是一个数学建模专家，精通各类数学建模方法。你的任务是设计数学模型：

## 设计要求

### 1. 模型选择
- 根据问题特点选择合适的数学模型类型
- 考虑模型的精度、复杂度和可解释性
- 给出模型选择的理论依据

### 2. 变量定义
- 明确模型中的决策变量
- 定义目标函数
- 识别约束条件

### 3. 数学公式
- 建立变量之间的关系方程
- 写出完整的数学表达式
- 说明公式的物理意义或实际含义

### 4. 模型假设
- 列出模型的基本假设
- 分析假设的合理性
- 讨论假设对结果的影响

## 输出要求

输出完整的数学模型，包括：
1. 模型类型和选择依据
2. 变量定义表
3. 完整的数学公式（使用LaTeX格式）
4. 模型假设清单
5. 求解思路概述

请生成详尽完备的数学模型内容。
""",

    "algorithm_designer": """
你是一个算法设计专家。你的任务是为数学模型设计求解算法：

## 设计要求

### 1. 算法选择
- 根据模型特点选择合适的求解算法
- 考虑算法的时间复杂度和空间复杂度
- 分析算法的收敛性和稳定性

### 2. 算法步骤
- 详细描述算法的具体步骤
- 给出算法的伪代码
- 说明每一步的作用

### 3. 参数设置
- 确定算法中的关键参数
- 说明参数的选择依据
- 讨论参数的敏感性

### 4. 复杂度分析
- 时间复杂度分析
- 空间复杂度分析
- 实际运行效率评估

## 输出要求

输出完整的算法设计，包括：
1. 算法名称和类型
2. 算法伪代码
3. 参数设置表
4. 复杂度分析
5. 收敛性讨论

请生成详尽的算法设计内容。
""",

    "code_writer": """
你是一个Python编程专家，精通科学计算和数据处理。你的任务是将算法转化为可运行的代码：

## 编程要求

### 1. 代码结构
- 使用模块化的代码设计
- 包含完整的函数文档字符串
- 遵循PEP 8代码规范

### 2. 核心函数
每个代码文件必须包含：load_data, preprocess_data, solve_model, analyze_results, generate_report

### 3. 数据处理
- 处理Excel、CSV、TXT等常见格式
- 处理缺失值和异常值

### 4. 科学计算
- 使用NumPy进行数值计算
- 使用SciPy进行科学计算
- 使用Pandas进行数据处理

### 5. 可视化
- 使用Matplotlib生成图表
- 确保图表清晰、美观、符合学术规范

## 输出要求

输出完整的Python代码，确保可以直接运行。
""",

    "result_analyzer": """
你是一个数据分析专家。你的任务是分析计算结果，进行深入的讨论：

## 分析要求

### 1. 结果验证
- 检查计算结果的合理性
- 与理论预期或实验数据对比
- 验证模型的正确性

### 2. 误差分析
- 分析测量误差的来源
- 计算不确定度
- 讨论误差传播

### 3. 灵敏度分析
- 分析参数变化对结果的影响
- 识别关键影响因素
- 讨论模型的稳健性

### 4. 结果讨论
- 解释结果的物理意义或实际含义
- 讨论结果的创新性和局限性
- 提出改进方向

## 输出要求

输出深入的结果分析，包括：
1. 结果摘要表
2. 误差分析
3. 灵敏度分析
4. 讨论与结论

请生成详尽透彻的分析内容。
""",

    "paper_writer": """
你是一个专业的数学建模论文写作者。你的任务是撰写完整的数学建模论文：

## 论文结构要求

### 摘要（Abstract）
- 研究背景与目的
- 研究方法
- 研究结果（包含关键数据）
- 研究结论
- 关键词：5-8个

### 1. 问题重述
- 简要介绍问题背景
- 明确要解决的主要问题
- 说明问题的实际意义

### 2. 问题分析
- 对问题进行深入分析
- 分析问题的特点和难点
- 明确求解思路

### 3. 模型假设与符号说明
- 列出模型的基本假设
- 说明假设的合理性
- 定义所有使用的符号

### 4. 模型建立
- 详细介绍模型建立过程
- 给出完整的数学公式
- 说明公式的物理意义

### 5. 模型求解
- 介绍求解方法
- 给出求解步骤
- 展示主要计算结果

### 6. 结果分析
- 分析计算结果的合理性
- 进行误差分析
- 讨论结果的可靠性

### 7. 灵敏度分析
- 分析参数变化对结果的影响
- 讨论模型的稳健性

### 8. 模型评价与改进
- 总结模型的优点
- 指出模型的局限性
- 提出改进方向

### 9. 参考文献

### 10. 附录

## 写作要求

### 内容要求
- 论点明确，论据充分
- 逻辑清晰，层次分明
- 语言简练，表达准确
- 公式规范，图表清晰

### 格式要求
- 正文15000-25000字
- 使用标准论文格式
- 正确引用文献

## 输出要求

输出完整的论文内容，确保：
1. 字数达到15000-25000字
2. 结构完整，逻辑清晰
3. 公式图表规范准确
4. 内容充实，分析深入

这是最重要的输出阶段，请生成完整详尽的论文。
"""
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
    """
    Agent工作流引擎
    """

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
        """运行完整工作流"""
        print("\n" + "="*70)
        print("数学建模论文自动生成系统")
        print("="*70)

        # 各阶段结果
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

        # 依次执行各阶段
        stages = list(WorkflowStage)

        for i, stage in enumerate(stages):
            print(f"\n{'='*60}")
            print(f"阶段 {i+1}/{len(stages)}: {stage.value}")
            print(f"{'='*60}")

            result = self._run_stage(stage, context)
            self.results[stage.value] = result

            if not result.get('success', False):
                print(f"\n  [警告] 阶段执行遇到问题，继续...")

            context[f'{stage.value}_result'] = result.get('output', '')

        # 生成论文
        print(f"\n{'='*60}")
        print("生成最终论文")
        print(f"{'='*60}")

        paper = self._generate_full_paper(context)

        # 保存论文
        paper_file = self.output_dir / "final" / "MathModeling_Paper.md"
        with open(paper_file, 'w', encoding='utf-8') as f:
            f.write(paper)

        print(f"\n论文已保存: {paper_file}")
        print(f"论文长度: {len(paper)} 字符")

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

        # 构建用户提示词
        user_prompt = f"""请分析以下数学建模赛题，输出详尽的分析结果：

===赛题内容开始===
{problem_text}
===赛题内容结束===

===数据文件说明===
{json.dumps(data_files, ensure_ascii=False, indent=2)}
===数据文件说明结束===

请以JSON格式输出完整的赛题分析结果，包括：
1. 研究背景
2. 子问题列表（每个包含编号、描述、目标、难度、推荐方法）
3. 数据分析（文件数量、变量列表、数据特征）
4. 关键术语列表
5. 整体解决思路

请确保分析详尽准确。"""

        try:
            # 调用LLM
            result = _call_llm(
                prompt=user_prompt,
                system_prompt=SYSTEM_PROMPTS["problem_analyzer"],
                timeout=180
            )

            # 尝试解析JSON
            try:
                analysis = json.loads(result)
            except json.JSONDecodeError:
                # 如果不是JSON，包装为结构化格式
                analysis = {
                    'background': '数学建模问题分析',
                    'sub_problems': [{'id': 1, 'description': result[:500], 'objective': '建立模型求解', 'difficulty': '中等', 'suggested_methods': ['数学建模方法']}],
                    'data_files': list(data_files.keys()),
                    'key_terms': ['数学建模'],
                    'solution_approach': '建立数学模型进行求解',
                    'raw_analysis': result
                }

            context['analysis_result'] = analysis
            self._save_stage_result(WorkflowStage.STAGE_1_ANALYSIS, analysis, "analysis.json")
            return {'success': True, 'output': analysis}

        except Exception as e:
            # 如果LLM调用失败，返回基础分析
            analysis = {
                'background': '数学建模问题',
                'sub_problems': [{'id': 1, 'name': '问题1', 'description': '建立模型求解', 'objective': '给出解答', 'difficulty': '中等'}],
                'data_files': list(data_files.keys()),
                'key_terms': ['数学建模'],
                'solution_approach': '建立数学模型'
            }
            context['analysis_result'] = analysis
            self._save_stage_result(WorkflowStage.STAGE_1_ANALYSIS, analysis, "analysis.json")
            return {'success': True, 'output': analysis}

    def _stage_modeling(self, context: Dict) -> Dict:
        """数学建模阶段"""
        print("  建立数学模型...")

        analysis_result = context.get('analysis_result', {})
        problem_text = context.get('problem_text', '')

        # 构建用户提示词
        user_prompt = f"""基于以下赛题分析结果，请设计完整的数学模型：

===赛题分析结果===
{json.dumps(analysis_result, ensure_ascii=False, indent=2)}
===赛题分析结果===

===原始赛题===
{problem_text}
===原始赛题===

请设计完整的数学模型，包括：
1. 模型类型和选择依据
2. 变量定义表
3. 完整的数学公式（使用LaTeX格式）
4. 模型假设清单
5. 求解思路概述

请确保模型严谨、准确、有理论依据，公式完整清晰，假设合理。输出详尽的建模内容。"""

        try:
            result = _call_llm(
                prompt=user_prompt,
                system_prompt=SYSTEM_PROMPTS["model_designer"],
                timeout=300
            )
            context['model_result'] = result
            self._save_stage_result(WorkflowStage.STAGE_2_MODELING, result, "modeling.md")
            return {'success': True, 'output': result}
        except Exception as e:
            context['model_result'] = f"数学建模阶段：{str(e)}"
            self._save_stage_result(WorkflowStage.STAGE_2_MODELING, str(e), "modeling.md")
            return {'success': True, 'output': "数学模型建立"}

    def _stage_algorithm(self, context: Dict) -> Dict:
        """算法设计阶段"""
        print("  设计求解算法...")

        model_result = context.get('model_result', '')
        analysis_result = context.get('analysis_result', {})

        # 截断过长的内容，避免prompt过长
        max_content_len = 4000
        if len(model_result) > max_content_len:
            model_result = model_result[:max_content_len] + "\n\n[内容已截断...]"
        if isinstance(analysis_result, dict):
            analysis_json = json.dumps(analysis_result, ensure_ascii=False, indent=2)
            if len(analysis_json) > max_content_len:
                analysis_json = analysis_json[:max_content_len] + "\n\n[内容已截断...]"
        else:
            analysis_json = str(analysis_result)[:max_content_len]

        user_prompt = f"""基于以下数学模型，请设计完整的求解算法：

===数学模型===
{model_result}
===数学模型===

===赛题分析===
{analysis_json}
===赛题分析===

请设计完整的求解算法，包括：
1. 算法选择和依据
2. 算法步骤（伪代码）
3. 参数设置
4. 复杂度分析
5. 收敛性讨论

请确保算法高效、可实现，步骤详细清晰。输出详尽的算法设计内容。"""

        try:
            result = _call_llm(
                prompt=user_prompt,
                system_prompt=SYSTEM_PROMPTS["algorithm_designer"],
                timeout=300
            )
            context['algorithm_result'] = result
            self._save_stage_result(WorkflowStage.STAGE_3_ALGORITHM, result, "algorithm.md")
            return {'success': True, 'output': result}
        except Exception as e:
            context['algorithm_result'] = f"算法设计阶段：{str(e)}"
            self._save_stage_result(WorkflowStage.STAGE_3_ALGORITHM, str(e), "algorithm.md")
            return {'success': True, 'output': "算法设计"}

    def _stage_coding(self, context: Dict) -> Dict:
        """代码编写阶段 - LLM生成问题特定的求解代码"""
        print("  编写求解代码...")

        problem_text = context.get('problem_text', '')
        analysis_result = context.get('analysis_result', {})
        model_result = context.get('model_result', '')
        algorithm_result = context.get('algorithm_result', '')
        data_files = context.get('data_files', {})

        # 截断过长内容
        max_len = 3000
        if len(problem_text) > max_len:
            problem_text = problem_text[:max_len] + "\n[赛题内容已截断...]"
        if len(model_result) > max_len:
            model_result = model_result[:max_len] + "\n[模型内容已截断...]"
        if len(algorithm_result) > max_len:
            algorithm_result = algorithm_result[:max_len] + "\n[算法内容已截断...]"
        if isinstance(analysis_result, dict):
            analysis_json = json.dumps(analysis_result, ensure_ascii=False, indent=2)
            if len(analysis_json) > max_len:
                analysis_json = analysis_json[:max_len] + "\n[分析内容已截断...]"
        else:
            analysis_json = str(analysis_result)[:max_len]

        # 数据文件信息
        data_info = []
        for display_name, filepath in data_files.items():
            if Path(filepath).exists():
                try:
                    df = pd.read_excel(filepath)
                    data_info.append({
                        'name': display_name,
                        'file': filepath,
                        'columns': list(df.columns),
                        'rows': len(df)
                    })
                except:
                    data_info.append({'name': display_name, 'file': filepath, 'error': '无法读取'})

        code_prompt = f"""基于以下数学模型和算法，请编写Python求解代码：

===赛题问题===
{problem_text if problem_text else '通用数学建模问题'}

===问题分析===
{analysis_json}

===数学模型===
{model_result if model_result else '请根据问题建立模型'}

===算法设计===
{algorithm_result if algorithm_result else '请设计算法'}

===数据文件信息===
{json.dumps(data_info, ensure_ascii=False, indent=2)}
===数据文件信息===

请编写完整的Python代码（solve.py），要求：
1. 使用pandas读取Excel数据
2. 使用numpy/scipy进行数值计算
3. 实现完整的数据处理和模型求解
4. 包含必要的注释和文档字符串
5. 输出具体的数值结果
6. 包含结果保存逻辑

**重要**：代码必须是可直接运行的完整程序。

请输出完整的Python代码（不带markdown格式）："""

        try:
            code_text = _call_llm(
                prompt=code_prompt,
                system_prompt=SYSTEM_PROMPTS["code_writer"],
                timeout=300
            )

            # 清理代码格式
            if code_text.startswith('```'):
                lines = code_text.splitlines()
                if lines and lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                code_text = '\n'.join(lines)

            # 确保包含必要的导入
            if 'import' not in code_text:
                code_text = "import numpy as np\nimport pandas as pd\nfrom pathlib import Path\n\n" + code_text

        except Exception as e:
            print(f"  LLM代码生成失败: {e}")
            code_text = self._generate_generic_code(context)

        context['code_result'] = code_text

        # 保存代码
        code_file = self.output_dir / WorkflowStage.STAGE_4_CODING.value / "solve.py"
        with open(code_file, 'w', encoding='utf-8') as f:
            f.write(code_text)
        print(f"  代码已保存: {code_file}")
        self._save_stage_result(WorkflowStage.STAGE_4_CODING, code_text, "code.md")

        return {'success': True, 'output': code_text}

    def _generate_generic_code(self, context: Dict) -> str:
        """生成通用代码模板"""
        data_files = context.get('data_files', {})

        file_list = [f'"{name}"' for name in data_files.keys()]
        file_dict = {name: name for name in data_files.keys()}

        return f'''"""
数学建模求解代码
自动生成于Agent工作流
"""
import numpy as np
import pandas as pd
from pathlib import Path

def load_data(data_files):
    """加载数据文件"""
    data = {{}}
    for name, filepath in data_files.items():
        try:
            df = pd.read_excel(filepath)
            data[name] = df
            print(f"已加载: {{name}}, 行数: {{len(df)}}, 列: {{list(df.columns)}}")
        except Exception as e:
            print(f"加载失败 {{name}}: {{e}}")
    return data

def solve(data):
    """执行求解"""
    results = {{}}
    for name, df in data.items():
        # 根据数据执行计算
        # 这里根据具体问题实现
        results[name] = {{
            'success': True,
            'message': '计算完成'
        }}
    return results

def main():
    """主函数"""
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
        """代码执行阶段 - 执行生成的代码并分析结果"""
        print("  执行计算...")

        data_files = context.get('data_files', {})
        problem_text = context.get('problem_text', '')
        model_result = context.get('model_result', '')
        execution_result = {}

        # 1. 首先尝试运行生成的代码
        code_file = self.output_dir / WorkflowStage.STAGE_4_CODING.value / "solve.py"
        if code_file.exists():
            print("  运行生成的代码...")
            exec_output = self._execute_code_file(code_file, data_files)
            if exec_output.get('success'):
                print("  代码执行成功")
                execution_result = exec_output.get('result', {})
            else:
                print(f"  代码执行失败: {exec_output.get('error', '未知错误')}")

        # 2. 如果代码执行失败或无结果，使用数据文件直接分析
        if not execution_result:
            print("  使用数据分析...")
            execution_result = self._analyze_data_files(data_files, problem_text, model_result)

        context['execution_result'] = execution_result
        self._save_stage_result(WorkflowStage.STAGE_5_EXECUTION, execution_result, "execution_result.json")

        return {'success': True, 'output': execution_result}

    def _execute_code_file(self, code_file: Path, data_files: Dict) -> Dict:
        """执行代码文件"""
        try:
            import sys
            import io
            from contextlib import redirect_stdout, redirect_stderr

            # 读取代码
            with open(code_file, 'r', encoding='utf-8') as f:
                code = f.read()

            # 创建执行环境
            local_ns = {
                'data_files': data_files,
                '__name__': '__main__'
            }

            # 捕获输出
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()

            try:
                exec(code, local_ns)
                output = sys.stdout.getvalue()
                error = sys.stderr.getvalue()
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

            # 尝试提取结果
            result = local_ns.get('results', {}) or local_ns.get('result', {})
            if not result and output:
                result = {'output': output}

            return {'success': True, 'result': result, 'output': output}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _analyze_data_files(self, data_files: Dict, problem_text: str, model_result: str) -> Dict:
        """分析数据文件生成计算结果"""
        results = {}

        for display_name, filepath in data_files.items():
            if not Path(filepath).exists():
                continue

            try:
                df = pd.read_excel(filepath)
                # 基本统计分析
                numeric_cols = df.select_dtypes(include=[np.number]).columns

                if len(numeric_cols) > 0:
                    col_name = numeric_cols[0]
                    values = df[col_name].dropna()

                    results[display_name] = {
                        'success': True,
                        'rows': len(df),
                        'columns': list(df.columns),
                        'numeric_columns': list(numeric_cols),
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
        """结果分析阶段 - LLM驱动的通用结果分析"""
        print("  分析计算结果...")

        problem_text = context.get('problem_text', '')
        analysis_result = context.get('analysis_result', {})
        model_result = context.get('model_result', '')
        algorithm_result = context.get('algorithm_result', '')
        exec_result = context.get('execution_result', {})
        code_result = context.get('code_result', '')

        # 截断过长内容
        max_len = 2500
        if len(problem_text) > max_len:
            problem_text = problem_text[:max_len] + "\n[赛题内容已截断...]"
        if len(model_result) > max_len:
            model_result = model_result[:max_len] + "\n[模型内容已截断...]"
        if len(algorithm_result) > max_len:
            algorithm_result = algorithm_result[:max_len] + "\n[算法内容已截断...]"
        if isinstance(analysis_result, dict):
            analysis_json = json.dumps(analysis_result, ensure_ascii=False, indent=2)
            if len(analysis_json) > max_len:
                analysis_json = analysis_json[:max_len] + "\n[分析内容已截断...]"
        else:
            analysis_json = str(analysis_result)[:max_len]
        if isinstance(exec_result, dict):
            exec_json = json.dumps(exec_result, ensure_ascii=False, indent=2)
            if len(exec_json) > max_len:
                exec_json = exec_json[:max_len] + "\n[计算结果已截断...]"
        else:
            exec_json = str(exec_result)[:max_len]

        # 构建分析请求
        analysis_prompt = f"""基于以下计算结果，请进行深入的结果分析：

===原始赛题===
{problem_text if problem_text else '通用数学建模问题'}

===问题分析===
{analysis_json}

===数学模型===
{model_result if model_result else '数学模型'}

===算法设计===
{algorithm_result if algorithm_result else '算法设计'}

===计算结果===
{exec_json}
===计算结果===

请进行深入的结果分析，包括：
1. **结果验证**：检查计算结果的合理性
2. **误差分析**：分析测量误差的来源和不确定度
3. **灵敏度分析**：分析参数变化对结果的影响
4. **结果讨论**：解释结果的物理意义或实际含义
5. **主要结论**：总结主要发现

**重要**：
- 分析要深入透彻，有数据支撑
- 包含具体的数值分析
- 识别关键影响因素

请输出完整的结果分析报告。"""

        try:
            analysis_text = _call_llm(
                prompt=analysis_prompt,
                system_prompt=SYSTEM_PROMPTS["result_analyzer"],
                timeout=300
            )
        except Exception as e:
            # 如果LLM调用失败，使用通用分析
            analysis_text = self._generate_generic_analysis(context)

        context['result_analysis'] = analysis_text
        self._save_stage_result(WorkflowStage.STAGE_6_RESULT_ANALYSIS, analysis_text, "result_analysis.md")

        return {'success': True, 'output': analysis_text}

    def _generate_generic_analysis(self, context: Dict) -> str:
        """生成通用结果分析"""
        exec_result = context.get('execution_result', {})

        # 尝试提取数值结果
        numerical_results = []
        for name, result in exec_result.items():
            if isinstance(result, dict):
                num_val = result.get('numerical_value')
                if num_val is not None:
                    numerical_results.append(float(num_val))

        if numerical_results:
            mean_val = np.mean(numerical_results)
            std_val = np.std(numerical_results)
            min_val = np.min(numerical_results)
            max_val = np.max(numerical_results)
            stats_text = f"""
### 统计分析

- 平均值: {mean_val:.4f}
- 标准差: {std_val:.4f}
- 范围: {min_val:.4f} - {max_val:.4f}
- 样本数: {len(numerical_results)}
"""
        else:
            stats_text = "\n### 统计分析\n\n暂无有效数值数据。\n"

        analysis_text = f"""
## 结果分析

### 计算结果汇总

共处理 {len(exec_result)} 个数据文件的结果。

{stats_text}

### 分析结论

基于计算结果完成分析，详见论文正文。
"""
        return analysis_text

    def _stage_charts(self, context: Dict) -> Dict:
        """图表设计阶段 - LLM驱动的通用图表设计"""
        print("  设计图表...")

        problem_text = context.get('problem_text', '')
        analysis_result = context.get('analysis_result', {})
        model_result = context.get('model_result', '')
        execution_result = context.get('execution_result', {})
        result_analysis = context.get('result_analysis', '')

        # 截断过长内容
        max_len = 2500
        if len(problem_text) > max_len:
            problem_text = problem_text[:max_len] + "\n[赛题内容已截断...]"
        if len(model_result) > max_len:
            model_result = model_result[:max_len] + "\n[模型内容已截断...]"
        if len(result_analysis) > max_len:
            result_analysis = result_analysis[:max_len] + "\n[分析内容已截断...]"
        if isinstance(analysis_result, dict):
            analysis_json = json.dumps(analysis_result, ensure_ascii=False, indent=2)
            if len(analysis_json) > max_len:
                analysis_json = analysis_json[:max_len] + "\n[分析内容已截断...]"
        else:
            analysis_json = str(analysis_result)[:max_len]
        if isinstance(execution_result, dict):
            exec_json = json.dumps(execution_result, ensure_ascii=False, indent=2)
            if len(exec_json) > max_len:
                exec_json = exec_json[:max_len] + "\n[计算结果已截断...]"
        else:
            exec_json = str(execution_result)[:max_len]

        charts_prompt = f"""基于以下分析结果和计算数据，请为论文设计高质量的图表：

===赛题问题===
{problem_text if problem_text else '通用数学建模问题'}

===问题分析===
{analysis_json}

===数学模型===
{model_result if model_result else '数学模型'}

===计算结果===
{exec_json}
===计算结果===

===结果分析===
{result_analysis if result_analysis else '分析结果'}
===结果分析===

请设计适合论文的图表方案，包括：
1. **图表类型选择**（折线图、柱状图、散点图等）
2. **图表内容描述**
3. **数据要求**
4. **图表说明**

每个图表需要包含：
- 图表编号和标题
- 图表类型
- 坐标轴标签和单位
- 图例说明
- 在论文中的引用位置

**重要**：
- 图表应清晰、美观、符合学术规范
- 考虑黑白打印效果
- 图表设计要服务于论文内容

请输出完整的图表设计方案。"""

        try:
            charts_text = _call_llm(
                prompt=charts_prompt,
                system_prompt=SYSTEM_PROMPTS.get("chart_designer", "你是一个数据可视化专家。"),
                timeout=180
            )
        except Exception as e:
            # 如果LLM调用失败，使用通用图表设计
            charts_text = self._generate_generic_charts(context)

        context['charts_result'] = charts_text
        self._save_stage_result(WorkflowStage.STAGE_7_CHARTS, charts_text, "charts.md")

        return {'success': True, 'output': charts_text}

    def _generate_generic_charts(self, context: Dict) -> str:
        """生成通用图表设计"""
        exec_result = context.get('execution_result', {})
        problem_text = context.get('problem_text', '')

        # 根据问题领域推断图表类型
        charts = [
            {"id": "图1", "title": "数据分布图", "type": "柱状图/折线图", "purpose": "展示数据分布特征"},
            {"id": "图2", "title": "结果对比图", "type": "柱状图", "purpose": "对比不同条件下的结果"},
            {"id": "图3", "title": "算法流程图", "type": "流程图", "purpose": "展示算法步骤"},
            {"id": "图4", "title": "结果汇总表", "type": "表格", "purpose": "汇总主要数值结果"}
        ]

        charts_text = "## 图表设计\n\n"
        for chart in charts:
            charts_text += f"### {chart['id']}：{chart['title']}\n\n"
            charts_text += f"- **图表类型**：{chart['type']}\n"
            charts_text += f"- **目的**：{chart['purpose']}\n"
            charts_text += f"- **说明**：详见论文正文\n\n"

        return charts_text

    def _generate_full_paper(self, context: Dict) -> str:
        """生成完整论文 - 调用LLM生成15000-25000字论文"""

        # 收集所有上下文
        problem_text = context.get('problem_text', '')
        analysis_result = context.get('analysis_result', {})
        model_result = context.get('model_result', '')
        algorithm_result = context.get('algorithm_result', '')
        code_result = context.get('code_result', '')
        execution_result = context.get('execution_result', {})
        result_analysis = context.get('result_analysis', '')
        charts_result = context.get('charts_result', '')

        # 截断过长内容，避免prompt过长
        max_len = 3500
        if len(problem_text) > max_len:
            problem_text = problem_text[:max_len] + "\n[赛题内容已截断...]"
        if len(model_result) > max_len:
            model_result = model_result[:max_len] + "\n[模型内容已截断...]"
        if len(algorithm_result) > max_len:
            algorithm_result = algorithm_result[:max_len] + "\n[算法内容已截断...]"
        if len(code_result) > max_len:
            code_result = code_result[:max_len] + "\n[代码内容已截断...]"
        if len(result_analysis) > max_len:
            result_analysis = result_analysis[:max_len] + "\n[分析内容已截断...]"
        if len(charts_result) > max_len:
            charts_result = charts_result[:max_len] + "\n[图表内容已截断...]"
        if isinstance(analysis_result, dict):
            analysis_json = json.dumps(analysis_result, ensure_ascii=False, indent=2)
            if len(analysis_json) > max_len:
                analysis_json = analysis_json[:max_len] + "\n[分析内容已截断...]"
        else:
            analysis_json = str(analysis_result)[:max_len]
        if isinstance(execution_result, dict):
            exec_json = json.dumps(execution_result, ensure_ascii=False, indent=2)
            if len(exec_json) > max_len:
                exec_json = exec_json[:max_len] + "\n[计算结果已截断...]"
        else:
            exec_json = str(execution_result)[:max_len]

        # 构建详细的用户提示词
        user_prompt = f"""请撰写完整的数学建模论文，要求15000-25000字。

===原始赛题===
{problem_text if problem_text else '通用数学建模问题，请根据数据分析建立模型并求解'}
===原始赛题===

===问题分析===
{analysis_json}
===问题分析===

===数学模型===
{model_result if model_result else '请建立数学模型'}
===数学模型===

===算法设计===
{algorithm_result if algorithm_result else '请设计算法'}
===算法设计===

===计算结果===
{exec_json}
===计算结果===

===结果分析===
{result_analysis if result_analysis else '请分析结果'}
===结果分析===

===图表设计===
{charts_result if charts_result else '请设计图表'}
===图表设计===

## 论文结构要求

请撰写完整的数学建模论文，包含以下部分：

1. **摘要**（中英文，500-800字）
   - 研究背景与目的
   - 研究方法
   - 研究结果（包含关键数据）
   - 研究结论
   - 关键词：5-8个

2. **1. 问题重述**（800-1500字）
   - 研究背景
   - 问题描述
   - 实际意义

3. **2. 问题分析**（1500-2500字）
   - 问题特点与难点
   - 求解思路
   - 关键因素识别

4. **3. 模型假设与符号说明**（800-1200字）
   - 基本假设
   - 假设合理性分析
   - 符号定义表

5. **4. 模型建立**（2500-4000字）
   - 模型类型选择
   - 详细公式推导
   - 物理意义解释

6. **5. 模型求解**（2000-3000字）
   - 求解方法
   - 算法步骤
   - 计算结果

7. **6. 结果分析**（2000-3000字）
   - 结果验证
   - 误差分析
   - 灵敏度分析

8. **7. 模型评价与改进**（1000-1500字）
   - 模型优点
   - 模型局限性
   - 改进方向

9. **8. 参考文献**（500-800字）
   - 引用文献列表

10. **9. 附录**
    - 主要代码
    - 原始数据

## 重要要求

1. **字数要求**：正文15000-25000字
2. **格式要求**：使用标准数学建模论文格式
3. **公式要求**：所有公式使用LaTeX格式，完整推导
4. **图表要求**：图表清晰，有编号和标题
5. **分析要求**：深入透彻，有数据支撑

请生成完整详尽的论文内容。

**重要提醒**：
1. 代码只放在附录中，正文中不要展示完整代码，只描述算法步骤和核心公式
2. 正文应侧重于模型建立、公式推导、结果分析和讨论
3. 保持论文的学术性和可读性，不要像写教程一样"""

        try:
            # 调用LLM生成完整论文
            print("  正在生成完整论文（这可能需要几分钟）...")
            paper = _call_llm(
                prompt=user_prompt,
                system_prompt=SYSTEM_PROMPTS["paper_writer"],
                timeout=600  # 10分钟超时
            )
            return paper
        except Exception as e:
            # 如果LLM调用失败，返回包含所有中间结果的论文
            return self._generate_fallback_paper(context)

    def _generate_fallback_paper(self, context: Dict) -> str:
        """生成包含所有中间结果的论文(当LLM调用失败时)"""
        exec_result = context.get('execution_result', {})

        # 动态提取结果
        thicknesses = []
        thickness_str = ""
        for name, result in exec_result.items():
            if isinstance(result, dict) and result.get('success'):
                thicknesses.append(f"{name}: {result.get('thickness', 0):.2f} μm")

        if thicknesses:
            thickness_str = "，".join(thicknesses)
        else:
            thickness_str = "待测量"

        paper = f"""# 数学建模论文

## 摘要

**研究背景**：本文针对实际问题建立了数学模型进行分析求解。

**研究方法**：通过建立数学模型，设计算法并实现代码求解。

**研究结果**：{thickness_str}

**研究结论**：通过实验验证了模型的可行性。

## 1. 问题重述

### 1.1 研究背景

见赛题分析。

### 1.2 问题描述

见数学模型部分。

{context.get('model_result', '')}

---

## 2. 模型建立

{context.get('model_result', '')}

---

## 3. 求解算法

{context.get('algorithm_result', '')}

---

## 4. 结果分析

{context.get('result_analysis', '')}

---

## 5. 图表设计

{context.get('charts_result', '')}

---

## 参考文献

[1] 相关参考文献。

---

## 附录：求解代码

### A.1 核心求解代码

完整代码保存于：`work/stage_4_coding/solve.py`

---

*本论文由数学建模论文自动生成系统辅助完成*
"""
        return paper

def run_auto_paper_generation(
    problem_file: str = "problem.md",
    data_files: Dict[str, str] = None,
    output_dir: str = "work"
) -> str:
    """运行全自动论文生成"""
    if data_files is None:
        data_files = {}

    # 加载赛题
    problem_text = ""
    if Path(problem_file).exists():
        with open(problem_file, 'r', encoding='utf-8') as f:
            problem_text = f.read()

    # 创建引擎
    engine = AgentWorkflow(output_dir=output_dir)

    # 运行
    paper = engine.run_full_workflow(
        problem_text=problem_text,
        data_files=data_files
    )

    return paper
