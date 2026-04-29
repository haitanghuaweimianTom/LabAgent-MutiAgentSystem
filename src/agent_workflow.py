"""
统一工作流引擎 v2.0
===================

融合 LLM-MM-Agent + cherry-studio + Claude CLI 的统一架构：
- Coordinator: DAG调度与黑板内存（LLM-MM-Agent）
- CritiqueEngine: Actor-Critic-Improvement 质量保障（LLM-MM-Agent）
- KnowledgeBase: RAG 知识增强（cherry-studio）
- DocumentLoader: 多格式文档处理（cherry-studio）
- CodeExecutor: Claude CLI 代码生成与执行
- PaperGenerator: 大纲驱动的论文章节生成（LLM-MM-Agent）
- PaperTemplate: 通用论文模板系统

核心改进：
1. 每章节完整生成、内容充实、可直接交付
2. 代码任务明确使用 Claude CLI
3. 数据分析利用 KnowledgeBase + DocumentLoader
4. 支持多种论文模板（数学建模/课程作业/金融分析）
"""

import os
import sys
import json
import time
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

# =============================================================================
# 多 LLM 提供商支持
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

    try:
        if os.getenv("OPENAI_API_KEY"):
            manager = get_provider_manager()
            manager.register(ProviderType.OPENAI)
            _llm_provider_instance = manager
            print(f"[LLM] 使用 OpenAI Provider (model={manager.get().config.model})")
        elif os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
            manager = get_provider_manager()
            config = ProviderConfig.from_env(ProviderType.ANTHROPIC)
            if not config.api_key and os.getenv("ANTHROPIC_AUTH_TOKEN"):
                config.api_key = os.getenv("ANTHROPIC_AUTH_TOKEN")
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
    return found


