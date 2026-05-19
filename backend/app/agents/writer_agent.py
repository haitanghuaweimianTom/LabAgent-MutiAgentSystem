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
    % ★ 每个子问题的 subsection 内部行文结构（必须按以下顺序逐层展开）：
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
    % ★ 子问题之间的衔接：
    %   - 后续子问题如果依赖前一个子问题的结果，要明确写出"基于上一节的结果……"
    %   - 不要让各个子问题看起来像完全独立的论文
    %   - 围绕解决问题的主线逐步深入
    \subsection{4.1 XXX模型（对应子问题1）}
    \subsection{4.2 XXX模型（对应子问题2）}
    \subsection{4.3 XXX模型（对应子问题3）}
    % 如有更多子问题，依次添加 \subsection

\section{5 结果分析}
    % 对各问题结果的定性和规律性讨论
    % 数值结果配合文字解释，说明实际含义
    % 多个方案可列表比较
    % 从全局视角分析各问题结果之间的关系

\section{6 可靠性分析}
    \subsection{6.1 模型检验}       % 准确性检验（与实际数据或已知结果对比）
    \subsection{6.2 敏感性分析}     % 关键参数变动对结果的影响
    % 即使题目未明确要求，对于工程领域的实际问题都必须做

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
1. 章节编号必须连续（1→2→3→...→9），不得跳过或重复
2. "模型的建立与求解"必须是唯一的 \section（第4章），所有子问题在其内部用 \subsection 组织
3. 不得将每个子问题拆分为独立的 \section（这是常见错误！评委批评的"问答式八股文"）
4. 每个子问题末尾必须有"问题小结"，简短总结该问题的核心结论
5. 如果使用经典算法/模型（如LSTM、随机森林、回归等），必须先介绍方法原理再应用
6. 多种方法/模型之间要做对比验证，择优使用
7. 摘要中不要出现复杂公式和表格
8. 表格用 booktabs 风格（\toprule, \midrule, \bottomrule）
9. 图形标题放在图形下方
10. 论文必须是可以用 xelatex 编译的完整LaTeX代码
11. 数学公式用 equation 或 align 环境
12. 能用初等方法解决就不用高等方法；能用简单方法就不用复杂方法

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
- ★ 每个子问题的叙述必须完整包含以下七个环节（缺一不可）：
  ① 问题分析：本子问题的具体分析和建模思路
  ② 方法介绍：如使用经典算法/模型，先说明原理（如LSTM、随机森林、雨流计数法等）
  ③ 模型构建：决策变量→目标函数/方程→约束条件→公式含义解释
  ④ 算法设计：求解方法原理→算法步骤→参数设置
  ⑤ 求解结果：数值结果+文字解读（"从结果可以看出……"）
  ⑥ 结果验证：多模型对比验证或与已知结果对比
  ⑦ 问题小结：简短总结本子问题的核心结论
- ★ 子问题之间必须衔接：如果后续问题依赖前面结果，写明"基于上一节的结果……"

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

