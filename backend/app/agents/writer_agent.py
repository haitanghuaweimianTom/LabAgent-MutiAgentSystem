"""写作Agent - 生成完整LaTeX论文（全国大学生数学建模竞赛标准格式）"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List
from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)


def _fmt_vars(vars_list: List) -> str:
    """格式化变量列表（处理dict和str混合）"""
    if not vars_list:
        return "无"
    parts = []
    for v in vars_list:
        if isinstance(v, dict):
            name = v.get("name", v.get("Name", "x"))
            desc = v.get("description", v.get("desc", ""))
            parts.append(f"{name}({desc})" if desc else name)
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
            parts.append(f"{name}: {expr}" if expr else name)
        else:
            parts.append(str(c))
    return "; ".join(parts)


@AgentFactory.register("writer_agent")
class WriterAgent(BaseAgent):
    name = "writer_agent"
    label = "写作专家"
    description = "生成完整LaTeX论文（全国大学生数学建模竞赛标准格式）"
    default_model = "minimax-m2.7"
    _max_tokens_override = 32000  # 论文生成需要更大的输出

    def get_system_prompt(self) -> str:
        return """你是一个专业的全国大学生数学建模竞赛论文写作助手，负责生成符合CUMCM格式规范的完整论文。

【论文结构（必须严格按此顺序）】
1. 摘要（300-500字）
2. 问题重述
   - 问题的提出
   - 问题要求
3. 模型假设与符号说明
   - 模型假设（列出3-5条合理假设）
   - 符号说明（表格形式）
4. 问题分析
   - 总体分析
   - 子问题分析
5. 模型建立
   - 模型概述
   - 子问题1的模型
   - 子问题2的模型（如有）
   - 子问题3的模型（如有）
6. 模型求解
   - 求解方法概述
   - 子问题1的求解
   - 子问题2的求解（如有）
   - 子问题3的求解（如有）
7. 结果分析
   - 主要结果
   - 结果分析
   - 可视化分析
8. 灵敏度分析
9. 模型评价
   - 模型优点
   - 模型缺点
   - 适用范围
10. 结论与展望
    - 研究总结
    - 主要结论
    - 未来展望
11. 参考文献
12. 附录（代码）

【重要要求】
- 使用 cumcmthesis.cls 格式
- 摘要必须包含：问题背景、采用方法、主要结果、结论
- 关键词5个，用 \quad 分隔
- 公式使用 align 环境，带编号
- 表格使用 booktabs 三线表
- 图片使用 figure 环境
- 参考文献不少于3篇
- 论文控制在20页以内

输出格式（严格JSON）：
{
    "title": "论文标题（简洁准确，体现问题核心）",
    "abstract": "摘要（300-500字，包含问题背景、方法、结果、结论）",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
    "latex_code": "完整LaTeX源代码（使用cumcmthesis.cls，包含所有章节）",
    "sections": {
        "摘要": "摘要内容",
        "问题重述": "问题重述内容",
        "模型假设": "模型假设内容",
        "符号说明": "符号说明内容",
        "问题分析": "问题分析内容",
        "模型建立": "模型建立内容",
        "模型求解": "模型求解内容",
        "结果分析": "结果分析内容",
        "灵敏度分析": "灵敏度分析内容",
        "模型评价": "模型评价内容",
        "结论": "结论内容"
    }
}"""

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        problem_text = task_input.get("problem_text", context.get("problem_text", ""))
        all_results = context.get("results", {})
        section_results = context.get("section_results", [])
        sub_problems = context.get("sub_problems", [])
        analyzer_result = context.get("analyzer_result", {})
        data_result = context.get("data_result", {})

        logger.info(f"WriterAgent generating CUMCM paper with {len(section_results)} sections")

        # 构建详细的写作上下文
        sections_context = ""
        for idx, sp in enumerate(section_results):
            sp_name = sp.get("sub_problem_name", f"子问题{idx+1}")
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

            numerical_results = solve.get("results", {}).get("numerical_results", {})
            key_findings = solve.get("results", {}).get("key_findings", [])

            sections_context += f"""
===== 子问题{idx+1}：{sp_name} =====
问题描述：{sp_desc}

数学模型：
- 模型类型：{model.get('model_type', '')}
- 模型名称：{model.get('model_name', '')}
- 决策变量：{decision_vars}
- 目标函数：{model.get('objective_function', '')}
- 约束条件：{constraints}
- 算法：{alg_name} - {alg_desc}

