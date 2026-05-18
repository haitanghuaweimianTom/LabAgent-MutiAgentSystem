"""写作Agent - 生成完整CUMCM格式LaTeX论文

完全重写（v3.0）：
- 使用官方 cumcmthesis.cls 文档类
- 按照CUMCM标准格式：问题重述、问题分析、模型假设与符号说明、模型建立、模型求解、结果分析、可靠性分析、结论、参考文献
- 包含承诺书、摘要、关键词
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List
from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)


def _fmt_vars(vars_list: List) -> str:
    """格式化变量列表"""
    if not vars_list:
        return "无"
    parts = []
    for v in vars_list:
        if isinstance(v, dict):
            name = v.get("name", v.get("Name", "x"))
            desc = v.get("description", v.get("desc", ""))
            parts.append(f"${name}$({desc})" if desc else f"${name}$")
        else:
            parts.append(str(v))
    return ", ".join(parts)


def _fmt_constraints(constraints: List) -> str:
    """格式化约束条件列表"""
    if not constraints:
        return "无"
    parts = []
    for c in constraints:
        if isinstance(c, dict):
            name = c.get("name", c.get("Name", "约束"))
            expr = c.get("expression", c.get("expr", ""))
            parts.append(f"{name}: ${expr}$" if expr else name)
        else:
            parts.append(str(c))
    return "; ".join(parts)


# ===== 论文模板系统提示词 =====

CUMCM_WRITER_SYSTEM = r"""你是一个专业的全国大学生数学建模竞赛（CUMCM）论文写作专家。

【评阅标准（核心目标）】
假设的合理性、建模的创造性、结果的正确性、表述的清晰性。

【论文格式要求】
严格按照以下格式生成论文，使用 cumcmthesis 文档类：
- 承诺书页（\maketitle）
- 摘要：300-500字，不超过一页
- 关键词：3-5个
- 章节：1 问题重述 → 2 问题分析 → 3 模型假设与符号说明 → 4 模型建立 → 5 模型求解 → 6 结果分析 → 7 可靠性分析 → 8 结论 → 9 参考文献
- 附录：代码

【CUMCM标准格式示例】
\section{1 问题重述}
\subsection{1.1 研究背景}
...
\subsection{1.2 问题描述}
...

\section{2 问题分析}
...

【各章节写作要求（来自韩中庚教授《数学建模竞赛论文的写作方法》）】

**摘要（重中之重）**：
- 针对每个问题，清晰说明：用了什么方法 → 建立了什么模型 → 如何求解 → 主要结果是什么 → 解决了什么问题 → 效果怎么样
- 必须包含：模型的数学归类、建模思想、算法思想、建模特点、主要数值结果
- 摘要中不要出现复杂公式和表格
- 结论必须明确具体，不能用"效果较好"等模糊表达

**问题重述**：
- 用你自己的语言重新表述问题，切忌照抄原题
- 对模糊概念和条件给出必要的澄清与说明
- 可以略微增加要研究的问题或添加限制条件（但不能降低难度）

**问题分析**：
- 相当于学术论文的引言：背景描述、研究意义、目标和现状
- 解决问题的思路、可能使用的方法、建模的过程和步骤
- 对要使用的数学方法和建模过程的适用性与合理性进行分析

**模型假设**：
- 每一条假设都要说明其必要性和合理性
- 假设必须在正文中被引用，否则评委可以质疑其合理性
- 切勿草率和随意罗列

**符号说明**：
- 宜简不宜繁，兼顾习惯与直观
- 尽量用单字母，不要用字词组合表示一个量
- 绝对避免一个符号表示不同意义的几个变量

**模型建立与求解（论文核心）**：
- 立题要反映所解决的问题和所用方法的特点，不要用"问题1的模型建立与求解"这种立题
- 建模前先说明建模方法的依据和思路
- 不要盲目追求"高大上"的方法，最简单的或许就是最好的
- 建模方法的选择、过程和表达都要明其理、讲其理
- 求解结果要明确表述，并对其正确性和实用性进行分析

**结果分析**：
- 避免直接给出表格或图形而不做任何文字解释和分析
- 数值结果必须配合文字解释，说明结果的实际含义和合理性
- 对问题的解答作定性或规律性的讨论，结论必须明确

**可靠性分析（不可或缺）**：
- 包含模型检验（准确性检验）和敏感性分析（可靠性检验）
- 即使题目未明确要求，对于工程领域的实际问题都必须做