请生成完整论文JSON输出，严格按以下格式返回（必须以JSON开头和结尾，不要有任何其他文字）：
{
    "title": "论文标题（简洁准确，不超过20字，避免使用公式和符号）",
    "abstract": "摘要（300-500字，包含：方法→模型→求解→结果→结论）",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
    "latex_code": "完整LaTeX源代码（包含导言区、承诺书、摘要、正文、上述全部9个章节、参考文献、附录）",
    "sections": {
        "问题重述": "主要内容摘要",
        "问题分析": "主要内容摘要",
        "模型假设与符号说明": "主要内容摘要",
        "模型的建立与求解": "主要内容摘要，含各子问题的七环节：问题分析→方法介绍→模型构建→算法设计→求解结果→结果验证→问题小结",
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
- 语言风格：学术但简洁，适合课程作业提交
- 篇幅：适中，不需要像竞赛论文那样冗长
- 重点：方法原理、实现过程、结果分析
- 不要求承诺书页

【各章节写作要求（课程作业/学术报告风格）】

**引言/研究背景**：
- 说明研究的目的和动机：为什么要做这个研究？问题来自哪里？
- 简述相关领域现状和已有方法（简要文献回顾即可，不需要像竞赛论文那样详细）
- 明确本文要解决的问题和主要贡献
- 语言风格：像学术报告一样条理清晰

**问题描述**：
- 用自己的语言重新描述要解决的问题
- 列出已知条件、约束和目标
- 如果问题来自实际场景，说明背景和数据特点
- 切忌照抄原题，要体现自己的理解

**方法与模型**：
- 先说明为什么选择这个方法：与问题的匹配度、相比其他方法的优势
- 详细描述方法的原理和数学推导过程（这是课程作业的重点）
- 列出模型假设，并简要说明合理性
- 符号说明要清晰，避免一个符号表示多个含义
- 如果是经典方法（如回归、聚类、优化），要写出核心公式和算法步骤

**实验/求解过程**：
- 说明实验环境、数据来源、预处理步骤
- 详细描述求解步骤和实现方法
- 如果使用了编程实现，说明使用的语言和关键库
- 代码可以放在正文中（简短）或附录中（较长）

**结果分析**：
- 数值结果必须配合文字解释，说明实际含义
- 避免只放图表不解释，每个图表都要有"从结果可以看出……"的分析
- 如果有多个方案或参数设置，进行对比分析
- 讨论结果的局限性和不足之处

**总结与展望**：
- 简要回顾研究的主要工作和主要发现
- 提出可以进一步改进的方向
- 不需要像竞赛论文那样详细评价模型优缺点

【重要】
1. 论文必须是可以用 xelatex 编译的完整LaTeX代码
2. 数学公式用 equation 或 align 环境
3. 表格用 booktabs 风格
4. 章节编号必须连续，不能重复或跳跃
5. 子问题使用 \subsection 区分，不要为每个子问题单独创建 \section
6. 课程作业重点在于展示对方法原理的理解，不要跳过推导过程
7. 能用简单方法就不用复杂方法，能被更多人看懂的方法更好

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

FINANCIAL_ANALYSIS_WRITER_SYSTEM = r"""你是一个专业的金融分析报告写作专家，擅长撰写投资分析、风险评估、资产定价、量化策略、投资组合优化等金融领域的分析报告。

【报告格式要求】
生成专业的金融分析报告，使用 article 文档类：
- 封面/标题页（\maketitle）
- 执行摘要（Executive Summary）：200-400字
- 关键词：3-5个
- 章节：1 投资背景与市场概述 → 2 数据描述与预处理 → 3 分析框架与方法 → 4 资产/策略建模 → 5 实证分析与回测结果 → 6 风险分析 → 7 投资建议与结论 → 8 参考文献
- 附录：代码、补充数据表格

【金融分析报告特点】
- 数据驱动：以数据和分析为基础，大量使用图表、数据表格支撑论点
- 风险意识：必须包含定量风险评估（VaR、CVaR、压力测试、灵敏度分析等）
- 实用性：给出明确可执行的投资建议或策略结论
- 专业术语：正确使用金融学术语（如收益率、波动率、夏普比率、最大回撤等）
- 可复现性：说明数据来源、处理步骤、参数设置，使分析可被他人复现

【各章节写作要求（金融分析报告风格）】

**执行摘要（Executive Summary）**：
- 用精炼语言概括全文核心：研究目的→数据来源→分析方法→关键发现→投资建议
- 投资建议必须明确具体（如"建议配置XX资产XX%"，而非"可适当关注"）
- 摘要中应包含关键数值结果（如预期收益率、风险指标、夏普比率等）
- 不要出现复杂公式和冗长推导
- 相当于整份报告的"电梯演讲"——读者只看摘要也能知道核心结论

**投资背景与市场概述**：
- 说明研究的实际动机：为什么要分析这个问题？有什么实际意义？
- 描述相关市场的宏观背景（如政策环境、经济周期、行业趋势等）
- 简述当前市场的热点、争议或不确定性
- 如果涉及特定资产类别（股票、债券、商品、衍生品等），说明其基本特征
- 文献回顾要聚焦，不需要面面俱到，选择与本文最相关的几篇即可
- 明确本文的研究目标和主要贡献（创新点）

**数据描述与预处理**：
- 说明数据来源（数据库名称、时间范围、频率、样本量）
- 描述性统计：均值、标准差、偏度、峰度、最大/最小值等
- 数据预处理步骤：缺失值处理、异常值检测与处理、平稳性检验（ADF检验等）
- 如果做了数据变换（如对数收益率、差分、标准化），说明原因和公式
- 用图表展示数据的分布特征、趋势特征（如时间序列图、直方图、相关系数热力图等）
- 每个图表都必须配合文字解释，说明"从数据中可以看出……"

**分析框架与方法**：
- 先说明为什么选择这个方法/模型：与问题的匹配度、相比其他方法的优势
- 如果涉及经典金融模型（如CAPM、Fama-French、Black-Scholes、VaR模型等），写出核心公式和假设
- 列出模型假设，并说明其在当前问题中的合理性（如市场有效性、正态性假设等）
- 符号说明要清晰，金融领域的符号有约定俗成的写法（如$r_t$表示收益率，$\sigma$表示波动率）
- 说明模型可能存在的局限性和适用条件
- 如果使用了多种方法，说明它们之间的关系和各自的适用场景

**资产/策略建模**：
- 详细描述模型的构建过程：从理论基础到具体公式推导
- 如果是量化策略，说明策略逻辑、信号生成、持仓规则、调仓频率等
- 如果是投资组合优化，说明目标函数（如最大化夏普比率、最小化方差等）和约束条件
- 如果是资产定价模型，说明定价因子、风险溢价、贴现率等
- 如果是预测模型（如时间序列、机器学习），说明特征工程、模型选择、训练/测试集划分
- 参数估计方法要说明（如OLS、MLE、贝叶斯等）
- 模型推导要严谨，关键步骤不能跳过

**实证分析与回测结果**：
- 回测/实证结果必须定量给出：收益率、波动率、夏普比率、最大回撤、胜率等关键指标
- 用表格对比不同模型/策略的表现（booktabs风格）
- 用图表展示结果（如累计收益曲线、净值曲线、收益分布直方图等）
- 每个图表都必须有文字解释，说明经济含义和实际意义
- 如果做了稳健性检验（如改变时间窗口、改变参数、使用不同基准），报告检验结果
- 结果分析要客观：既报告成功的方面，也报告不理想的方面
- 如果是预测任务，报告预测精度指标（如MAE、RMSE、MAPE、方向准确率等）

**风险分析（不可或缺）**：
- VaR分析：在给定置信水平（如95%、99%）下的风险价值，说明计算方法（历史模拟法、参数法、蒙特卡洛法）
- CVaR/ES：条件风险价值，衡量尾部风险
- 压力测试：在极端情景下的表现（如2008年金融危机、2020年疫情冲击等历史情景，或自定义情景）
- 灵敏度分析：关键参数变化对结果的影响（如利率变动±1%、波动率变动±20%等）
- 风险指标要明确数值，不能只说"风险可控"——具体是多少？
- 如果涉及杠杆，说明杠杆率和保证金要求
- 流动性风险、模型风险也要适当讨论

**投资建议与结论**：
- 投资建议必须明确、具体、可操作，避免模糊表述
- 建议应该基于前文分析结果，前后一致，不能脱离分析凭空给出
- 如果建议配置资产，给出具体比例和理由
- 如果建议某种策略，说明适用条件和触发条件
- 风险提示不可或缺：明确指出可能面临的主要风险和应对建议
- 总结全文主要发现和贡献
- 提出可以进一步研究的方向（如扩大样本、引入新因子、改进模型等）

【重要】
1. 报告必须是可以用 xelatex 编译的完整LaTeX代码
2. 数学公式用 equation 或 align 环境
3. 表格用 booktabs 风格（\toprule, \midrule, \bottomrule）
4. 必须包含数据可视化占位（如 \includegraphics[width=0.8\textwidth]{figure1}），图表标题放在图/表下方
5. 章节编号必须连续，不能重复或跳跃
6. 子问题使用 \subsection 区分
7. 图表必须有文字解释，不能只给出而不分析
8. 金融指标和专业术语要准确使用
9. 能定量给出的就定量，不要只作定性描述

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
        "投资背景与市场概述": "主要内容摘要",
        "数据描述与预处理": "主要内容摘要",
        "分析框架与方法": "主要内容摘要",
        "资产/策略建模": "主要内容摘要",
        "实证分析与回测结果": "主要内容摘要",
        "风险分析": "主要内容摘要",
        "投资建议与结论": "主要内容摘要"
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
