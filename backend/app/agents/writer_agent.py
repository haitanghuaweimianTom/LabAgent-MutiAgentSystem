"""写作Agent - 按章节独立生成高质量LaTeX论文

v4.0 重构：
- 按章节独立调用 LLM，每章附带大纲、相关摘要、前2章摘要、可用图表列表
- 每章生成后自动评分（格式、内容、引用、图表），低于阈值自动重写
- 自动注入 available_figures 图表路径到写作上下文

v4.1 扩展：
- 接入 [app.core.paper_templates](../core/paper_templates/__init__.py) 注册表。
  旧 4 套模板（math_modeling / coursework / financial_analysis / research_survey）
  仍由本文件内的常量提供（保持向后兼容），新 CCF-A 模板
  （ieee_conference / neurips_2024 / acm_sigconf / springer_lncs 等）由注册表提供。
  通过 :func:`_resolve_template` 统一桥接：旧 id 走旧常量，新 id 走注册表。
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseAgent, AgentFactory
from ..core.paper_templates import load_template as _load_template_from_registry

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


# ===== 章节规划 =====

ChapterPlan = Dict[str, Any]

CUMCM_CHAPTERS: List[ChapterPlan] = [
    {
        "id": "abstract",
        "title": "摘要",
        "section_level": 0,
        "prompt_role": "撰写论文摘要和关键词。",
        "requirements": [
            "300-500字，不超过一页",
            "针对每个问题说明：方法→模型→求解→结果→结论",
            "包含模型的数学归类、建模思想、算法思想、建模特点、主要数值结果",
            "不要出现复杂公式和表格",
            "结论必须明确具体，避免模糊表达",
        ],
    },
    {
        "id": "problem_restated",
        "title": "1 问题重述",
        "section_level": 1,
        "prompt_role": "撰写问题重述，包括研究背景与问题描述。",
        "requirements": [
            "用自己的语言重新表述问题，切忌照抄原题",
            "对模糊概念和条件给出必要的澄清与说明",
            "1.1 研究背景：问题实际背景与意义",
            "1.2 问题描述：重述问题，体现自己的理解",
        ],
    },
    {
        "id": "problem_analysis",
        "title": "2 问题分析",
        "section_level": 1,
        "prompt_role": "撰写问题分析，相当于学术论文引言。",
        "requirements": [
            "解决问题的宏观思路、方法选择依据、建模过程与步骤",
            "对要使用的数学方法的适用性与合理性进行分析",
            "整体分析+总体建模思路",
        ],
    },
    {
        "id": "assumptions",
        "title": "3 模型假设与符号说明",
        "section_level": 1,
        "prompt_role": "撰写模型假设与符号说明。",
        "requirements": [
            "3.1 模型假设：逐条编号列出，每条说明必要性和合理性",
            "3.2 符号说明：表格形式，包含符号、含义、单位、关系",
            "假设必须在正文中被引用",
        ],
    },
    {
        "id": "modeling",
        "title": "4 模型的建立与求解",
        "section_level": 1,
        "prompt_role": "撰写论文核心：各子问题的建模与求解。",
        "requirements": [
            "所有子问题在本章节内用 \\subsection 区分",
            "子问题标题要反映所解决的问题和方法，不要空洞命名",
            "每个子问题必须包含七个环节：问题分析→方法介绍→模型构建→算法设计→求解结果→结果验证→问题小结",
            "子问题之间要衔接，依赖前序结果时明确写出",
            "适当插入可用图表",
        ],
    },
    {
        "id": "result_analysis",
        "title": "5 结果分析",
        "section_level": 1,
        "prompt_role": "撰写结果分析。",
        "requirements": [
            "对各问题结果的定性和规律性讨论",
            "数值结果配合文字解释，说明实际含义",
            "多个方案可列表比较",
            "从全局视角分析各问题结果之间的关系",
        ],
    },
    {
        "id": "reliability",
        "title": "6 可靠性分析",
        "section_level": 1,
        "prompt_role": "撰写可靠性分析。",
        "requirements": [
            "6.1 模型检验：准确性检验，与实际数据或已知结果对比",
            "6.2 敏感性分析：关键参数变动对结果的影响",
            "对于工程领域的实际问题必须做",
        ],
    },
    {
        "id": "evaluation",
        "title": "7 模型评价",
        "section_level": 1,
        "prompt_role": "撰写模型评价。",
        "requirements": [
            "从优点、缺点和创新点三方面实事求是评价",
            "推广方向和可能的改进",
        ],
    },
    {
        "id": "conclusion",
        "title": "8 结论",
        "section_level": 1,
        "prompt_role": "撰写结论。",
        "requirements": [
            "简要回顾全文主要工作和发现",
            "对题目要求回答的问题一一明确回答",
        ],
    },
    {
        "id": "references",
        "title": "9 参考文献",
        "section_level": 1,
        "prompt_role": "撰写参考文献。",
        "requirements": [
            "使用 \\begin{thebibliography}{99} 环境",
            "根据已有文献列表生成规范引用",
        ],
    },
    {
        "id": "appendix",
        "title": "附录",
        "section_level": 0,
        "prompt_role": "撰写附录，包含核心代码。",
        "requirements": [
            "使用 \\begin{appendices} 环境",
            "附录核心求解代码",
        ],
    },
]

COURSEWORK_CHAPTERS: List[ChapterPlan] = [
    {
        "id": "abstract",
        "title": "摘要",
        "section_level": 0,
        "prompt_role": "撰写报告摘要和关键词。",
        "requirements": ["200-400字", "说明研究目的、方法、主要结果和结论"],
    },
    {
        "id": "introduction",
        "title": "1 引言",
        "section_level": 1,
        "prompt_role": "撰写引言/研究背景。",
        "requirements": [
            "说明研究目的和动机",
            "简述相关领域现状和已有方法",
            "明确本文要解决的问题和主要贡献",
        ],
    },
    {
        "id": "problem_description",
        "title": "2 问题描述",
        "section_level": 1,
        "prompt_role": "撰写问题描述。",
        "requirements": [
            "用自己的语言重新描述要解决的问题",
            "列出已知条件、约束和目标",
        ],
    },
    {
        "id": "methods",
        "title": "3 方法与模型",
        "section_level": 1,
        "prompt_role": "撰写方法与模型。",
        "requirements": [
            "说明为什么选择这个方法",
            "详细描述方法原理和数学推导",
            "列出模型假设和符号说明",
            "核心公式和算法步骤",
        ],
    },
    {
        "id": "experiment",
        "title": "4 实验与求解",
        "section_level": 1,
        "prompt_role": "撰写实验与求解过程。",
        "requirements": [
            "说明实验环境、数据来源、预处理步骤",
            "详细描述求解步骤和实现方法",
            "适当插入可用图表",
        ],
    },
    {
        "id": "result_analysis",
        "title": "5 结果分析",
        "section_level": 1,
        "prompt_role": "撰写结果分析。",
        "requirements": [
            "数值结果必须配合文字解释",
            "对比分析和局限性讨论",
        ],
    },
    {
        "id": "conclusion",
        "title": "6 总结与展望",
        "section_level": 1,
        "prompt_role": "撰写总结与展望。",
        "requirements": ["回顾主要工作", "提出改进方向"],
    },
    {
        "id": "references",
        "title": "参考文献",
        "section_level": 0,
        "prompt_role": "撰写参考文献。",
        "requirements": ["规范引用已有文献"],
    },
]

FINANCIAL_CHAPTERS: List[ChapterPlan] = [
    {
        "id": "abstract",
        "title": "执行摘要",
        "section_level": 0,
        "prompt_role": "撰写执行摘要和关键词。",
        "requirements": [
            "200-400字",
            "精炼概括研究目的→数据来源→分析方法→关键发现→投资建议",
            "投资建议必须明确具体",
            "包含关键数值结果",
        ],
    },
    {
        "id": "market_overview",
        "title": "1 投资背景与市场概述",
        "section_level": 1,
        "prompt_role": "撰写投资背景与市场概述。",
        "requirements": [
            "说明研究实际动机和意义",
            "描述宏观背景、市场热点",
            "文献回顾聚焦最相关文献",
            "明确研究目标和主要贡献",
        ],
    },
    {
        "id": "data",
        "title": "2 数据描述与预处理",
        "section_level": 1,
        "prompt_role": "撰写数据描述与预处理。",
        "requirements": [
            "说明数据来源、时间范围、频率、样本量",
            "描述性统计",
            "预处理步骤和变换说明",
            "用图表展示数据特征",
        ],
    },
    {
        "id": "methods",
        "title": "3 分析框架与方法",
        "section_level": 1,
        "prompt_role": "撰写分析框架与方法。",
        "requirements": [
            "说明方法选择依据",
            "经典金融模型写出核心公式和假设",
            "符号说明清晰",
            "讨论模型局限性和适用条件",
        ],
    },
    {
        "id": "modeling",
        "title": "4 资产/策略建模",
        "section_level": 1,
        "prompt_role": "撰写资产/策略建模。",
        "requirements": [
            "详细描述模型构建过程",
            "量化策略说明逻辑、信号、持仓、调仓",
            "参数估计方法说明",
        ],
    },
    {
        "id": "empirical",
        "title": "5 实证分析与回测结果",
        "section_level": 1,
        "prompt_role": "撰写实证分析与回测结果。",
        "requirements": [
            "定量给出收益率、波动率、夏普比率、最大回撤等",
            "表格对比不同模型/策略",
            "图表展示累计收益、净值等",
            "每个图表必须有文字解释",
            "适当插入可用图表",
        ],
    },
    {
        "id": "risk",
        "title": "6 风险分析",
        "section_level": 1,
        "prompt_role": "撰写风险分析。",
        "requirements": [
            "VaR分析、CVaR/ES、压力测试、灵敏度分析",
            "风险指标明确数值",
            "讨论流动性风险、模型风险",
        ],
    },
    {
        "id": "conclusion",
        "title": "7 投资建议与结论",
        "section_level": 1,
        "prompt_role": "撰写投资建议与结论。",
        "requirements": [
            "投资建议明确、具体、可操作",
            "基于前文分析结果，前后一致",
            "风险提示不可或缺",
            "总结主要发现和贡献",
        ],
    },
    {
        "id": "references",
        "title": "参考文献",
        "section_level": 0,
        "prompt_role": "撰写参考文献。",
        "requirements": ["规范引用已有文献"],
    },
]

RESEARCH_SURVEY_CHAPTERS: List[ChapterPlan] = [
    {
        "id": "abstract",
        "title": "摘要",
        "section_level": 0,
        "prompt_role": "撰写调研报告摘要和关键词。",
        "requirements": [
            "200-400字",
            "说明调研目标、检索策略、主要发现、结论",
        ],
    },
    {
        "id": "introduction",
        "title": "1 引言",
        "section_level": 1,
        "prompt_role": "撰写引言。",
        "requirements": [
            "说明调研背景和动机",
            "明确研究问题和调研范围",
            "概述报告结构",
        ],
    },
    {
        "id": "background",
        "title": "2 研究背景与问题定义",
        "section_level": 1,
        "prompt_role": "撰写研究背景与问题定义。",
        "requirements": [
            "定义核心概念",
            "描述问题的重要性和应用场景",
            "梳理相关背景",
        ],
    },
    {
        "id": "search_strategy",
        "title": "3 文献检索策略",
        "section_level": 1,
        "prompt_role": "撰写文献检索策略。",
        "requirements": [
            "说明检索关键词和数据库（如 arXiv）",
            "说明筛选标准和Top-K过滤方法",
            "列出检索结果数量",
        ],
    },
    {
        "id": "methods_survey",
        "title": "4 现有方法综述",
        "section_level": 1,
        "prompt_role": "撰写现有方法综述。",
        "requirements": [
            "按类别或时间线组织文献",
            "对每篇高相关论文说明：方法、创新点、优缺点",
            "使用表格对比不同方法",
        ],
    },
    {
        "id": "datasets",
        "title": "5 数据集与实验设置",
        "section_level": 1,
        "prompt_role": "撰写数据集与实验设置。",
        "requirements": [
            "汇总文献中使用的数据集",
            "说明评价指标和实验设置",
            "使用表格汇总",
        ],
    },
    {
        "id": "results_discussion",
        "title": "6 结果对比与讨论",
        "section_level": 1,
        "prompt_role": "撰写结果对比与讨论。",
        "requirements": [
            "对比各方法的关键结果",
            "讨论性能差异的原因",
            "指出方法适用场景",
        ],
    },
    {
        "id": "challenges",
        "title": "7 挑战与局限",
        "section_level": 1,
        "prompt_role": "撰写挑战与局限。",
        "requirements": [
            "总结当前研究面临的主要挑战",
            "列出各文献指出的局限性",
        ],
    },
    {
        "id": "future",
        "title": "8 未来研究方向",
        "section_level": 1,
        "prompt_role": "撰写未来研究方向。",
        "requirements": [
            "基于现有文献提出未来研究趋势",
            "指出潜在的研究机会",
        ],
    },
    {
        "id": "conclusion",
        "title": "9 结论",
        "section_level": 1,
        "prompt_role": "撰写结论。",
        "requirements": [
            "总结主要发现",
            "回答引言中提出的问题",
        ],
    },
    {
        "id": "references",
        "title": "10 参考文献",
        "section_level": 0,
        "prompt_role": "撰写参考文献。",
        "requirements": ["规范引用已有文献"],
    },
]


CHAPTER_PLANS: Dict[str, List[ChapterPlan]] = {
    "math_modeling": CUMCM_CHAPTERS,
    "coursework": COURSEWORK_CHAPTERS,
    "financial_analysis": FINANCIAL_CHAPTERS,
    "research_survey": RESEARCH_SURVEY_CHAPTERS,
}


# ===== 论文模板系统提示词 =====

CUMCM_WRITER_SYSTEM = r"""你是一个专业的全国大学生数学建模竞赛（CUMCM）论文写作专家。