模型假设：{model.get('model_assumptions', [])}
模型优点：{model.get('model_advantages', [])}

求解结果：
- 算法步骤：{solve.get('algorithm_steps', [])}
- 关键发现：{key_findings}
- 数值结果：{numerical_results}
"""

        data_context = ""
        analyses = data_result.get("analyses", [])
        if analyses:
            data_context = "数据文件分析结果：\n"
            for a in analyses:
                fname = a.get("file_name", "")
                shape = a.get("shape", [0, 0])
                cols = a.get("basic_info", {}).get("numerical_columns", [])
                insights = a.get("insights", [])
                data_context += f"- {fname}: {shape[0]}行×{shape[1]}列，列名：{cols}，洞察：{insights}\n"

        prompt = f"""生成全国大学生数学建模竞赛论文，严格按照CUMCM格式规范。

【原始赛题】
{problem_text}

【问题分析结论】
- 问题类型：{analyzer_result.get('problem_type', '')}
- 难度：{analyzer_result.get('difficulty', '')}
- 整体思路：{analyzer_result.get('overall_approach', '')}
- 关键难点：{analyzer_result.get('key_difficulties', [])}
- 推荐工具：{analyzer_result.get('suggested_tools', [])}

【数据分析】
{data_context or '（无数据文件）'}

【各子问题建模与求解结果】
{sections_context}

请生成符合CUMCM格式的完整论文LaTeX代码，必须包含：
1. 使用 cumcmthesis.cls 文档类
2. 完整的摘要（300-500字）
3. 问题重述、模型假设、符号说明、问题分析、模型建立、模型求解、结果分析、灵敏度分析、模型评价、结论与展望
4. 至少3篇参考文献
5. 附录代码
6. 所有章节必须有实质内容，不能只是框架

输出JSON格式。"""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.call_llm(messages=messages, temperature=0.3)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
                result["latex_code"] = result.get("latex_code", self._generate_cumcm_latex(problem_text, section_results, sub_problems))
                result["generated_at"] = datetime.now().isoformat()
                logger.info(f"WriterAgent CUMCM paper generated: {result.get('title', '')}")
                return result
        except Exception as e:
            logger.error(f"WriterAgent failed: {e}")

        # Fallback: 使用CUMCM模板生成基础论文
        return {
            "title": "基于数学建模的论文研究",
            "abstract": f"本文针对建模问题进行了系统研究，建立了数学模型并求解得到数值结果。",
            "keywords": ["数学建模", "优化模型", "算法设计", "数据分析", "结果分析"],
            "latex_code": self._generate_cumcm_latex(problem_text, section_results, sub_problems),
            "sections": {},
            "generated_at": datetime.now().isoformat(),
        }

    def _generate_cumcm_latex(self, problem_text: str, section_results: List, sub_problems: List) -> str:
        """生成符合CUMCM格式的基础LaTeX论文"""
        sections_latex = ""

        # 为每个子问题生成对应的章节
        for idx, sr in enumerate(section_results):
            sp_name = sr.get("sub_problem_name", f"子问题{idx+1}")
            sp_desc = sr.get("sub_problem_desc", "")
            model = sr.get("model", {})
            solve = sr.get("solve", {})

            decision_vars = _fmt_vars(model.get("decision_variables", []))
            constraints = _fmt_constraints(model.get("constraints", []))
            alg_name = model.get("algorithm", {}).get("name", "算法")
            model_name = model.get("model_name", "")
            model_type = model.get("model_type", "")

            numerical_results = solve.get("results", {}).get("numerical_results", {})
            key_findings = solve.get("results", {}).get("key_findings", [])
            assumptions = model.get("model_assumptions", [])

            sections_latex += f"""
\\section{{{sp_name}的模型建立}}
subsection{{模型假设}}
"""

            if assumptions:
                for i, assumption in enumerate(assumptions[:5], 1):
                    sections_latex += f"\\item {{assumption {i}：{assumption}}}\n"
            else:
                sections_latex += """\\item 假设所有数据真实可靠
\\item 假设模型参数在研究期间保持稳定
\\item 假设各变量满足模型所要求的数学性质
"""

            sections_latex += f"""
subsection{{符号说明}}
\\begin{{center}}
\\begin{{tabular}}{{cc}}
\\toprule
符号 & 意义 \\\\
\\midrule
x & 决策变量 \\\\
y & 中间变量 \\\\
z & 目标变量 \\\\
\\bottomrule
\\end{{tabular}}
\\end{{center}}