**模型评价**：
- 从优点、缺点和创新点三方面给出实事求是的评价
- 评价要尊重事实，优点不要过于夸张，缺点不要回避

**论文系统性和连贯性**：
- 避免"问答式"八股文：问题分析→建立模型→编程求解→结果如下图（没有前因后果）
- 不要把各个子问题视为相互独立的问题，问什么答什么
- 应该围绕解决问题的主线逐步深入

【重要】
1. 论文必须是可以用 xelatex 编译的完整LaTeX代码
2. 数学公式用 equation 或 align 环境
3. 表格用 booktabs 风格（\toprule, \midrule, \bottomrule）
4. 图形标题放在图形下方
5. 参考文献使用 thebibliography 环境
6. 章节编号必须连续，不能重复或跳跃
7. 每个子问题的模型建立和求解应合并到统一章节中，使用 \subsection 区分，不要为每个子问题单独创建 \section
8. 能用初等方法解决就不用高等方法；能用简单方法就不用复杂方法；能被更多人看懂的方法就不用少数人看懂的方法

【引号使用规范（强制约束）】
LaTeX 源代码中所有引号必须严格遵守以下规则，违反将导致编译错误或排版异常：
1. 中文正文中的引用、强调、专有名词等：必须使用中文双引号 "中文内容" 和中文单引号 '中文内容'
2. 英文摘要（\begin{abstract}...\end{abstract} 中的英文部分）或纯英文段落：使用 LaTeX 原生英文引号，即开双引号用两个反引号 ``，闭双引号用两个单引号 ''；开单引号用 `，闭单引号用 '
3. 数学公式内（$...$ 或 \begin{equation}...\end{equation}）：不使用任何引号
4. 严禁在中文正文中使用 `` 或 '' 等 LaTeX 英文引号
5. 严禁使用反引号 ` 作为中文引用的开引号
6. 参考文献条目的标题、期刊名等：按 GB/T 7714 标准使用中文引号或英文引号（根据文献语言而定）

请生成完整论文JSON输出，严格按以下格式返回（必须以JSON开头和结尾，不要有任何其他文字）：
{
    "title": "论文标题（简洁准确，不超过20字，避免使用公式和符号）",
    "abstract": "摘要（300-500字，包含：方法→模型→求解→结果→结论）",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
    "latex_code": "完整LaTeX源代码（包含导言区、承诺书、摘要、正文、所有章节、参考文献、附录）",
    "sections": {
        "问题重述": "主要内容摘要",
        "问题分析": "主要内容摘要",
        "模型建立": "主要内容摘要",
        "模型求解": "主要内容摘要",
        "结果分析": "主要内容摘要",
        "可靠性分析": "主要内容摘要",
        "结论": "主要内容摘要"
    }
}"""

COURSEWORK_WRITER_SYSTEM = r"""你是一个专业的课程作业/学术报告写作专家。

【论文格式要求】
生成结构清晰、内容充实的课程作业报告，使用 article 文档类：
- 标题页（\maketitle）
- 摘要：200-400字
- 关键词：3-5个
- 章节：1 引言/研究背景 → 2 问题描述 → 3 方法与模型 → 4 实验/求解过程 → 5 结果分析 → 6 总结与展望 → 7 参考文献
- 附录：代码（如有）

【课程作业格式特点】
- 语言风格：学术但简洁，适合课程作业提交
- 篇幅：适中，不需要像竞赛论文那样冗长
- 重点：方法原理、实现过程、结果分析
- 不要求承诺书页

【写作要点】
- 摘要应包含：研究目的、使用的方法、主要结果和结论
- 问题分析相当于引言：包括背景描述、研究意义、解决思路
- 模型建立前先说明方法选择的依据和优势
- 求解结果必须配合文字解释，说明实际含义
- 模型假设要合理且在正文中被引用
- 避免"问答式"八股文，围绕解决问题的主线逐步深入

【重要】
1. 论文必须是可以用 xelatex 编译的完整LaTeX代码
2. 数学公式用 equation 或 align 环境
3. 表格用 booktabs 风格
4. 章节编号必须连续，不能重复或跳跃
5. 子问题使用 \subsection 区分，不要为每个子问题单独创建 \section
6. 能用简单方法就不用复杂方法，能被更多人看懂的方法更好