def _call_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: str = "sonnet",
    timeout: int = 600,
    max_retries: int = 3,
    retry_wait: int = 5
) -> str:
    """
    调用 LLM 生成内容
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
# 统一工作流引擎
# =============================================================================

from src.workflow import (
    Coordinator,
    DependencyType,
    MathModelingTemplate,
    CourseworkTemplate,
    FinancialAnalysisTemplate,
    get_template,
    CritiqueEngine,
    CodeExecutor,
    PaperGenerator,
)
from src.document_processing import DocumentLoader


try:
    from src.knowledge import KnowledgeBase
    _KNOWLEDGE_AVAILABLE = True
except ImportError:
    _KNOWLEDGE_AVAILABLE = False


class UnifiedWorkflow:
    """
    统一工作流引擎 v2.0

    四阶段架构（借鉴 LLM-MM-Agent）：
    Stage 1: Problem Analysis - 问题分析 + DAG构建
    Stage 2: Mathematical Modeling - 数学建模（按DAG拓扑序）
    Stage 3: Computational Solving - 计算求解（Claude CLI代码）
    Stage 4: Paper Generation - 论文生成（大纲驱动 + 相关性过滤）
    """

    def __init__(
        self,
        output_dir: str = "work",
        template_name: str = "math_modeling",
        use_knowledge_base: bool = True,
        use_critique: bool = True,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.template_name = template_name
        self.use_critique = use_critique
        self.use_knowledge_base = use_knowledge_base and _KNOWLEDGE_AVAILABLE

        # 初始化各组件
        self.coordinator = Coordinator()
        self.critique_engine = CritiqueEngine(_call_llm)
        self.code_executor = CodeExecutor(
            call_llm=_call_llm,
            output_dir=str(self.output_dir),
        )
        self.paper_generator = PaperGenerator(
            call_llm=_call_llm,
            template=get_template(template_name),
            output_dir=str(self.output_dir),
        )
        self.document_loader = DocumentLoader()
        self.knowledge_base = KnowledgeBase() if self.use_knowledge_base else None

        # 全局上下文
        self.context: Dict[str, Any] = {}
        self.problem_text = ""
        self.data_files: Dict[str, str] = {}

    def run_full_workflow(
        self,
        problem_text: str,
        data_files: Dict[str, str],
        problem_name: str = "数学建模问题",
    ) -> str:
        """运行完整工作流"""
        print("\n" + "=" * 70)
        print("数学建模论文自动生成系统 v2.0")
        print(f"模板: {self.template_name}")
        print("=" * 70)

        self.problem_text = problem_text
        self.data_files = data_files
        self.context["problem_text"] = problem_text
        self.context["data_files"] = data_files

        # Stage 1: 问题分析
        print(f"\n{'='*60}")
        print("Stage 1: 问题分析")
        print(f"{'='*60}")
        analysis = self._stage_problem_analysis()
        self.context["analysis"] = analysis

        # Stage 2: 数学建模（按DAG拓扑序）
        print(f"\n{'='*60}")
        print("Stage 2: 数学建模")
        print(f"{'='*60}")
        modeling = self._stage_mathematical_modeling(analysis)
        self.context["modeling"] = modeling

        # Stage 3: 计算求解（Claude CLI代码）
        print(f"\n{'='*60}")
        print("Stage 3: 计算求解")
        print(f"{'='*60}")
        solving = self._stage_computational_solving(modeling)
        self.context["execution_result"] = solving.get("execution_result", {})
        self.context["code"] = solving.get("code", "")
        self.context["result_analysis"] = solving.get("interpretation", "")

        # Stage 4: 论文生成
        print(f"\n{'='*60}")
        print("Stage 4: 论文生成")
        print(f"{'='*60}")
        paper = self._stage_paper_generation()

        # 保存结果
        paper_path = self.output_dir / "final" / "MathModeling_Paper.md"
        paper_path.parent.mkdir(parents=True, exist_ok=True)
        paper_path.write_text(paper, encoding="utf-8")

        # 字数统计
        chinese_chars = len(re.findall(r'[一-鿿]', paper))
        print(f"\n{'='*60}")
        print("论文生成完成")
        print(f"{'='*60}")
        print(f"论文文件: {paper_path}")
        print(f"总字符数: {len(paper)}")
        print(f"中文字数: {chinese_chars}")

        # 导出解决方案
        solution_path = self.output_dir / "final" / "solution.json"
        self.coordinator.export_solution(solution_path)

        return paper

    # ========================================================================
    # Stage 1: 问题分析
    # ========================================================================

    def _stage_problem_analysis(self) -> Dict[str, Any]:
        """
        问题分析阶段

        借鉴 LLM-MM-Agent 的反思链设计 + Critique-Improvement
        """
        print("  分析问题并构建DAG...")

        # 加载数据文件摘要
        data_descriptions = self._load_data_descriptions()
        self.context["data_descriptions"] = data_descriptions

        # 注册知识库（如果有相关文档）
        if self.knowledge_base and data_descriptions:
            for name, desc in data_descriptions.items():
                self.knowledge_base.add_document(
                    title=f"数据文件: {name}",
                    content=desc,
                    metadata={"type": "data"},
                )

        # Prompt: 反思链设计（借鉴 LLM-MM-Agent PROBLEM_ANALYSIS_PROMPT）
        prompt = f"""请对以下数学建模问题进行深度分析。

【赛题】
{self.problem_text[:4000]}

【数据文件描述】
{chr(10).join(data_descriptions.values())[:2000]}

要求：
1. 识别问题的核心组件和它们之间的依赖关系
2. 分析问题的动态特性（时间演化、空间分布等）
3. 从多个视角审视问题（数学视角、物理视角、工程视角）
4. 识别关键假设和潜在的不确定性
5. 将问题分解为可管理的子任务