subsection{{模型建立}}
\\textbf{{模型类型：}}{model_type} \\\\
\\textbf{{模型名称：}}{model_name} \\\\
\\textbf{{决策变量：}}{decision_vars} \\\\
\\textbf{{目标函数：}}{model.get('objective_function', '')} \\\\
\\textbf{{约束条件：}}{constraints}

\\section{{{sp_name}的求解}}
subsection{{算法设计}}
\\textbf{{求解算法：}}{alg_name}

subsection{{数值结果}}
"""

            if numerical_results:
                sections_latex += "\\begin{itemize}\n"
                for k, v in list(numerical_results.items())[:5]:
                    sections_latex += f"\\item {k} = {v}\n"
                sections_latex += "\\end{itemize}\n"

            if key_findings:
                sections_latex += "\\subsection*{主要发现}\n"
                sections_latex += "\\begin{itemize}\n"
                for finding in key_findings[:3]:
                    sections_latex += f"\\item {finding}\n"
                sections_latex += "\\end{itemize}\n"

        return f"""\\documentclass{{cumcmthesis}}
\\usepackage{{url,subcaption}}

\\title{{基于数学建模的论文研究}}
\\tihao{{A}}
\\baominghao{{123456789012}}
\\schoolname{{XX大学}}
\\membera{{成员A}}
\\memberb{{成员B}}
\\memberc{{成员C}}
\\supervisor{{指导教师}}
\\yearinput{{2025}}
\\monthinput{{08}}
\\dayinput{{15}}

\\begin{{document}}
\\maketitle

\\begin{{abstract}}
本文针对数学建模问题进行了系统研究。首先对问题进行了深入分析，明确了问题的核心要求和关键难点...（此处根据实际问题填充）

本文的主要工作包括：
\\begin{{enumerate}}
\\item 对问题进行了全面分析，明确了问题的类型和难度
\\item 建立了合理的数学模型，给出了模型假设和符号说明
\\item 设计了有效的求解算法，得到了可靠的数值结果
\\item 进行了灵敏度分析，验证了模型的稳健性
\\end{{enumerate}}

\\keywords{{数学建模\quad 优化模型\quad 算法设计\quad 数据分析\quad 结果分析}}
\\end{{abstract}}

\\newpage

{section_latex or '\\section{{问题重述}} \\section{{模型假设}} \\section{{符号说明}} \\section{{问题分析}} \\section{{模型建立}} \\section{{模型求解}}'}

\\section{{结果分析}}
\\subsection*{{主要结果}}
% 根据具体数值结果填充

\\subsection*{{结果分析}}
% 分析结果的合理性和有效性

\\section{{灵敏度分析}}
\\subsection*{{参数灵敏度分析}}
% 分析各参数对结果的影响

\\subsection*{{稳健性分析}}
% 验证模型在不同条件下的表现

\\section{{模型评价}}
\\subsection*{{模型优点}}
\\begin{{enumerate}}
\\item 模型结构清晰，便于理解和解释
\\item 求解方法成熟，计算效率高
\\item 结果具有良好的可解释性
\\end{{enumerate}}

\\subsection*{{模型缺点}}
\\begin{{enumerate}}
\\item 假设可能过于理想化
\\item 对数据质量有一定要求
\\end{{enumerate}}

\\section{{结论与展望}}
\\subsection*{{研究总结}}
本文对数学建模问题进行了系统研究...

\\subsection*{{主要结论}}
\\begin{{enumerate}}
\\item 建立了有效的数学模型
\\item 求得了合理的数值结果
\\item 验证了模型的稳健性
\\end{{enumerate}}

\\newpage
\\begin{{thebibliography}}{{9}}
\\bibitem{{1}} 作者1. 题目1[J]. 期刊名称, 年份.
\\bibitem{{2}} 作者2. 题目2[M]. 出版社, 年份.
\\bibitem{{3}} 作者3. 题目3[R]. 报告编号, 年份.
\\end{{thebibliography}}

\\newpage
\\begin{{appendices}}
\\section{{附录A：Python求解代码}}
\\begin{{lstlisting}}[language=Python]
# 代码内容
import numpy as np
print("Hello World")
\\end{{lstlisting}}
\\end{{appendices}}
\\end{{document}}
"""