【引号使用规范（强制约束）】
LaTeX 源代码中所有引号必须严格遵守以下规则：
1. 中文正文中的引用、强调、方法名称、专有名词：必须使用中文双引号 "中文内容" 和中文单引号 '中文内容'
2. 英文摘要或纯英文段落：使用 LaTeX 原生英文引号，即开双引号 `` 和闭双引号 ''；开单引号 ` 和闭单引号 '
3. 数学公式内（$...$ 或 \begin{equation}...\end{equation}）：不使用任何引号
4. 严禁在中文正文中使用 `` 或 '' 等 LaTeX 英文引号
5. 严禁使用反引号 ` 作为中文引用的开引号
6. 参考文献条目按文献语言选择对应的引号

请生成完整论文JSON输出，严格按以下格式返回（必须以JSON开头和结尾，不要有任何其他文字）：
{
    "title": "报告标题",
    "abstract": "摘要（200-400字）",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "latex_code": "完整LaTeX源代码",
    "sections": {
        "引言": "主要内容摘要",
        "问题描述": "主要内容摘要",
        "方法与模型": "主要内容摘要",
        "实验与求解": "主要内容摘要",
        "结果分析": "主要内容摘要",
        "总结与展望": "主要内容摘要"
    }
}"""

FINANCIAL_ANALYSIS_WRITER_SYSTEM = r"""你是一个专业的金融分析报告写作专家，擅长撰写投资分析、风险评估、资产定价、量化策略等金融领域的分析报告。

【报告格式要求】
生成专业的金融分析报告，使用 article 文档类：
- 封面/标题页
- 执行摘要（Executive Summary）：200-400字
- 关键词：3-5个
- 章节结构：
  1. 投资背景与市场概述
  2. 数据描述与预处理
  3. 分析框架与方法（含模型假设）
  4. 资产/策略建模
  5. 实证分析与回测结果
  6. 风险分析（VaR、压力测试、灵敏度分析）
  7. 投资建议与结论
  8. 参考文献
- 附录：代码、数据表格

【金融分析报告特点】
- 数据驱动：大量使用图表、数据表格展示分析结果
- 风险意识：必须包含风险评估和敏感性分析
- 实用性：给出明确的投资建议或策略结论
- 专业术语：正确使用金融学术语

【写作要点】
- 执行摘要应清晰说明：数据→方法→核心结论→投资建议
- 模型建立前先说明方法选择的依据和适用性
- 实证结果必须配合文字解释，说明经济含义
- 投资建议要明确具体，不可模棱两可
- 风险分析要定量给出结果（VaR值、压力情景下的损失等）
- 模型假设要合理且在正文中被引用

【重要】
1. 报告必须是可以用 xelatex 编译的完整LaTeX代码
2. 数学公式用 equation 或 align 环境
3. 表格用 booktabs 风格
4. 必须包含数据可视化占位（如 \includegraphics[width=0.8\textwidth]{figure1}）
5. 章节编号必须连续
6. 参考文献格式规范
7. 图表不要直接给出而不做任何文字解释和分析

【引号使用规范（强制约束）】
LaTeX 源代码中所有引号必须严格遵守以下规则：
1. 中文正文中的引用、强调、金融产品名、指标名：必须使用中文双引号 "中文内容" 和中文单引号 '中文内容'
2. 英文摘要（Executive Summary）或纯英文段落：使用 LaTeX 原生英文引号，即开双引号 `` 和闭双引号 ''；开单引号 ` 和闭单引号 '
3. 数学公式内（$...$ 或 \begin{equation}...\end{equation}）：不使用任何引号
4. 严禁在中文正文中使用 `` 或 '' 等 LaTeX 英文引号
5. 严禁使用反引号 ` 作为中文引用的开引号
6. 参考文献条目按文献语言选择对应的引号