【评阅标准（核心目标）】
假设的合理性、建模的创造性、结果的正确性、表述的清晰性。

【论文格式与行文结构（强制约束）】
严格按照以下格式生成论文，使用 cumcmthesis 文档类。章节顺序、层级结构必须遵循以下规定，不得增删章节、不得改变顺序：

\maketitle                          % 承诺书页（自动生成）
\begin{abstract} ... \end{abstract} % 摘要（300-500字，不超过一页）
\textbf{关键词}: XXX; XXX; XXX; XXX % 关键词3-5个，分号分隔

\section{1 问题重述}
    \subsection{1.1 研究背景}       % 问题实际背景与意义（行业痛点、现实需求）
    \subsection{1.2 问题描述}       % 用你自己的语言重述问题，切忌照抄原题

\section{2 问题分析}
    % 解决问题的宏观思路、方法选择依据、建模过程与步骤
    % 对要使用的数学方法的适用性与合理性进行分析
    % 相当于学术论文的引言：整体分析+总体建模思路

\section{3 模型假设与符号说明}
    \subsection{3.1 模型假设}       % 逐条编号列出，每条需说明必要性和合理性
    \subsection{3.2 符号说明}       % 表格形式：符号、含义、单位、关系

\section{4 模型的建立与求解}        % 论文核心部分
    % 所有子问题的建模与求解都在本 section 内，用 \subsection 区分
    % 立题名称要反映所解决的问题，不要用"问题1的模型建立与求解"这种空洞命名
    %
    % 每个子问题的 subsection 内部行文结构（必须按以下顺序逐层展开）：
    %   (1) 问题分析：本子问题的具体分析 + 建模思路
    %       → "针对XX子问题，我们首先……然后……"
    %   (2) 方法介绍（如使用经典算法/模型）：先介绍所用方法的基本概念和原理
    %       → 如使用雨流计数法、LSTM、随机森林等，需先说明方法原理
    %   (3) 模型构建：完整的数学推导过程
    %       → 定义决策变量 → 建立目标函数/方程 → 列出约束条件 → 解释每个公式的含义
    %       → 关键步骤不能跳过，推导过程要明其理、讲其理
    %   (4) 算法设计：用什么方法求解？为什么选这个算法？
    %       → 算法原理简述 → 算法步骤（可用伪代码或流程图） → 参数设置说明
    %   (5) 求解结果：数值结果突出表达（表格/图形）
    %       → 结果必须有文字解释，说明"从结果可以看出……"和实际含义
    %   (6) 结果验证/对比：用其他方法/基准方法对比验证结果合理性
    %       → 如多种模型对比、与已知结果对比、与常识对比
    %   (7) 问题小结：简短总结本子问题的主要发现和结论
    %       → "综上所述，通过XX方法，我们得到……"
    %
    % 子问题之间的衔接：
    %   - 后续子问题如果依赖前一个子问题的结果，要明确写出"基于上一节的结果……"
    %   - 不要让各个子问题看起来像完全独立的论文
    %   - 围绕解决问题的主线逐步深入
    \subsection{4.1 XXX模型（对应子问题1）}
    \subsection{4.2 XXX模型（对应子问题2）}
    \subsection{4.3 XXX模型（对应子问题3）}