输出严格的JSON格式：
{{
  "background": "问题背景概述（300字）",
  "sub_problems": [
    {{
      "id": "task_1",
      "description": "子任务描述",
      "objective": "任务目标",
      "key_constraints": ["约束1", "约束2"],
      "suggested_methods": ["建议方法1", "建议方法2"]
    }}
  ],
  "key_assumptions": ["假设1", "假设2"],
  "data_dependencies": {{"task_1": ["数据文件1"]}},
  "solution_approach": "整体解决思路（500字）"
}}"""

        # 生成 + Critique-Improvement
        print("  生成初始分析...")
        result = _call_llm(prompt, "你是一位数学建模专家，擅长深度问题分析。")

        analysis = self._parse_json_safely(result, self._default_analysis())

        if self.use_critique:
            print("  启动Critique-Improvement循环...")
            analysis_text = json.dumps(analysis, ensure_ascii=False, indent=2)
            improved = self.critique_engine.critique_and_improve(
                content=analysis_text,
                content_type="analysis",
                context=self.problem_text[:2000],
                max_iterations=1,
                score_threshold=7.5,
            )
            analysis = self._parse_json_safely(improved, analysis)

        # 构建DAG
        sub_problems = analysis.get("sub_problems", [])
        for i, sp in enumerate(sub_problems):
            task_id = sp.get("id", f"task_{i+1}")
            deps = {}
            # 简单的顺序依赖：后面的任务依赖前面的
            if i > 0:
                prev_id = sub_problems[i-1].get("id", f"task_{i}")
                deps[prev_id] = [DependencyType.STRUCTURAL, DependencyType.DATA]
            self.coordinator.register_task(
                task_id=task_id,
                description=sp.get("description", ""),
                dependencies=deps,
            )

        self.coordinator.analyze_dependencies()
        self.context["sub_problems"] = sub_problems

        # 保存
        self._save_json("stage_1_analysis/analysis.json", analysis)
        return analysis

    def _load_data_descriptions(self) -> Dict[str, str]:
        """加载数据文件描述"""
        descriptions = {}
        for name, filepath in self.data_files.items():
            path = Path(filepath)
            if not path.exists():
                descriptions[name] = f"{name}: 文件不存在"
                continue

            try:
                result = self.document_loader.load(filepath)
                if result.success and result.document:
                    desc = result.document.text[:1500]
                    descriptions[name] = f"【{name}】\n{desc}\n"
                    # 添加到知识库
                    if self.knowledge_base:
                        self.knowledge_base.add_document(
                            title=f"数据: {name}",
                            content=desc,
                            source=filepath,
                            metadata={"type": "data_file", "filename": name},
                        )
                else:
                    descriptions[name] = f"{name}: 加载失败 - {result.error}"
            except Exception as e:
                descriptions[name] = f"{name}: 错误 - {str(e)}"

        return descriptions

    # ========================================================================
    # Stage 2: 数学建模
    # ========================================================================

    def _stage_mathematical_modeling(self, analysis: Dict) -> Dict[str, Any]:
        """
        数学建模阶段 - 按DAG拓扑序执行每个子任务

        借鉴 LLM-MM-Agent：
        - 依赖上下文自动拼接
        - 方法检索增强生成
        - Actor-Critic-Improvement 循环
        """
        sub_problems = analysis.get("sub_problems", [])
        if not sub_problems:
            sub_problems = [{"id": "task_1", "description": "建立模型求解"}]

        all_formulas = []
        all_models = []

        for task_id in self.coordinator.dag_order:
            task_node = self.coordinator.tasks.get(task_id)
            if not task_node:
                continue

            print(f"\n  建模任务: {task_id} - {task_node.description[:60]}...")

            # 获取依赖上下文
            dep_context = self.coordinator.get_dependency_context(
                task_id, max_chars=3000
            )

            # 知识库检索相关方法
            kb_context = ""
            if self.knowledge_base:
                kb_results = self.knowledge_base.query_with_context(
                    task_node.description, top_k=3, max_chars=1500
                )
                if kb_results:
                    kb_context = f"【相关知识】\n{kb_results}\n\n"

            # 1. 任务分析
            analysis_prompt = f"""对以下子任务进行深入分析：

任务描述: {task_node.description}

整体问题背景:
{self.problem_text[:2000]}

{dep_context}

{kb_context}

请分析：
1. 该任务的核心数学结构
2. 适合的建模方法及选择理由
3. 关键变量和参数
4. 与前置任务的衔接点

输出详细分析（至少800字）。"""

            task_analysis = _call_llm(
                analysis_prompt,
                "你是数学建模专家，擅长将实际问题抽象为数学结构。"
            )

            # 2. 公式生成（Actor）
            formulas_prompt = f"""基于以下分析，建立完整的数学模型。

任务分析:
{task_analysis[:1500]}

要求：
1. 明确定义所有变量和参数（用表格形式）
2. 建立核心数学公式（LaTeX格式），公式必须编号
3. 说明每个公式的物理/数学意义
4. 列出模型假设及其合理性
5. 讨论模型的适用条件和局限性

