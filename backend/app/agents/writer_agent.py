"""写作Agent - 生成完整LaTeX论文"""
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
    description = "生成完整LaTeX论文"
    default_model = "minimax-m2.7"
    _max_tokens_override = 16000  # 论文生成需要更大的输出

    def get_system_prompt(self) -> str:
        return """你是一个专业的数学建模论文写作助手，负责生成符合全国大学生数学建模竞赛格式的完整论文。

论文必须包含以下章节（用LaTeX格式输出）：
1. 摘要（300-500字）
2. 问题重述
3. 模型假设与符号说明
4. 模型建立（每个子问题一节）
5. 模型求解（每个子问题一节）
6. 结果分析
7. 灵敏度分析
8. 结论
9. 参考文献

输出格式（严格JSON）：
{
    "title": "论文标题（简洁准确）",
    "abstract": "摘要（300-500字，包含问题、方法、结果）",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
    "latex_code": "完整LaTeX源代码（包含导言区、正文、所有章节）",
    "sections": {"摘要": "...", "问题分析": "...", ...},
    "model_summary": "模型总结（100字）"
}"""

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        problem_text = task_input.get("problem_text", context.get("problem_text", ""))
        all_results = context.get("results", {})
        section_results = context.get("section_results", [])
        sub_problems = context.get("sub_problems", [])
        analyzer_result = context.get("analyzer_result", {})
        data_result = context.get("data_result", {})

        logger.info(f"WriterAgent generating paper with {len(section_results)} sections")

        # 构建详细的写作上下文
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
- 算法步骤：{solve.get('algorithm_steps', [])}
- 关键发现：{solve.get('results', {}).get('key_findings', [])}
- 数值结果：{solve.get('results', {}).get('numerical_results', {})}
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

        prompt = f"""生成全国大学生数学建模竞赛论文，严格按照格式规范。

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

请生成完整论文LaTeX代码（可以直接编译运行），输出JSON格式。"""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.call_llm(messages=messages)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
                result["latex_code"] = result.get("latex_code", "% 论文")
                result["generated_at"] = datetime.now().isoformat()
                logger.info(f"WriterAgent paper generated: {result.get('title', '')}")
                return result
        except Exception as e:
            logger.error(f"WriterAgent failed: {e}")

        # Fallback: 构建基础论文结构
        return {
            "title": "基于数学建模的论文研究",
            "abstract": "本文针对数学建模问题进行了系统研究...",
            "keywords": ["数学建模", "优化模型", "算法设计", "数据分析", "论文写作"],
            "latex_code": self._generate_fallback_latex(problem_text, section_results, sub_problems),
            "sections": {},
            "generated_at": datetime.now().isoformat(),
        }

    def _generate_fallback_latex(self, problem_text: str, section_results: List, sub_problems: List) -> str:
        """生成基础LaTeX模板（当LLM调用失败时）"""
        sections_latex = ""
        for idx, sp in enumerate(section_results):
            sp_name = sp.get("sub_problem_name", f"子问题{idx+1}")
            model = sp.get("model", {})
            decision_vars = _fmt_vars(model.get("decision_variables", []))
            sections_latex += f"""
\\section{{{sp_name}的模型建立}}
\\subsection{{模型假设}}
% 根据问题特点建立模型假设

\\subsection{{模型建立}}
\\textbf{{模型类型：}}{model.get('model_type', '')}\\\\
\\textbf{{决策变量：}}{decision_vars}\\\\

\\section{{{sp_name}的求解}}
\\subsection{{算法设计}}
"""

        return f"""\\documentclass{{article}}
\\usepackage{{ctex}}
\\usepackage{{amsmath,amssymb,graphicx}}
\\usepackage{{[margin=1in]{{geometry}}}}
\\title{{基于数学建模的论文研究}}
\\author{{数学建模团队}}

\\begin{{document}}
\\maketitle

\\section{{问题重述}}
{problem_text[:500]}

{sections_latex or '\\section{模型建立} \\section{模型求解}'}

\\section{{结论}}
% 总结研究结果

\\end{{document}}
"""