请生成完整报告JSON输出，严格按以下格式返回（必须以JSON开头和结尾，不要有任何其他文字）：
{
    "title": "报告标题（如：基于ARIMA-GARCH的原油价格预测与投资策略研究）",
    "abstract": "执行摘要（200-400字，突出数据来源、方法、核心结论和投资建议）",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "latex_code": "完整LaTeX源代码",
    "sections": {
        "投资背景": "主要内容摘要",
        "数据描述": "主要内容摘要",
        "分析框架": "主要内容摘要",
        "资产建模": "主要内容摘要",
        "实证分析": "主要内容摘要",
        "风险分析": "主要内容摘要",
        "投资建议": "主要内容摘要"
    }
}"""


@AgentFactory.register("writer_agent")
class WriterAgent(BaseAgent):
    name = "writer_agent"
    label = "写作专家"
    description = "生成完整CUMCM格式LaTeX论文"
    default_model = ""
    
    _max_tokens_override = 16000

    def get_system_prompt(self, template: str = "math_modeling") -> str:
        if template == "coursework":
            return COURSEWORK_WRITER_SYSTEM
        elif template == "financial_analysis":
            return FINANCIAL_ANALYSIS_WRITER_SYSTEM
        return CUMCM_WRITER_SYSTEM

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        problem_text = task_input.get("problem_text", context.get("problem_text", ""))
        all_results = context.get("results", {})
        section_results = context.get("section_results", [])
        sub_problems = context.get("sub_problems", [])
        analyzer_result = context.get("analyzer_result", {})
        data_result = context.get("data_result", {})
        template = context.get("template", "math_modeling")

        logger.info(f"WriterAgent generating paper (template={template}) with {len(section_results)} sections")

        # 构建详细的写作上下文
        sections_context = self._build_sections_context(
            problem_text, section_results, sub_problems, analyzer_result, data_result
        )

        if template == "coursework":
            prompt = f"""请生成课程作业格式的完整报告。

【题目/任务描述】
{problem_text}

【数据分析结果】
{self._build_data_context(data_result)}

【各子问题建模与求解结果】
{sections_context}

请生成完整报告LaTeX代码，输出严格JSON格式。"""
        elif template == "financial_analysis":
            prompt = f"""请生成金融分析专业报告的完整LaTeX代码。

【分析主题/问题】
{problem_text}

【数据分析结果】
{self._build_data_context(data_result)}

【各子问题建模与求解结果】
{sections_context}

请生成完整金融分析报告LaTeX代码，输出严格JSON格式。
注意：必须包含风险分析、投资建议等金融报告特有的章节。"""
        else:
            prompt = f"""请生成全国大学生数学建模竞赛（CUMCM）格式的完整论文。

【原始赛题】
{problem_text}

【数据分析结果】
{self._build_data_context(data_result)}

【各子问题建模与求解结果】
{sections_context}

请生成完整论文LaTeX代码，输出严格JSON格式。"""

        messages = [
            {"role": "system", "content": self.get_system_prompt(template)},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.call_llm(messages=messages)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            # 解析JSON响应
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
                result["latex_code"] = result.get("latex_code", self._generate_fallback_latex(problem_text, section_results, analyzer_result, template))
                result["generated_at"] = datetime.now().isoformat()
                logger.info(f"WriterAgent paper generated: {result.get('title', '')}")
                return result
        except Exception as e:
            logger.error(f"WriterAgent failed: {e}")

        # Fallback
        fallback_keywords = {
            "math_modeling": ["数学建模", "优化模型", "算法设计", "数据分析", "论文写作"],
            "coursework": ["课程作业", "数学模型", "数据分析", "实验报告"],
            "financial_analysis": ["金融分析", "投资策略", "风险管理", "量化模型", "资产定价"],
        }
        fallback_titles = {
            "math_modeling": "基于数学建模的论文研究",
            "coursework": "课程作业研究报告",
            "financial_analysis": "金融分析报告",
        }
        return {
            "title": fallback_titles.get(template, "基于数学建模的论文研究"),
            "abstract": "本文针对问题进行了系统研究...",
            "keywords": fallback_keywords.get(template, ["数学建模", "优化模型"]),
            "latex_code": self._generate_fallback_latex(problem_text, section_results, analyzer_result, template),
            "sections": {},
            "generated_at": datetime.now().isoformat(),
        }

    def _build_sections_context(
        self,
        problem_text: str,
        section_results: List,
        sub_problems: List,
        analyzer_result: Dict,
        data_result: Dict
    ) -> str:
        """构建各子问题的详细上下文"""
        sections_context = ""
        for sp in section_results:
            sp_name = sp.get("sub_problem_name", "")
            sp_desc = sp.get("sub_problem_desc", "")
            model = sp.get("model", {})
            solve = sp.get("solve", {})

            decision_vars = _fmt_vars(model.get("decision_variables", []))
            constraints = _fmt_constraints(model.get("constraints", []))
            alg_name = ""
            alg_desc = ""
            if isinstance(model.get("algorithm"), dict):
                alg_name = model["algorithm"].get("name", "")
                alg_desc = model["algorithm"].get("description", "")
            elif isinstance(model.get("algorithm"), str):
                alg_name = model["algorithm"]

            numerical_results = solve.get("numerical_results", {})
            numerical_str = json.dumps(numerical_results, ensure_ascii=False, indent=2) if numerical_results else "待计算"
            key_findings = solve.get("key_findings", [])
            key_findings_str = "; ".join([str(f) for f in key_findings[:5]]) if key_findings else "待确定"

            sections_context += f"""