输出完整的建模过程（至少1500字）。"""

            formulas = _call_llm(
                formulas_prompt,
                "你是数学建模专家，擅长严谨的形式化建模。"
            )

            # 3. Critique-Improvement
            if self.use_critique:
                print(f"    对公式进行Critique-Improvement...")
                formulas = self.critique_engine.critique_and_improve(
                    content=formulas,
                    content_type="modeling",
                    context=f"任务: {task_node.description}\n{self.problem_text[:1000]}",
                    max_iterations=1,
                    score_threshold=7.5,
                    min_chars=1500,
                )

            # 保存结果
            self.coordinator.save_task_result(
                task_id, {"analysis": task_analysis, "formulas": formulas}, key="modeling"
            )
            all_formulas.append(formulas)
            all_models.append(task_analysis)

        modeling_result = {
            "formulas": "\n\n".join(all_formulas),
            "models": "\n\n".join(all_models),
        }

        self.context["formulas"] = modeling_result["formulas"]
        self._save_json("stage_2_modeling/modeling.json", modeling_result)
        self._save_text("stage_2_modeling/formulas.md", modeling_result["formulas"])

        return modeling_result

    # ========================================================================
    # Stage 3: 计算求解
    # ========================================================================

    def _stage_computational_solving(self, modeling: Dict) -> Dict[str, Any]:
        """
        计算求解阶段

        明确使用 Claude CLI 生成代码
        使用 CodeExecutor 执行与调试
        """
        print("  生成求解代码...")

        formulas = modeling.get("formulas", "")
        algorithm_desc = self._design_algorithm(modeling)
        self.context["algorithm"] = algorithm_desc

        # 构建代码生成 Prompt
        code_prompt = f"""请编写完整的Python求解代码，解决以下数学建模问题。

【数学模型】
{formulas[:3000]}

【算法设计】
{algorithm_desc[:2000]}

【赛题】
{self.problem_text[:2000]}

【数据文件】
{json.dumps(self.data_files, ensure_ascii=False, indent=2)}

硬性要求：
1. 代码开头必须是 import 语句，不要有任何中文说明
2. 代码必须能够读取上述数据文件（使用 pandas 读取 Excel）
3. 代码运行后必须在 {self.output_dir}/execution/results.json 写入结构化结果
4. 代码中必须包含 main() 函数
5. 所有数值结果使用 Python 原生 float/int
6. 不得使用 input() 等交互式函数
7. 结果必须包含具体的数值，不能是空值或占位符

输出纯Python代码，不要包含 markdown 代码块标记。"""

        # 使用 CodeExecutor（明确使用 Claude CLI）
        print("  调用 Claude CLI 生成代码...")
        result = self.code_executor.generate_and_run(
            prompt=code_prompt,
            system_prompt="你是Python编程专家，擅长数值计算和数据处理。",
            data_files=self.data_files,
            filename="solve.py",
            use_claude_cli=True,
        )

        code = result.get("code", "")
        execution_result = result.get("execution_result", {})

        # 结果解读
        print("  解读计算结果...")
        interpretation = self._interpret_results(execution_result, modeling)

        # 保存
        self._save_text("stage_4_coding/solve.py", code)
        self._save_json("stage_5_execution/execution_result.json", execution_result)
        self._save_text("stage_6_result_analysis/interpretation.md", interpretation)

        return {
            "code": code,
            "execution_result": execution_result,
            "interpretation": interpretation,
            "success": result.get("success", False),
        }

    def _design_algorithm(self, modeling: Dict) -> str:
        """设计求解算法"""
        formulas = modeling.get("formulas", "")

        prompt = f"""基于以下数学模型，设计详细的求解算法。

【数学模型】
{formulas[:3000]}

要求：
1. 选择合适的数值方法或优化算法
2. 给出详细的算法步骤（伪代码或分步说明）
3. 分析算法的时间复杂度和空间复杂度
4. 讨论算法的收敛性和稳定性
5. 设置关键参数及其选择依据

输出至少1000字的算法设计文档。"""

        return _call_llm(prompt, "你是算法设计专家。")

    def _interpret_results(self, execution_result: Dict, modeling: Dict) -> str:
        """解读计算结果"""
        result_text = json.dumps(execution_result, ensure_ascii=False, indent=2)

        prompt = f"""请对以下计算结果进行专业解读。

【计算结果】
{result_text[:3000]}

【数学模型】
{modeling.get('formulas', '')[:1500]}

