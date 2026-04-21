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


# ===== CUMCM论文LaTeX生成提示词 =====
CUMCM_WRITER_SYSTEM = r"""你是一个专业的全国大学生数学建模竞赛（CUMCM）论文写作专家。

【论文格式要求】
严格按照以下格式生成论文，使用 cumcmthesis 文档类：
- 承诺书页（\maketitle）
- 摘要：300-500字
- 关键词：5个
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

【重要】
1. 论文必须是可以用 xelatex 编译的完整LaTeX代码
2. 数学公式用 equation 或 align 环境
3. 表格用 booktabs 风格（\toprule, \midrule, \bottomrule）
4. 图形标题放在图形下方
5. 参考文献使用 thebibliography 环境

请生成完整论文JSON输出，严格按以下格式返回（必须以JSON开头和结尾，不要有任何其他文字）：
{
    "title": "论文标题（简洁准确）",
    "abstract": "摘要（300-500字，包含问题背景、采用方法、主要结果和结论）",
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


@AgentFactory.register("writer_agent")
class WriterAgent(BaseAgent):
    name = "writer_agent"
    label = "写作专家"
    description = "生成完整CUMCM格式LaTeX论文"
    default_model = "minimax-m2.7"
    default_llm_backend = "claude"  # 使用 Claude Code
    _max_tokens_override = 16000

    def get_system_prompt(self) -> str:
        return CUMCM_WRITER_SYSTEM

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        problem_text = task_input.get("problem_text", context.get("problem_text", ""))
        all_results = context.get("results", {})
        section_results = context.get("section_results", [])
        sub_problems = context.get("sub_problems", [])
        analyzer_result = context.get("analyzer_result", {})
        data_result = context.get("data_result", {})

        logger.info(f"WriterAgent generating CUMCM paper with {len(section_results)} sections")

        # 构建详细的写作上下文
        sections_context = self._build_sections_context(
            problem_text, section_results, sub_problems, analyzer_result, data_result
        )

        prompt = f"""请生成全国大学生数学建模竞赛（CUMCM）格式的完整论文。

【原始赛题】
{problem_text}

【数据分析结果】
{self._build_data_context(data_result)}

【各子问题建模与求解结果】
{sections_context}

请生成完整论文LaTeX代码，输出严格JSON格式。"""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
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
                result["latex_code"] = result.get("latex_code", self._generate_fallback_latex(problem_text, section_results, analyzer_result))
                result["generated_at"] = datetime.now().isoformat()
                logger.info(f"WriterAgent paper generated: {result.get('title', '')}")
                return result
        except Exception as e:
            logger.error(f"WriterAgent failed: {e}")

        # Fallback
        return {
            "title": "基于数学建模的论文研究",
            "abstract": "本文针对数学建模问题进行了系统研究...",
            "keywords": ["数学建模", "优化模型", "算法设计", "数据分析", "论文写作"],
            "latex_code": self._generate_fallback_latex(problem_text, section_results, analyzer_result),
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
        analyzer_result: Dict
    ) -> str:
        """生成CUMCM格式LaTeX模板（当LLM调用失败时）"""
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

{sp_sections or '\\section{4 模型建立} \\section{5 模型求解}'}

\\section{{6 结果分析}}
{f'数值结果：\\begin{{verbatim}}{results_table or "待计算"}\\end{{verbatim}}' if numerical_found else '（此处填入结果分析）'}

\\section{{7 可靠性分析}}
\\begin{{enumerate}}
\\item 结果合理性检验
\\item 约束满足性检验
\\item 灵敏度分析
\\end{{enumerate}}

\\section{{8 结论}}
本文针对数学建模问题建立了完整的模型并进行了求解...

\\section{{9 参考文献}}
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