===== 子问题：{sp_name} =====
问题描述：{sp_desc}

数学模型：
- 模型类型：{model.get('model_type', '')}
- 模型名称：{model.get('model_name', '')}
- 决策变量：{decision_vars}
- 目标函数：{model.get('objective_function', '')}
- 约束条件：{constraints}
- 算法：{alg_name} - {alg_desc}

求解结果：
- 关键发现：{key_findings_str}
- 数值结果：{numerical_str}
"""
        return sections_context

    def _build_data_context(self, data_result: Dict) -> str:
        """构建数据分析上下文"""
        analyses = data_result.get("analyses", [])
        if not analyses:
            return "（无数据文件）"

        data_context = "数据文件分析结果：\n"
        for a in analyses:
            fname = a.get("file_name", "")
            shape = a.get("shape", [0, 0])
            cols = a.get("basic_info", {}).get("numerical_columns", [])
            insights = a.get("insights", [])
            insights_str = "; ".join([str(i) for i in insights[:3]]) if insights else "无"
            data_context += f"- {fname}: {shape[0]}行×{shape[1]}列，列名：{cols}，洞察：{insights_str}\n"
        return data_context

    def _generate_fallback_latex(
        self,
        problem_text: str,
        section_results: List,
        analyzer_result: Dict,
        template: str = "math_modeling"
    ) -> str:
        """生成LaTeX模板（当LLM调用失败时），根据 template 选择不同格式"""
        # 生成各子问题的章节
        sp_sections = ""
        for idx, sp in enumerate(section_results):
            sp_name = sp.get("sub_problem_name", f"子问题{idx+1}")
            model = sp.get("model", {})
            solve = sp.get("solve", {})

            decision_vars = _fmt_vars(model.get("decision_variables", []))
            constraints = _fmt_constraints(model.get("constraints", []))
            alg_name = model.get("algorithm", {}).get("name", "优化算法") if isinstance(model.get("algorithm"), dict) else "优化算法"
            key_findings = solve.get("key_findings", []) if isinstance(solve, dict) else []
            key_findings_str = "; ".join([str(f) for f in key_findings[:3]]) if key_findings else "待确定"

            sp_sections += f"""
\\section{{{idx+4} {sp_name}的模型建立}}
\\subsection{{模型假设}}
\\begin{{enumerate}}
\\item 假设所有数据真实可靠
\\item 假设模型参数在研究期间保持稳定
\\item 假设各变量满足模型所要求的数学性质
\\end{{enumerate}}

\\subsection{{模型建立}}
{{\\textbf{{模型类型：}}{model.get('model_type', '优化模型')}}}\\\\\\
{{\\textbf{{决策变量：}}{decision_vars}}}\\\\\\
{{\\textbf{{目标函数：}}{model.get('objective_function', '')}}}\\\\\\
{{\\textbf{{约束条件：}}{constraints}}}

\\section{{{idx+5} {sp_name}的求解}}
\\subsection{{算法设计}}
{alg_name}

\\subsection{{求解结果}}
{key_findings_str}
"""

        # 生成数值结果表格
        results_table = ""
        numerical_found = False
        for idx, sp in enumerate(section_results):
            solve = sp.get("solve", {})
            if isinstance(solve, dict):
                numerical = solve.get("numerical_results", {})
                if numerical:
                    numerical_found = True
                    sp_name = sp.get("sub_problem_name", f"子问题{idx+1}")
                    results_table += f"{sp_name}: {json.dumps(numerical, ensure_ascii=False)[:200]}\n"

        if template == "coursework":
            return self._generate_coursework_fallback(problem_text, section_results, analyzer_result, sp_sections, numerical_found, results_table)
        elif template == "financial_analysis":
            return self._generate_financial_fallback(problem_text, section_results, analyzer_result, sp_sections, numerical_found, results_table)
        return self._generate_cumcm_fallback(problem_text, section_results, analyzer_result, sp_sections, numerical_found, results_table)

    def _generate_cumcm_fallback(self, problem_text, section_results, analyzer_result, sp_sections, numerical_found, results_table):
        return f"""\\documentclass[withoutpreface]{{cumcmthesis}}