要求：
1. 总结主要数值结果
2. 分析结果的合理性和物理意义
3. 进行误差分析（如有可能）
4. 讨论结果的稳健性
5. 给出明确的研究结论

输出至少1500字的详细解读。"""

        return _call_llm(prompt, "你是数据分析专家。")

    # ========================================================================
    # Stage 4: 论文生成
    # ========================================================================

    def _stage_paper_generation(self) -> str:
        """
        论文生成阶段

        使用 PaperGenerator：
        - 根据模板类型选择大纲
        - 逐章生成，每章完整详实
        - 相关性过滤，避免上下文过长
        - Critique-Improvement 质量保障
        """
        # 生成图表
        print("  生成图表...")
        charts = self._generate_charts()
        self.context["charts"] = charts

        # 使用 PaperGenerator 生成论文
        paper = self.paper_generator.generate_paper(
            context=self.context,
            use_critique=self.use_critique,
        )

        # 保存
        self.paper_generator.save_paper(paper, "MathModeling_Paper.md")

        return paper

    def _generate_charts(self) -> str:
        """生成论文图表"""
        charts_dir = self.output_dir / "stage_7_charts"
        charts_dir.mkdir(parents=True, exist_ok=True)

        execution_result = self.context.get("execution_result", {})

        # 使用 matplotlib 生成基础图表
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            plt.rcParams['font.sans-serif'] = [
                'Noto Sans CJK SC', 'SimHei', 'DejaVu Sans'
            ]
            plt.rcParams['axes.unicode_minus'] = False

            chart_count = 0

            # 如果有多个子问题结果，生成对比图
            if isinstance(execution_result, dict) and len(execution_result) > 0:
                numeric_keys = []
                numeric_vals = []
                for k, v in execution_result.items():
                    if isinstance(v, dict) and 'result' in v:
                        try:
                            val = float(v['result'])
                            numeric_keys.append(str(k))
                            numeric_vals.append(val)
                        except:
                            pass

                if len(numeric_keys) > 1:
                    fig, ax = plt.subplots(figsize=(10, 6))
                    ax.bar(numeric_keys, numeric_vals, color='steelblue')
                    ax.set_xlabel('问题', fontsize=12)
                    ax.set_ylabel('结果值', fontsize=12)
                    ax.set_title('各问题计算结果对比', fontsize=14)
                    plt.tight_layout()
                    fig.savefig(str(charts_dir / 'fig_01_comparison.png'), dpi=300)
                    plt.close(fig)
                    chart_count += 1

            print(f"  生成 {chart_count} 个图表")
        except ImportError:
            print("  matplotlib 未安装，跳过图表生成")

        return f"图表保存于: {charts_dir}"

    # ========================================================================
    # 工具方法
    # ========================================================================

    def _save_json(self, rel_path: str, data: Any):
        """保存JSON文件"""
        path = self.output_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_text(self, rel_path: str, text: str):
        """保存文本文件"""
        path = self.output_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _parse_json_safely(self, text: str, default: Any) -> Any:
        """安全解析JSON"""
        try:
            # 尝试提取 JSON 块
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(text)
        except Exception:
            return default

    def _default_analysis(self) -> Dict:
        """默认分析问题结果"""
        return {
            "background": "数学建模问题分析",
            "sub_problems": [
                {
                    "id": "task_1",
                    "description": "建立模型求解",
                    "objective": "解答问题",
                    "key_constraints": [],
                    "suggested_methods": ["数学建模方法"],
                }
            ],
            "key_assumptions": ["合理假设"],
            "data_dependencies": {},
            "solution_approach": "建立数学模型进行求解",
        }


def run_auto_paper_generation(
    problem_file: str = "problem.md",
    data_files: Dict[str, str] = None,
    output_dir: str = "work",
    template_name: str = "math_modeling",
) -> str:
    """运行全自动论文生成"""
    if data_files is None:
        data_files = {}

    problem_text = ""
    if Path(problem_file).exists():
        with open(problem_file, "r", encoding="utf-8") as f:
            problem_text = f.read()

    engine = UnifiedWorkflow(
        output_dir=output_dir,
        template_name=template_name,
    )

    return engine.run_full_workflow(
        problem_text=problem_text,
        data_files=data_files,
    )