\section{5 结果分析}
    % 对各问题结果的定性和规律性讨论
    % 数值结果配合文字解释，说明实际含义
    % 多个方案可列表比较
    % 从全局视角分析各问题结果之间的关系

\section{6 可靠性分析}
    \subsection{6.1 模型检验}       % 准确性检验（与实际数据或已知结果对比）
    \subsection{6.2 敏感性分析}     % 关键参数变动对结果的影响

\section{7 模型评价}
    % 优点、缺点和创新点三方面实事求是的评价
    % 推广方向和可能的改进

\section{8 结论}
    % 简要回顾全文主要工作和发现
    % 对题目要求回答的问题一一明确回答

\section{9 参考文献}
    \begin{thebibliography}{99} ... \end{thebibliography}

\begin{appendices}
    \section{Python求解代码}         % 附录：核心代码
\end{appendices}

【重要结构约束】
1. 章节编号必须连续，不得跳过或重复
2. "模型的建立与求解"必须是唯一的 \section（第4章），所有子问题在其内部用 \subsection 组织
3. 不得将每个子问题拆分为独立的 \section
4. 每个子问题末尾必须有"问题小结"
5. 如果使用经典算法/模型，必须先介绍方法原理再应用
6. 多种方法/模型之间要做对比验证，择优使用
7. 摘要中不要出现复杂公式和表格
8. 表格用 booktabs 风格（\toprule, \midrule, \bottomrule）
9. 图形标题放在图形下方
10. 论文必须是可以用 xelatex 编译的完整LaTeX代码
11. 数学公式用 equation 或 align 环境
12. 能用初等方法解决就不用高等方法；能用简单方法就不用复杂方法

【引号使用规范（强制约束）】
LaTeX 源代码中所有引号必须严格遵守以下规则：
1. 中文正文中的引用、强调、方法名称、专有名词：必须使用中文双引号 "中文内容" 和中文单引号 '中文内容'
2. 英文摘要或纯英文段落：使用 LaTeX 原生英文引号 `` 和 ''
3. 数学公式内：不使用任何引号
4. 严禁在中文正文中使用 `` 或 '' 等 LaTeX 英文引号
5. 严禁使用反引号 ` 作为中文引用的开引号

请严格按以下JSON格式返回（必须以JSON开头和结尾，不要有任何其他文字）：
{
    "title": "论文标题（简洁准确，不超过20字）",
    "abstract": "摘要（300-500字）",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
    "latex_code": "完整LaTeX源代码",
    "sections": {
        "问题重述": "主要内容摘要",
        "问题分析": "主要内容摘要",
        "模型假设与符号说明": "主要内容摘要",
        "模型的建立与求解": "主要内容摘要",
        "结果分析": "主要内容摘要",
        "可靠性分析": "主要内容摘要",
        "模型评价": "主要内容摘要",
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
- 语言风格：学术但简洁
- 篇幅：适中
- 重点：方法原理、实现过程、结果分析
- 不要求承诺书页

【引号使用规范（强制约束）】
LaTeX 源代码中所有引号必须严格遵守以下规则：
1. 中文正文中的引用、强调、方法名称、专有名词：必须使用中文双引号 "中文内容" 和中文单引号 '中文内容'
2. 英文摘要或纯英文段落：使用 LaTeX 原生英文引号 `` 和 ''
3. 数学公式内：不使用任何引号
4. 严禁在中文正文中使用 `` 或 '' 等 LaTeX 英文引号
5. 严禁使用反引号 ` 作为中文引用的开引号

请严格按以下JSON格式返回（必须以JSON开头和结尾，不要有任何其他文字）：
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

FINANCIAL_ANALYSIS_WRITER_SYSTEM = r"""你是一个专业的金融分析报告写作专家，擅长撰写投资分析、风险评估、资产定价、量化策略、投资组合优化等金融领域的分析报告。

【报告格式要求】
生成专业的金融分析报告，使用 article 文档类：
- 封面/标题页（\maketitle）
- 执行摘要（Executive Summary）：200-400字
- 关键词：3-5个
- 章节：1 投资背景与市场概述 → 2 数据描述与预处理 → 3 分析框架与方法 → 4 资产/策略建模 → 5 实证分析与回测结果 → 6 风险分析 → 7 投资建议与结论 → 8 参考文献
- 附录：代码、补充数据表格

【金融分析报告特点】
- 数据驱动：大量使用图表、数据表格支撑论点
- 风险意识：必须包含定量风险评估
- 实用性：给出明确可执行的投资建议或策略结论
- 专业术语：正确使用金融学术语
- 可复现性：说明数据来源、处理步骤、参数设置

【引号使用规范（强制约束）】
LaTeX 源代码中所有引号必须严格遵守以下规则：
1. 中文正文中的引用、强调、金融产品名、指标名：必须使用中文双引号 "中文内容" 和中文单引号 '中文内容'
2. 英文摘要或纯英文段落：使用 LaTeX 原生英文引号 `` 和 ''
3. 数学公式内：不使用任何引号
4. 严禁在中文正文中使用 `` 或 '' 等 LaTeX 英文引号
5. 严禁使用反引号 ` 作为中文引用的开引号

请严格按以下JSON格式返回（必须以JSON开头和结尾，不要有任何其他文字）：
{
    "title": "报告标题",
    "abstract": "执行摘要（200-400字）",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "latex_code": "完整LaTeX源代码",
    "sections": {
        "投资背景与市场概述": "主要内容摘要",
        "数据描述与预处理": "主要内容摘要",
        "分析框架与方法": "主要内容摘要",
        "资产/策略建模": "主要内容摘要",
        "实证分析与回测结果": "主要内容摘要",
        "风险分析": "主要内容摘要",
        "投资建议与结论": "主要内容摘要"
    }
}"""