\\usepackage{{url}}
\\usepackage{{subcaption}}

% 字体设置（使用系统自带字体）
\\setCJKmainfont{{SimSun}}
\\setCJKsansfont{{SimHei}}
\\setCJKmonofont{{FangSong}}

\\tihao{{B}}
\\baominghao{{2025001}}
\\schoolname{{某大学}}
\\membera{{队员A}}
\\memberb{{队员B}}
\\memberc{{队员C}}
\\supervisor{{指导教师}}
\\yearinput{{2025}}
\\monthinput{{09}}
\\dayinput{{15}}

\\begin{{document}}

\\maketitle

\\begin{{abstract}}
本文针对数学建模问题进行了系统研究。首先对问题进行了深入分析，建立了相应的数学模型...（此处填入详细摘要）

\\textbf{{关键词}}: 数学建模；优化模型；算法设计；数据分析；论文写作
\\end{{abstract}}

\\section{{1 问题重述}}

\\subsection{{1.1 研究背景}}
{problem_text[:500]}

\\subsection{{1.2 问题描述}}
（此处填入问题描述）

\\section{{2 问题分析}}
问题类型：{analyzer_result.get('problem_type', '优化问题')}\\\\
整体思路：{analyzer_result.get('overall_approach', '建立数学模型求解')}

\\section{{3 模型假设与符号说明}}

\\subsection{{3.1 模型假设}}
\\begin{{enumerate}}
\\item 假设所有数据真实可靠，来源于实际测量或权威统计
\\item 假设模型参数在研究期间保持相对稳定
\\item 假设各变量之间满足模型所要求的数学性质
\\end{{enumerate}}

\\subsection{{3.2 符号说明}}
\\begin{{table}}[H]
\\centering
\\caption{{主要符号说明}}
\\begin{{tabular}}{{ccp{{8cm}}}}
\\toprule
符号 & 意义 & 说明 \\\\
\\midrule
$x$ & 决策变量 & 变量描述 \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\section{{4 模型建立与求解}}
{sp_sections or '（此处填入模型建立与求解内容）'}

\\section{{5 结果分析}}
{f'数值结果：\\begin{{verbatim}}{results_table or "待计算"}\\end{{verbatim}}' if numerical_found else '（此处填入结果分析）'}

\\section{{6 可靠性分析}}
\\begin{{enumerate}}
\\item 结果合理性检验
\\item 约束满足性检验
\\item 灵敏度分析
\\end{{enumerate}}

\\section{{7 结论}}
本文针对数学建模问题建立了完整的模型并进行了求解...

\\section{{8 参考文献}}
\\begin{{thebibliography}}{{99}}
\\addcontentsline{{toc}}{{section}}{{参考文献}}
\\bibitem{{1}} 作者1. 题目1[J]. 期刊名称, 年份.
\\bibitem{{2}} 作者2. 题目2[M]. 出版地: 出版社, 年份.
\\end{{thebibliography}}

\\newpage
\\begin{{appendices}}
\\section{{Python求解代码}}
\\begin{{lstlisting}}[language=python]
# 代码内容
\\end{{lstlisting}}
\\end{{appendices}}

\\end{{document}}
"""

    def _generate_coursework_fallback(self, problem_text, section_results, analyzer_result, sp_sections, numerical_found, results_table):
        return f"""\\documentclass{{article}}
\\usepackage{{ctex}}
\\usepackage{{amsmath,amssymb,graphicx,booktabs}}
\\usepackage[margin=1in]{{geometry}}

\\title{{课程作业研究报告}}
\\author{{学生姓名}}
\\date{{\\today}}

\\begin{{document}}

\\maketitle

\\begin{{abstract}}
本文针对课程作业中的问题进行了系统研究。首先对问题背景进行了分析，然后建立了相应的数学模型并进行求解。研究结果表明所采用的方法是有效的。

\\textbf{{关键词}}: 课程作业；数学模型；数据分析
\\end{{abstract}}

\\section{{引言}}
{problem_text[:500]}

\\section{{问题描述}}
（此处填入问题描述）

\\section{{方法与模型}}

\\subsection{{模型假设}}
\\begin{{enumerate}}
\\item 假设所有数据真实可靠
\\item 假设模型参数在研究期间保持稳定
\\item 假设各变量满足模型所要求的数学性质
\\end{{enumerate}}