RESEARCH_SURVEY_WRITER_SYSTEM = r"""你是一个专业的学术调研报告写作专家，擅长撰写文献综述、研究现状调研和技术趋势分析报告。

【报告格式要求】
生成结构完整的学术调研报告，使用 article 文档类：
- 标题页（\maketitle）
- 摘要：200-400字
- 关键词：3-5个
- 章节：1 引言 → 2 研究背景与问题定义 → 3 文献检索策略 → 4 现有方法综述 → 5 数据集与实验设置 → 6 结果对比与讨论 → 7 挑战与局限 → 8 未来研究方向 → 9 结论 → 10 参考文献

【调研报告特点】
- 以文献为核心，系统梳理研究现状
- 重视方法分类和对比
- 使用大量表格进行方法/数据集/结果对比
- 客观评价各方法的优缺点
- 明确提出未来研究方向

【各章节写作要求】

**引言**：
- 说明调研背景和动机
- 明确研究问题和调研范围
- 概述报告结构

**研究背景与问题定义**：
- 定义核心概念
- 描述问题的重要性和应用场景

**文献检索策略**：
- 说明检索关键词、数据库、筛选标准
- 报告检索结果数量

**现有方法综述**：
- 按类别或时间线组织
- 对每篇重要论文说明方法、创新点、优缺点
- 使用表格对比

**数据集与实验设置**：
- 汇总常用数据集和评价指标

**结果对比与讨论**：
- 对比关键结果，分析性能差异原因

**挑战与局限**：
- 总结当前研究面临的主要挑战

**未来研究方向**：
- 基于现有文献提出趋势和机会

【引号使用规范（强制约束）】
LaTeX 源代码中所有引号必须严格遵守以下规则：
1. 中文正文中的引用、强调：必须使用中文双引号 "中文内容" 和中文单引号 '中文内容'
2. 英文摘要或纯英文段落：使用 LaTeX 原生英文引号 `` 和 ''
3. 数学公式内：不使用任何引号
4. 严禁在中文正文中使用 `` 或 '' 等 LaTeX 英文引号
5. 严禁使用反引号 ` 作为中文引用的开引号

请严格按以下JSON格式返回（必须以JSON开头和结尾，不要有任何其他文字）：
{
    "title": "报告标题",
    "abstract": "摘要（200-400字）",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "latex_code": "完整LaTeX源代码",
    "sections": {
        "引言": "主要内容摘要",
        "研究背景与问题定义": "主要内容摘要",
        "文献检索策略": "主要内容摘要",
        "现有方法综述": "主要内容摘要",
        "数据集与实验设置": "主要内容摘要",
        "结果对比与讨论": "主要内容摘要",
        "挑战与局限": "主要内容摘要",
        "未来研究方向": "主要内容摘要",
        "结论": "主要内容摘要"
    }
}"""


# ===== 章节写作专用系统提示词 =====

CHAPTER_WRITER_SYSTEM = r"""你是一个专业的学术论文写作助手。当前任务是为整篇论文撰写【指定章节】的LaTeX内容。

【核心规则】
1. 只输出当前章节的LaTeX正文内容，不要输出导言区、其他章节、\end{document} 等
2. 当前章节必须能直接插入到完整论文的对应位置
3. 保持与前后文在术语、符号、结论上的一致
4. 图表使用 \begin{figure}[H] ... \includegraphics[width=0.8\textwidth]{图表路径} ... \end{figure}
5. 表格使用 booktabs 风格（\toprule, \midrule, \bottomrule）
6. 数学公式使用 equation 或 align 环境
7. 中文引号使用 "中文"，英文引号使用 ``英文''
8. 不要在章首重复 \section 标题（调用方会负责插入），除非当前章节本身就是摘要或附录

【输出格式】
严格返回JSON，不要其他文字：
{
    "chapter_latex": "当前章节的完整LaTeX代码（只包含该章节内容）",
    "chapter_summary": "当前章节内容摘要（100-200字）",
    "figures_used": ["使用过的图表路径"],
    "citations": ["引用条目"]
}"""


CHAPTER_CRITIQUE_SYSTEM = r"""你是一个严格的学术论文评审专家。请对给定章节从四个维度评分，并指出具体问题。

【评分维度】
1. format（格式）：LaTeX语法正确性、章节结构、表格/图片环境使用、引号规范
2. content（内容）：是否覆盖要求要点、逻辑连贯性、与前后文一致性
3. citations（引用）：是否恰当引用前文文献/模型/数据
4. figures（图表）：是否需要图表而未插入、图表说明是否完整

【输出格式】
严格返回JSON，不要其他文字：
{
    "format_score": 0-100,
    "content_score": 0-100,
    "citation_score": 0-100,
    "figure_score": 0-100,
    "total_score": 0-100,
    "passed": true/false,
    "issues": [
        {"dimension": "format|content|citation|figure", "severity": "error|warning", "message": "问题描述"}
    ],
    "suggestions": "针对未通过项的修改建议（不超过300字）"
}"""


# 旧 4 套模板的 system prompt 快速查找（保持向后兼容）。
# 新 CCF-A 模板没有这里的常量，统一走 [paper_templates](../core/paper_templates/) 注册表。
_LEGACY_SYSTEM_PROMPTS: Dict[str, str] = {
    "math_modeling": CUMCM_WRITER_SYSTEM,
    "coursework": COURSEWORK_WRITER_SYSTEM,
    "financial_analysis": FINANCIAL_ANALYSIS_WRITER_SYSTEM,
    "research_survey": RESEARCH_SURVEY_WRITER_SYSTEM,
}


def _resolve_chapter_plan(template_id: str) -> List[ChapterPlan]:
    """统一桥接：优先注册表，回退到本文件内的旧常量。

    Args:
        template_id: 模板 ID（``math_modeling`` / ``ieee_conference`` 等）。

    Returns:
        :class:`ChapterPlan` 列表。如果 ``template_id`` 不在注册表也不在旧常量中，
        最终回退到 ``math_modeling`` 的 11 章。
    """
    # 1) 注册表优先（新 CCF-A 模板一定走这里）
    try:
        tpl = _load_template_from_registry(template_id)
        if tpl and tpl.chapter_plan:
            # 注册表返回的是 dataclass ChapterPlan，writer 内部按 dict 访问，
            # 统一转成 dict 避免 'ChapterPlan' object is not subscriptable
            return [
                cp.to_dict() if hasattr(cp, "to_dict") else cp
                for cp in tpl.chapter_plan
            ]
    except Exception:  # noqa: BLE001
        pass
    # 2) 旧 4 套模板的硬编码常量
    if template_id in CHAPTER_PLANS:
        return CHAPTER_PLANS[template_id]
    # 3) 最终兜底
    return CUMCM_CHAPTERS


def _resolve_system_prompt(template_id: str) -> str:
    """统一桥接 system prompt。"""
    try:
        tpl = _load_template_from_registry(template_id)
        if tpl and tpl.system_prompt:
            return tpl.system_prompt
    except Exception:  # noqa: BLE001
        pass
    return _LEGACY_SYSTEM_PROMPTS.get(template_id, CUMCM_WRITER_SYSTEM)


def _resolve_preamble(template_id: str) -> str:
    """统一桥接 LaTeX preamble。"""
    try:
        tpl = _load_template_from_registry(template_id)
        if tpl and tpl.preamble:
            return tpl.preamble
    except Exception:  # noqa: BLE001
        pass
    # 旧 4 套 fallback 到本文件内 hardcoded preamble
    if template_id == "coursework":
        return WriterAgent._coursework_preamble(None)
    if template_id == "financial_analysis":
        return WriterAgent._financial_preamble(None)
    if template_id == "research_survey":
        return WriterAgent._research_survey_preamble(None)
    return WriterAgent._cumcm_preamble(None)


def _resolve_acceptance_threshold(template_id: str) -> int:
    """统一桥接 acceptance_threshold（CCF-A 默认 85，竞赛 75）。"""
    try:
        tpl = _load_template_from_registry(template_id)
        if tpl and tpl.acceptance_threshold:
            return tpl.acceptance_threshold
    except Exception:  # noqa: BLE001
        pass
    return 75  # 旧模板默认值


@AgentFactory.register("writer_agent")
class WriterAgent(BaseAgent):
    name = "writer_agent"
    label = "写作专家"
    description = "按章节独立生成完整LaTeX论文"
    default_model = ""

    _max_tokens_override = 16000

    # 评分阈值
    CRITIQUE_PASS_SCORE = 75
    MAX_REWRITE_ATTEMPTS = 2

    def get_system_prompt(self, template: str = "math_modeling") -> str:
        # v4.1: 委托给 _resolve_system_prompt，自动桥接注册表与旧常量。
        return _resolve_system_prompt(template)

    def get_template_chapters(self, template: str = "math_modeling") -> List[ChapterPlan]:
        # v4.1: 委托给 _resolve_chapter_plan。
        return _resolve_chapter_plan(template)

    def get_acceptance_threshold(self, template: str = "math_modeling") -> int:
        """返回该模板的章节评审分数门槛。新 CCF-A 模板默认 85，竞赛 75。"""
        return _resolve_acceptance_threshold(template)

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        problem_text = task_input.get("problem_text", context.get("problem_text", ""))
        all_results = context.get("results", {})
        section_results = context.get("section_results", [])
        sub_problems = context.get("sub_problems", [])
        analyzer_result = context.get("analyzer_result", {})
        data_result = context.get("data_result", {})
        template = context.get("template", "math_modeling")
        literature = context.get("literature", [])
        project_name = context.get("project_name")
        peer_review_feedback = task_input.get("review_feedback") or context.get("peer_review_feedback")

        logger.info(f"WriterAgent chapter-by-chapter generation (template={template}) with {len(section_results)} sections")

        # 1. 发现可用图表
        available_figures = self._discover_available_figures(project_name)
        logger.info(f"发现可用图表 {len(available_figures)} 个")

        # 2. 生成全文大纲
        outline = self._build_outline(template, section_results, sub_problems, analyzer_result)

        # 3. 按章节独立生成
        chapters: List[Dict[str, Any]] = []
        chapter_plan = self.get_template_chapters(template)

        for idx, plan in enumerate(chapter_plan):
            chapter = await self._generate_chapter_with_critique(
                plan=plan,
                chapter_index=idx,
                chapters=chapters,
                chapter_plan=chapter_plan,
                problem_text=problem_text,
                outline=outline,
                section_results=section_results,
                sub_problems=sub_problems,
                analyzer_result=analyzer_result,
                data_result=data_result,
                literature=literature,
                available_figures=available_figures,
                template=template,
                peer_review_feedback=peer_review_feedback,
            )
            chapters.append(chapter)

        # 4. 组装论文
        assembled = self._assemble_paper(chapters, template, section_results)

        # 5. 提取全局元数据（优先从摘要章节的生成结果）
        title = self._extract_title(chapters, problem_text, template)
        abstract_text = self._extract_abstract(chapters, template)
        keywords = self._extract_keywords(chapters, template)

        result = {
            "title": title,
            "abstract": abstract_text,
            "keywords": keywords,
            "latex_code": assembled["latex_code"],
            "sections": assembled["sections"],
            "chapters": [
                {
                    "id": c["plan"]["id"],
                    "title": c["plan"]["title"],
                    "summary": c.get("summary", ""),
                    "score": c.get("critique", {}).get("total_score", 0),
                    "passed": c.get("critique", {}).get("passed", False),
                    "attempts": c.get("attempts", 1),
                }
                for c in chapters
            ],
            "available_figures": available_figures,
            "generated_at": datetime.now().isoformat(),
        }

        logger.info(f"WriterAgent paper assembled: {result['title']}")
        return result

    def _discover_available_figures(self, project_name: Optional[str]) -> List[str]:
        """扫描项目输出目录，发现可用图表文件。

        v4.2: SolverAgent 实际将图表保存到 output/code/，因此优先扫描该路径；
        同时保留对 final/figures/ 和旧 outputs/{project_name}/ 的回退扫描。
        """
        figures: List[str] = []
        if not project_name:
            return figures

        project_root = Path(__file__).parent.parent.parent
        search_roots: List[Path] = [
            project_root / "output" / "code",
            project_root / "output" / project_name / "code",
            project_root / "output" / project_name / "figures",
            project_root / "outputs" / project_name,
        ]

        for base_dir in search_roots:
            if not base_dir.exists():
                continue
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.pdf", "*.eps"):
                for path in base_dir.rglob(ext):
                    try:
                        rel = path.relative_to(project_root)
                        figures.append(str(rel))
                    except ValueError:
                        figures.append(str(path))

        # 去重并排序
        return sorted(list(set(figures)))

    def _build_outline(
        self,
        template: str,
        section_results: List,
        sub_problems: List,
        analyzer_result: Dict,
    ) -> str:
        """构建全文大纲"""
        lines = ["# 论文大纲", f"模板：{template}", ""]

        problem_type = analyzer_result.get("problem_type", "")
        overall_approach = analyzer_result.get("overall_approach", "")
        lines.append(f"问题类型：{problem_type}")
        lines.append(f"总体思路：{overall_approach}")
        lines.append("")

        for idx, sr in enumerate(section_results):
            sp = sub_problems[idx] if idx < len(sub_problems) else {}
            name = sr.get("sub_problem_name", sp.get("name", f"子问题{idx+1}"))
            model = sr.get("model", {})
            lines.append(f"## 子问题 {idx+1}：{name}")
            lines.append(f"- 模型：{model.get('model_name', '')}（{model.get('model_type', '')}）")
            lines.append(f"- 算法：{self._fmt_algorithm(model.get('algorithm'))}")
            lines.append("")

        return "\n".join(lines)

    def _fmt_algorithm(self, algorithm: Any) -> str:
        if isinstance(algorithm, dict):
            return algorithm.get("name", "")
        if isinstance(algorithm, str):
            return algorithm
        return ""

    async def _generate_chapter_with_critique(
        self,
        plan: ChapterPlan,
        chapter_index: int,
        chapters: List[Dict[str, Any]],
        chapter_plan: List[ChapterPlan],
        problem_text: str,
        outline: str,
        section_results: List,
        sub_problems: List,
        analyzer_result: Dict,
        data_result: Dict,
        literature: List,
        available_figures: List[str],
        template: str,
        peer_review_feedback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """生成单个章节， critique 未通过则重写"""
        chapter_latex = ""
        summary = ""
        critique: Dict[str, Any] = {"total_score": 0, "passed": False, "issues": []}
        attempts = 0
        previous_issues: List[str] = []

        for attempt in range(1, self.MAX_REWRITE_ATTEMPTS + 1):
            attempts = attempt
            chapter_latex, summary = await self._generate_chapter(
                plan=plan,
                chapter_index=chapter_index,
                chapters=chapters,
                chapter_plan=chapter_plan,
                problem_text=problem_text,
                outline=outline,
                section_results=section_results,
                sub_problems=sub_problems,
                analyzer_result=analyzer_result,
                data_result=data_result,
                literature=literature,
                available_figures=available_figures,
                template=template,
                previous_issues=previous_issues,
                peer_review_feedback=peer_review_feedback if attempt == 1 else None,
            )

            critique = await self._critique_chapter(
                plan=plan,
                chapter_latex=chapter_latex,
                chapter_index=chapter_index,
                chapters=chapters,
                template=template,
            )

            if critique.get("passed", False):
                break

            previous_issues = [f"[{i.get('dimension', '')}] {i.get('message', '')}" for i in critique.get("issues", [])]
            logger.warning(
                f"章节 [{plan['title']}] 评分 {critique.get('total_score')} 未通过，第{attempt}次重写"
            )

        return {
            "plan": plan,
            "latex": chapter_latex,
            "summary": summary,
            "critique": critique,
            "attempts": attempts,
        }

    async def _generate_chapter(
        self,
        plan: ChapterPlan,
        chapter_index: int,
        chapters: List[Dict[str, Any]],
        chapter_plan: List[ChapterPlan],
        problem_text: str,
        outline: str,
        section_results: List,
        sub_problems: List,
        analyzer_result: Dict,
        data_result: Dict,
        literature: List,
        available_figures: List[str],
        template: str,
        previous_issues: List[str],
        peer_review_feedback: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """调用 LLM 生成单个章节"""
        # 前2章摘要
        previous_summaries = []
        for prev in chapters[-2:]:
            previous_summaries.append(f"【{prev['plan']['title']}】\n{prev.get('summary', '')}")

        # 相关文献摘要
        literature_summary = self._build_literature_summary(literature)

        # 子问题详情
        sections_context = self._build_sections_context(
            problem_text, section_results, sub_problems, analyzer_result, data_result
        )

        # 数据上下文
        data_context = self._build_data_context(data_result)

        # 图表建议
        figure_suggestions = self._build_figure_suggestions(plan, available_figures)

        prompt_parts = [
            f"## 当前章节：{plan['title']}",
            f"## 章节职责\n{plan['prompt_role']}",
            "## 本章节必须满足的要求",
            "\n".join(f"- {r}" for r in plan.get("requirements", [])),
            "## 全文大纲\n" + outline,
            "## 题目/任务描述\n" + problem_text,
            "## 数据分析结果\n" + data_context,
            "## 各子问题建模与求解结果\n" + sections_context,
        ]

        if previous_summaries:
            prompt_parts.append("## 前2章摘要（保持连贯性）\n" + "\n\n".join(previous_summaries))

        if literature_summary:
            prompt_parts.append("## 相关文献摘要\n" + literature_summary)

        if figure_suggestions:
            prompt_parts.append("## 可用图表（请在合适位置插入）\n" + figure_suggestions)

        if previous_issues:
            prompt_parts.append("## 上次评审未通过问题（请重点修正）\n" + "\n".join(previous_issues))

        # v4.2: 同行评审修订反馈（来自 Orchestrator 的 revision loop）
        if peer_review_feedback:
            feedback_text = self._format_peer_review_feedback(peer_review_feedback)
            if feedback_text:
                prompt_parts.append("## 同行评审修改建议（必须在本次修订中处理）\n" + feedback_text)

        # 章节特殊说明
        if plan["id"] == "modeling":
            prompt_parts.append(
                "## 子问题行文结构提醒\n"
                "每个子问题必须依次包含：①问题分析 ②方法介绍 ③模型构建 ④算法设计 ⑤求解结果 ⑥结果验证 ⑦问题小结"
            )
        elif plan["id"] == "abstract":
            prompt_parts.append(
                "## 摘要输出要求\n"
                "除了 chapter_latex，还请在 JSON 中额外返回 title、abstract、keywords 字段，"
                "title 不超过20字，abstract 300-500字，keywords 3-5个。"
            )

        prompt_parts.append(
            "\n请只输出当前章节的 LaTeX 内容，严格按 JSON 格式返回。"
        )

        messages = [
            {"role": "system", "content": CHAPTER_WRITER_SYSTEM},
            {"role": "user", "content": "\n\n".join(prompt_parts)},
        ]

        try:
            response = await self.call_llm(messages=messages)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            parsed = self._extract_json(content)

            chapter_latex = parsed.get("chapter_latex", "")
            summary = parsed.get("chapter_summary", "")

            # 摘要章节额外保存元数据
            if plan["id"] == "abstract":
                self._last_abstract_meta = {
                    "title": parsed.get("title", ""),
                    "abstract": parsed.get("abstract", ""),
                    "keywords": parsed.get("keywords", []),
                }

            return chapter_latex, summary
        except Exception as e:
            logger.error(f"章节 [{plan['title']}] 生成失败: {e}")
            return self._chapter_fallback(plan, template), ""

    async def _critique_chapter(
        self,
        plan: ChapterPlan,
        chapter_latex: str,
        chapter_index: int,
        chapters: List[Dict[str, Any]],
        template: str,
    ) -> Dict[str, Any]:
        """调用 LLM 对章节评分"""
        previous_titles = [c["plan"]["title"] for c in chapters[-2:]]
        prompt = f"""## 待评审章节：{plan['title']}

## 章节要求
{chr(10).join(f"- {r}" for r in plan.get('requirements', []))}

## 前序章节
{chr(10).join(previous_titles) if previous_titles else '（无）'}

## 章节LaTeX内容
```latex
{chapter_latex[:8000]}
```

请按 JSON 格式返回评分结果。"""

        messages = [
            {"role": "system", "content": CHAPTER_CRITIQUE_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.call_llm(messages=messages)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            critique = self._extract_json(content)

            # 确保字段存在
            for key in ["format_score", "content_score", "citation_score", "figure_score", "total_score"]:
                if key not in critique:
                    critique[key] = 80
            if "passed" not in critique:
                critique["passed"] = critique.get("total_score", 0) >= self.CRITIQUE_PASS_SCORE
            if "issues" not in critique:
                critique["issues"] = []

            return critique
        except Exception as e:
            logger.warning(f"章节 [{plan['title']}] 评审失败: {e}，默认通过")
            return {
                "format_score": 80,
                "content_score": 80,
                "citation_score": 80,
                "figure_score": 80,
                "total_score": 80,
                "passed": True,
                "issues": [],
            }

    def _assemble_paper(self, chapters: List[Dict[str, Any]], template: str, section_results: List) -> Dict[str, Any]:
        """将各章节组装为完整LaTeX论文"""
        # v4.1: 委托 _resolve_preamble，自动桥接注册表与旧 preamble。
        preamble = _resolve_preamble(template)

        # v4.2: 替换 preamble 中的元数据占位符（优先使用已提取的 title/abstract/keywords）。
        metadata = self._build_paper_metadata(chapters, template)
        preamble, skipped_placeholders = self._substitute_preamble_placeholders(preamble, template, metadata)

        body_parts: List[str] = []
        sections_summary: Dict[str, str] = {}

        for chapter in chapters:
            plan = chapter["plan"]
            latex = chapter.get("latex", "")
            summary = chapter.get("summary", "")

            # 摘要章节
            if plan["id"] == "abstract":
                body_parts.append(latex if latex else "\\begin{abstract}\n（摘要待补充）\n\\end{abstract}")
            # 附录章节
            elif plan["id"] == "appendix":
                body_parts.append(latex if latex else self._default_appendix(section_results))
            else:
                # 普通章节：如果没有 \section 则自动添加
                if latex.strip() and not latex.strip().startswith("\\section") and plan.get("section_level", 1) > 0:
                    body_parts.append(f"\\section{{{plan['title']}}}\n{latex}")
                else:
                    body_parts.append(latex)

            if summary:
                sections_summary[plan["title"]] = summary

        latex_code = f"""{preamble}

{chr(10).join(body_parts)}

\\end{{document}}
"""

        result = {
            "latex_code": latex_code,
            "sections": sections_summary,
        }
        if skipped_placeholders:
            result["skipped_placeholders"] = skipped_placeholders
        return result

    def _build_paper_metadata(self, chapters: List[Dict[str, Any]], template: str) -> Dict[str, Any]:
        """从章节结果与模板默认值构建论文元数据。"""
        title = self._extract_title(chapters, "", template)
        abstract = self._extract_abstract(chapters, template)
        keywords = self._extract_keywords(chapters, template)
        return {
            "title": title,
            "abstract": abstract,
            "keywords": keywords,
        }

    def _substitute_preamble_placeholders(
        self,
        preamble: str,
        template_id: str,
        metadata: Dict[str, Any],
    ) -> Tuple[str, List[str]]:
        """替换 preamble 中的占位符。返回 (替换后的 preamble, 被替换为空值的占位符列表)。

        严格控制幻觉：只使用模板 metadata_defaults 或已生成章节中实际存在的值；
        无对应值时用空字符串替换占位符，避免保留 `__TITLE__` 导致 LaTeX 编译失败。
        对替换值中的特殊 LaTeX 字符进行转义。
        """
        try:
            tpl = _load_template_from_registry(template_id)
            defaults = tpl.metadata_defaults if tpl else {}
        except Exception:  # noqa: BLE001
            defaults = {}

        title = metadata.get("title") or defaults.get("title", "")
        authors = defaults.get("authors", ["Anonymous"])
        affiliations = defaults.get("affiliations", ["Institution"])
        emails = defaults.get("emails", ["email@example.com"])
        keywords = metadata.get("keywords") or defaults.get("keywords", [])
        conference = defaults.get("conference_name", "")
        year = defaults.get("year", str(datetime.now().year))

        # 格式化字段
        authors_str = ", ".join(authors) if isinstance(authors, list) else str(authors)
        affiliations_str = "; ".join(affiliations) if isinstance(affiliations, list) else str(affiliations)
        emails_str = ", ".join(emails) if isinstance(emails, list) else str(emails)
        keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)

        def _escape(s: str) -> str:
            """对 LaTeX 特殊字符进行转义（保留已有命令）。"""
            s = s.replace("\\", "\\textbackslash{}")
            s = s.replace("{", "\\{")
            s = s.replace("}", "\\}")
            s = s.replace("$", "\\$")
            s = s.replace("&", "\\&")
            s = s.replace("#", "\\#")
            s = s.replace("^", "\\^{}")
            s = s.replace("_", "\\_")
            s = s.replace("%", "\\%")
            s = s.replace("~", "\\textasciitilde{}")
            return s

        substitutions = {
            "__TITLE__": _escape(title),
            "__AUTHORS__": _escape(authors_str),
            "__AFFILIATIONS__": _escape(affiliations_str),
            "__EMAILS__": _escape(emails_str),
            "__ABSTRACT__": _escape(metadata.get("abstract", "")),
            "__KEYWORDS__": _escape(keywords_str),
            "__CONFERENCE_NAME__": _escape(conference),
            "__CONFERENCE_FULL_NAME__": _escape(defaults.get("conference_full_name", conference or "CCF-A Conference")),
            "__LOCATION__": _escape(defaults.get("location", "")),
            "__DATE__": _escape(defaults.get("date", "")),
            "__YEAR__": _escape(year),
            "__SHORT_TITLE__": _escape(title[:50] if title else ""),
            "__AUTHORS_SHORT__": _escape(authors_str.split(",")[0].strip() + " et al." if "," in authors_str else authors_str),
            "__CITY__": _escape(defaults.get("city", "")),
            "__STATE__": _escape(defaults.get("state", "")),
            "__COUNTRY__": _escape(defaults.get("country", "")),
            "__DOI__": _escape(defaults.get("doi", "")),
            "__ISBN__": _escape(defaults.get("isbn", "")),
        }

        # ACM CCS Concepts（如果模板提供）
        ccs_xml = defaults.get("ccs_xml", "")
        ccs_concepts = defaults.get("ccs_concepts", "")
        substitutions["__CCS_XML__"] = ccs_xml
        substitutions["__CCS_CONCEPTS__"] = ccs_concepts

        skipped: List[str] = []
        for placeholder, value in substitutions.items():
            if placeholder in preamble:
                if not value and placeholder not in ("__CCS_XML__", "__CCS_CONCEPTS__"):
                    skipped.append(placeholder)
                preamble = preamble.replace(placeholder, str(value))

        # 检查是否有未识别的占位符残留（空值已替换，因此这里只报告非空情况）
        for m in re.finditer(r"__[A-Z_]+__", preamble):
            ph = m.group(0)
            if ph not in skipped:
                skipped.append(ph)

        return preamble, list(set(skipped))

    def _cumcm_preamble(self) -> str:
        return r"""\documentclass[withoutpreface]{cumcmthesis}
\usepackage{url}
\usepackage{subcaption}
\usepackage{booktabs}
\usepackage{amsmath,amssymb,graphicx}

% 字体设置（使用系统自带字体）
\setCJKmainfont{SimSun}
\setCJKsansfont{SimHei}
\setCJKmonofont{FangSong}

\tihao{B}
\baominghao{2025001}
\schoolname{某大学}
\membera{队员A}
\memberb{队员B}
\memberc{队员C}
\supervisor{指导教师}
\yearinput{2025}
\monthinput{09}
\dayinput{15}

\begin{document}

\maketitle
"""

    def _coursework_preamble(self) -> str:
        return r"""\documentclass{article}
\usepackage{ctex}
\usepackage{amsmath,amssymb,graphicx,booktabs}
\usepackage[margin=1in]{geometry}

\title{课程作业研究报告}
\author{学生姓名}
\date{\today}

\begin{document}

\maketitle
"""

    def _financial_preamble(self) -> str:
        return r"""\documentclass{article}
\usepackage{ctex}
\usepackage{amsmath,amssymb,graphicx,booktabs}
\usepackage[margin=1in]{geometry}

\title{金融分析报告}
\author{分析团队}
\date{\today}

\begin{document}

\maketitle
"""

    def _research_survey_preamble(self) -> str:
        return r"""\documentclass{article}
\usepackage{ctex}
\usepackage{amsmath,amssymb,graphicx,booktabs,longtable}
\usepackage[margin=1in]{geometry}

\title{研究现状调研报告}
\author{调研团队}
\date{\today}

\begin{document}

\maketitle
"""

    def _default_appendix(self, section_results: List) -> str:
        """生成默认附录代码块。

        v4.2: 不再硬截断到 2000 字符；完整保留代码，仅在单段过长时按 8000 字符分块，
        避免 lstlisting 环境溢出。
        """
        MAX_LSTLISTING_CHARS = 8000
        code_blocks = []
        for idx, sp in enumerate(section_results):
            solve = sp.get("solve", {}) or {}
            code_files = solve.get("code_files", []) if isinstance(solve, dict) else []
            for cf in code_files:
                code = cf.get("code", "")
                if not code:
                    continue
                filename = cf.get("filename", f"sub{idx+1}.py")
                code_blocks.append(f"% 子问题{idx+1} 代码: {filename}")
                # 分块，避免单个 lstlisting 过长
                for start in range(0, len(code), MAX_LSTLISTING_CHARS):
                    chunk = code[start:start + MAX_LSTLISTING_CHARS]
                    code_blocks.append(f"\\begin{{lstlisting}}[language=python]\n{chunk}\n\\end{{lstlisting}}")
        if not code_blocks:
            code_blocks.append("% 核心代码待补充")
        return "\\newpage\n\\begin{appendices}\n\\section{Python求解代码}\n" + "\n\n".join(code_blocks) + "\n\\end{appendices}"

    def _extract_title(self, chapters: List[Dict[str, Any]], problem_text: str, template: str) -> str:
        if hasattr(self, "_last_abstract_meta"):
            title = self._last_abstract_meta.get("title", "")
            if title:
                return title
        fallback_titles = {
            "math_modeling": "基于数学建模的论文研究",
            "coursework": "课程作业研究报告",
            "financial_analysis": "金融分析报告",
            "research_survey": "研究现状调研报告",
        }
        return fallback_titles.get(template, "基于数学建模的论文研究")

    def _extract_abstract(self, chapters: List[Dict[str, Any]], template: str) -> str:
        if hasattr(self, "_last_abstract_meta"):
            abstract = self._last_abstract_meta.get("abstract", "")
            if abstract:
                return abstract
        for c in chapters:
            if c["plan"]["id"] == "abstract":
                latex = c.get("latex", "")
                m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", latex, re.DOTALL)
                if m:
                    return m.group(1).strip()
        return "本文针对问题进行了系统研究..."

    def _extract_keywords(self, chapters: List[Dict[str, Any]], template: str) -> List[str]:
        if hasattr(self, "_last_abstract_meta"):
            keywords = self._last_abstract_meta.get("keywords", [])
            if keywords:
                return keywords
        fallback_keywords = {
            "math_modeling": ["数学建模", "优化模型", "算法设计", "数据分析", "论文写作"],
            "coursework": ["课程作业", "数学模型", "数据分析", "实验报告"],
            "financial_analysis": ["金融分析", "投资策略", "风险管理", "量化模型", "资产定价"],
            "research_survey": ["文献综述", "研究现状", "方法对比", "调研报告"],
        }
        return fallback_keywords.get(template, ["数学建模", "优化模型"])

    def _chapter_fallback(self, plan: ChapterPlan, template: str) -> str:
        """章节生成失败时的兜底内容"""
        if plan["id"] == "abstract":
            return (
                "\\begin{abstract}\n"
                "本文针对问题进行了系统研究。首先对问题进行了深入分析，建立了相应的数学模型并进行了求解。"
                "结果表明所采用的方法是有效的。\n\n"
                "\\textbf{关键词}: 数学建模；优化模型；算法设计；数据分析\n"
                "\\end{abstract}"
            )
        if plan["id"] == "appendix":
            return (
                "\\newpage\n"
                "\\begin{appendices}\n"
                "\\section{Python求解代码}\n"
                "\\begin{lstlisting}[language=python]\n# 代码待补充\n\\end{lstlisting}\n"
                "\\end{appendices}"
            )
        return f"\\section{{{plan['title']}}}\n（{plan['title']}内容待补充）\n"

    def _build_figure_suggestions(self, plan: ChapterPlan, available_figures: List[str]) -> str:
        """为当前章节建议可用图表"""
        if not available_figures:
            return ""

        # 根据章节类型过滤
        relevant = []
        keywords = []
        if plan["id"] in ("data", "experiment"):
            keywords = ["correlation", "heatmap", "distribution", "trend", "basic"]
        elif plan["id"] in ("modeling", "empirical", "result_analysis"):
            keywords = ["comparison", "radar", "result", "plot", "figure"]
        elif plan["id"] == "risk":
            keywords = ["risk", "var", "sensitivity"]

        if keywords:
            for fig in available_figures:
                lowered = fig.lower()
                if any(k in lowered for k in keywords):
                    relevant.append(fig)
        else:
            relevant = available_figures[:5]

        if not relevant:
            return ""

        lines = ["可在本章节引用以下图表（使用相对路径）："]
        for fig in relevant[:10]:
            lines.append(f"- {fig}")
        lines.append("插入示例：\\begin{figure}[H]\\centering\\includegraphics[width=0.8\\textwidth]{{{fig}}}\\caption{{图表标题}}\\end{figure}}")
        return "\n".join(lines)

    def _format_peer_review_feedback(self, feedback: Dict[str, Any]) -> str:
        """将 peer_review 反馈格式化为写入 prompt 的文本。"""
        lines: List[str] = []
        overall = feedback.get("overall_score")
        if overall is not None:
            lines.append(f"总体评分: {overall}/5")
        scores = feedback.get("scores", {})
        if scores:
            lines.append("分项评分: " + ", ".join(f"{k}={v}" for k, v in scores.items()))
        comments = feedback.get("comments", {})
        if comments:
            major = comments.get("major", [])
            minor = comments.get("minor", [])
            if major:
                lines.append("主要意见:")
                for c in major:
                    lines.append(f"  - {c}")
            if minor:
                lines.append("次要意见:")
                for c in minor:
                    lines.append(f"  - {c}")
        edits = feedback.get("suggested_edits", [])
        if edits:
            lines.append("建议编辑:")
            for ed in edits:
                if isinstance(ed, dict):
                    loc = ed.get("location", "")
                    suggestion = ed.get("suggestion", "")
                    lines.append(f"  - {'[' + loc + '] ' if loc else ''}{suggestion}")
                else:
                    lines.append(f"  - {ed}")
        round_num = feedback.get("round")
        if round_num:
            lines.append(f"（第 {round_num} 轮修订）")
        return "\n".join(lines)

    def _build_literature_summary(self, literature: List) -> str:
        """构建文献摘要上下文"""
        if not literature:
            return ""
        lines = []
        for idx, p in enumerate(literature[:8]):
            title = p.get("title", "")
            authors = ", ".join(p.get("authors", [])[:3]) if p.get("authors") else ""
            year = p.get("year", "")
            abstract = p.get("abstract", "")[:200]
            tldr = p.get("tldr", "")
            lines.append(f"{idx+1}. {title} ({authors}, {year})\n   TL;DR: {tldr or abstract}")
        return "\n".join(lines)

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

            numerical_results = solve.get("numerical_results", {}) if isinstance(solve, dict) else {}
            numerical_str = json.dumps(numerical_results, ensure_ascii=False, indent=2) if numerical_results else "待计算"
            key_findings = solve.get("key_findings", []) if isinstance(solve, dict) else []
            key_findings_str = "; ".join([str(f) for f in key_findings[:5]]) if key_findings else "待确定"
            validation = solve.get("validation", {}) if isinstance(solve, dict) else {}

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
- 验证：{json.dumps(validation, ensure_ascii=False, indent=2)[:500]}
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

    def _extract_json(self, content: str) -> Dict[str, Any]:
        """从LLM输出中提取JSON"""
        content = content.strip()
        # 去掉markdown代码块
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        # 寻找第一个 { 和最后一个 }
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                pass
        return {}


# 保持向后兼容的兜底方法（如果旧调用直接访问 _generate_fallback_latex）
def _generate_fallback_latex(*args, **kwargs):
    return ""