\\subsection{{符号说明}}
\\begin{{table}}[H]
\\centering
\\caption{{主要符号说明}}
\\begin{{tabular}}{{ccp{{8cm}}}}
\\toprule
符号 & 意义 & 说明 \\\\
\\midrule
$x$ & 决策变量 & 变量描述 \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\subsection{{模型建立}}
{sp_sections or '（此处填入模型建立内容）'}

\\section{{实验与求解}}
（此处填入求解过程和代码说明）

\\section{{结果分析}}
{f'数值结果：\\begin{{verbatim}}{results_table or "待计算"}\\end{{verbatim}}' if numerical_found else '（此处填入结果分析）'}

\\section{{总结与展望}}
本文针对课程作业问题建立了完整的模型并进行了求解。未来可以进一步改进...

\\section*{{参考文献}}
\\addcontentsline{{toc}}{{section}}{{参考文献}}
\\begin{{thebibliography}}{{99}}
\\bibitem{{1}} 作者1. 题目1[J]. 期刊名称, 年份.
\\bibitem{{2}} 作者2. 题目2[M]. 出版地: 出版社, 年份.
\\end{{thebibliography}}

\\newpage
\\appendix
\\section{{Python代码}}
\\begin{{verbatim}}
# 代码内容
\\end{{verbatim}}

\\end{{document}}
"""

    def _generate_financial_fallback(self, problem_text, section_results, analyzer_result, sp_sections, numerical_found, results_table):
        return f"""\\documentclass{{article}}
\\usepackage{{ctex}}
\\usepackage{{amsmath,amssymb,graphicx,booktabs}}
\\usepackage[margin=1in]{{geometry}}

\\title{{金融分析报告}}
\\author{{分析团队}}
\\date{{\\today}}

\\begin{{document}}

\\maketitle

\\begin{{abstract}}
本报告针对金融市场中的相关问题进行了系统分析。通过数据驱动的研究方法，建立了量化分析模型，并进行了实证检验。报告最后给出了明确的投资建议和风险提示。

\\textbf{{关键词}}: 金融分析；投资策略；风险管理；量化模型
\\end{{abstract}}

\\section{{投资背景与市场概述}}
{problem_text[:500]}

\\section{{数据描述与预处理}}
（此处填入数据来源、处理方法和描述性统计）

\\section{{分析框架与方法}}

\\subsection{{模型假设}}
\\begin{{enumerate}}
\\item 假设市场价格服从一定的随机过程
\\item 假设历史数据可以反映未来趋势
\\item 假设交易成本可忽略或固定
\\end{{enumerate}}

\\subsection{{符号说明}}
\\begin{{table}}[H]
\\centering
\\caption{{主要符号说明}}
\\begin{{tabular}}{{ccp{{8cm}}}}
\\toprule
符号 & 意义 & 说明 \\\\
\\midrule
$r_t$ & 收益率 & 第t期收益率 \\\\
$\\sigma$ & 波动率 & 标准差 \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\subsection{{分析框架}}
{sp_sections or '（此处填入分析框架和模型）'}

\\section{{资产/策略建模}}
（此处填入具体的资产定价或策略模型）

\\section{{实证分析与回测结果}}
{f'数值结果：\\begin{{verbatim}}{results_table or "待计算"}\\end{{verbatim}}' if numerical_found else '（此处填入实证分析结果）'}

\\section{{风险分析}}
\\subsection{{VaR分析}}
（此处填入风险价值分析）
\\subsection{{压力测试}}
（此处填入压力测试结果）
\\subsection{{灵敏度分析}}
（此处填入灵敏度分析）

\\section{{投资建议与结论}}
基于以上分析，给出明确的投资建议：
\\begin{{enumerate}}
\\item 建议一
\\item 建议二
\\item 风险提示
\\end{{enumerate}}

\\section*{{参考文献}}
\\addcontentsline{{toc}}{{section}}{{参考文献}}
\\begin{{thebibliography}}{{99}}
\\bibitem{{1}} 作者1. 题目1[J]. 期刊名称, 年份.
\\bibitem{{2}} 作者2. 题目2[M]. 出版地: 出版社, 年份.
\\end{{thebibliography}}

\\newpage
\\appendix
\\section{{Python分析代码}}
\\begin{{verbatim}}
# 代码内容
\\end{{verbatim}}

\\end{{document}}
"""
