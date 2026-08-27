"""
论文模板系统
============

支持多种论文类型的通用模板：
- 数学建模论文 (Math Modeling)
- 课程作业论文 (Coursework)
- 金融分析论文 (Financial Analysis)
- NeurIPS 2024 (ML/CCF-A)
- IEEE Conference (Systems/Security/CCF-A)
- ACM SIGCONF (Graphics/Networking/CCF-A)
- Springer LNCS (Computer Science/CCF-B)
- Research Survey (文献综述)

每个模板定义：
- 大纲结构（章节列表）
- 章节相关性映射（哪些数据参与哪一章）
- 字数要求与生成策略
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class ChapterSpec:
    """章节规格"""
    id: str                      # 章节ID，如 "abstract"
    title: str                   # 章节标题
    level: int = 1               # 层级（1=章，2=节）
    min_chars: int = 1000        # 最少中文字数
    max_chars: int = 5000        # 最多中文字数
    target_chars: int = 2000     # 目标中文字数
    relevance_keys: List[str] = field(default_factory=list)
    # relevance_keys: 参与此章节生成的上下文键
    # 如 ["analysis", "modeling", "execution_result"]
    prompt_template: str = ""    # 章节专属 prompt 模板（可选）
    requires_coding: bool = False  # 是否依赖代码执行结果
    requires_data: bool = False    # 是否依赖数据文件


class PaperTemplate(ABC):
    """论文模板基类"""

    name: str = "base"
    description: str = "base"
    # 是否为 CCF-A 顶会模板。CCF-A 模板会强制注入"严谨性检查清单"并触发
    # ccf_a_rigor 维度的批判（见 CritiqueEngine），用以堵住常见拒稿点：
    # 复现性、回测/OOS 验证、基线对比、消融、敏感性、因果识别、异质性、
    # 网络传染、反馈环、定义形式化。
    is_ccf_a: bool = False

    @abstractmethod
    def get_outline(self) -> List[ChapterSpec]:
        """获取论文大纲"""
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """获取论文写作系统提示词"""
        pass

    def get_rigor_checklist(self) -> List[str]:
        """返回 CCF-A 严谨性硬性检查清单（注入到各章 prompt + critique）。

        基类返回空列表；CCF-A 模板覆写。每条以"必须"开头，便于批判引擎核对。
        """
        return []

    def requires_rigor_critique(self, chapter_id: str) -> bool:
        """该章节是否需要走 ccf_a_rigor 批判（默认 method/experiments/appendix）。"""
        return self.is_ccf_a and chapter_id in {
            "method", "experiments", "appendix", "discussion", "evaluation",
        }

    def get_relevance_context(
        self,
        chapter: ChapterSpec,
        context: Dict[str, Any],
        max_chars: int = 4000,
    ) -> str:
        """
        根据章节相关性映射提取上下文
        避免将所有历史内容堆入 prompt
        """
        parts = []
        total = 0

        for key in chapter.relevance_keys:
            value = context.get(key)
            if not value:
                continue

            if isinstance(value, dict):
                text = f"【{key}】\n{self._dict_to_text(value)}\n\n"
            elif isinstance(value, str):
                text = f"【{key}】\n{value}\n\n"
            else:
                text = f"【{key}】\n{str(value)}\n\n"

            if total + len(text) > max_chars:
                remaining = max_chars - total
                if remaining > 100:
                    parts.append(text[:remaining])
                break

            parts.append(text)
            total += len(text)

        return "\n".join(parts)

    def _dict_to_text(self, d: Dict, indent: int = 0) -> str:
        """将字典转为可读文本"""
        lines = []
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append(f"{'  ' * indent}{k}:")
                lines.append(self._dict_to_text(v, indent + 1))
            elif isinstance(v, list) and len(v) > 0 and not isinstance(v[0], dict):
                lines.append(f"{'  ' * indent}{k}: {', '.join(str(x) for x in v[:10])}")
            else:
                text = str(v)
                if len(text) > 500:
                    text = text[:500] + "..."
                lines.append(f"{'  ' * indent}{k}: {text}")
        return "\n".join(lines)


class MathModelingTemplate(PaperTemplate):
    """
    数学建模论文模板

    标准 MCM/ICM 结构：
    摘要 → 问题重述 → 问题分析 → 模型假设 → 符号说明 →
    模型建立 → 模型求解 → 结果分析 → 灵敏度分析 →
    模型评价与改进 → 参考文献 → 附录
    """

    name = "math_modeling"
    description = "数学建模竞赛论文（MCM/ICM标准格式）"

    def get_system_prompt(self) -> str:
        return """你是一位资深的数学建模竞赛论文写作专家，曾获得MCM/ICM Outstanding Winner。

写作要求：
1. 语言严谨、逻辑清晰、论证充分，避免空洞的套话
2. 公式必须使用 LaTeX 格式（如 $E=mc^2$ 或 $$...$$），公式必须编号
3. 数据必须真实，不得编造；若引用计算结果，必须准确
4. 每个段落都要有实质性内容，禁止用"综上所述"等无信息量的填充
5. 模型建立部分必须有完整的推导过程，不能只有结论
6. 结果分析必须具体到数值，配合表格展示
7. 灵敏度分析必须改变参数并给出定量结果
8. 使用学术中文写作风格，术语准确
9. 论文正文目标约15-18页（约10,000-13,000中文字符），内容精炼紧凑
10. 严格控制篇幅，每个章节不超过设定的最大字数"""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract",
                title="摘要",
                level=1,
                min_chars=300,
                target_chars=500,
                max_chars=700,
                relevance_keys=["problem_text", "analysis", "modeling", "execution_result", "result_analysis"],
            ),
            ChapterSpec(
                id="problem_restated",
                title="一、问题重述",
                level=1,
                min_chars=400,
                target_chars=600,
                max_chars=900,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="problem_analysis",
                title="二、问题分析",
                level=1,
                min_chars=700,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["problem_text", "analysis", "sub_problems"],
            ),
            ChapterSpec(
                id="assumptions",
                title="三、模型假设",
                level=1,
                min_chars=350,
                target_chars=500,
                max_chars=800,
                relevance_keys=["analysis", "modeling"],
            ),
            ChapterSpec(
                id="notations",
                title="四、符号说明",
                level=1,
                min_chars=200,
                target_chars=350,
                max_chars=500,
                relevance_keys=["modeling"],
            ),
            ChapterSpec(
                id="model_establishment",
                title="五、模型的建立",
                level=1,
                min_chars=1000,
                target_chars=1400,
                max_chars=2000,
                relevance_keys=["problem_text", "analysis", "modeling", "formulas"],
            ),
            ChapterSpec(
                id="model_solution",
                title="六、模型的求解",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=1800,
                relevance_keys=["algorithm", "code", "execution_result"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="result_analysis",
                title="七、结果分析",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=1800,
                relevance_keys=["execution_result", "result_analysis", "charts"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="sensitivity",
                title="八、灵敏度分析",
                level=1,
                min_chars=500,
                target_chars=800,
                max_chars=1200,
                relevance_keys=["modeling", "execution_result", "result_analysis"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="evaluation",
                title="九、模型评价与改进",
                level=1,
                min_chars=400,
                target_chars=600,
                max_chars=1000,
                relevance_keys=["modeling", "algorithm", "result_analysis"],
            ),
            ChapterSpec(
                id="references",
                title="参考文献",
                level=1,
                min_chars=200,
                target_chars=350,
                max_chars=600,
                relevance_keys=["problem_text", "modeling"],
            ),
            ChapterSpec(
                id="appendix",
                title="附录",
                level=1,
                min_chars=200,
                target_chars=400,
                max_chars=800,
                relevance_keys=["code", "charts", "execution_result"],
                requires_coding=True,
            ),
        ]


class CourseworkTemplate(PaperTemplate):
    """
    课程作业论文模板

    结构：
    摘要 → 引言 → 理论基础 → 问题描述 → 方法设计 →
    实验/计算 → 结果讨论 → 结论 → 参考文献
    """

    name = "coursework"
    description = "一般课程作业论文"

    def get_system_prompt(self) -> str:
        return """你是一位优秀的学术论文写作助手，擅长撰写课程作业论文。

写作要求：
1. 语言通顺、结构清晰、论述有理有据
2. 对理论部分要解释清楚概念，适合同年级学生理解
3. 实验/计算部分要有具体步骤和结果
4. 讨论部分要有自己的思考，不能只是罗列结果
5. 适当使用图表辅助说明
6. 中文学术写作风格
7. 必须包含"学习心得与反思"章节，总结本次作业的学习收获、遇到的困难及解决方法
8. 参考文献需分类标注（教材/论文/网络资源），体现学术规范
9. 论文正文目标约8,000-12,000中文字符，内容完整且有深度"""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract",
                title="摘要",
                level=1,
                min_chars=300,
                target_chars=500,
                max_chars=800,
                relevance_keys=["problem_text", "analysis", "execution_result"],
            ),
            ChapterSpec(
                id="introduction",
                title="一、引言",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=2000,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="theory",
                title="二、理论基础",
                level=1,
                min_chars=1000,
                target_chars=2000,
                max_chars=3500,
                relevance_keys=["problem_text", "analysis", "modeling"],
            ),
            ChapterSpec(
                id="problem_description",
                title="三、问题描述",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=2000,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="methodology",
                title="四、方法设计",
                level=1,
                min_chars=1500,
                target_chars=2500,
                max_chars=4000,
                relevance_keys=["modeling", "algorithm", "formulas"],
            ),
            ChapterSpec(
                id="experiment",
                title="五、实验与计算",
                level=1,
                min_chars=1500,
                target_chars=2500,
                max_chars=4000,
                relevance_keys=["code", "execution_result", "algorithm"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="discussion",
                title="六、结果讨论",
                level=1,
                min_chars=1200,
                target_chars=2000,
                max_chars=3500,
                relevance_keys=["execution_result", "result_analysis", "charts"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="conclusion",
                title="七、结论",
                level=1,
                min_chars=600,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["execution_result", "result_analysis"],
            ),
            ChapterSpec(
                id="reflection",
                title="八、学习心得与反思",
                level=1,
                min_chars=500,
                target_chars=800,
                max_chars=1200,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="references",
                title="九、参考文献",
                level=1,
                min_chars=200,
                target_chars=400,
                max_chars=800,
                relevance_keys=["problem_text", "modeling"],
            ),
        ]


class FinancialAnalysisTemplate(PaperTemplate):
    """
    金融分析论文模板

    结构：
    摘要 → 市场背景 → 数据描述 → 分析方法 →
    模型构建 → 实证结果 → 风险评估 → 投资建议 → 结论
    """

    name = "financial_analysis"
    description = "金融数据分析与投资报告"

    def get_system_prompt(self) -> str:
        return """你是一位资深的金融分析师，擅长量化分析与投资报告撰写。

写作要求：
1. 数据分析必须基于真实计算结果，严禁编造数字
2. 使用专业金融术语（夏普比率、VaR、Beta、Alpha等）
3. 模型部分要说明假设、参数估计方法和稳健性检验
4. 风险评估要全面，包含市场风险、信用风险、流动性风险
5. 投资建议要有数据支撑，明确给出买入/持有/卖出建议及理由
6. 图表必须配合分析文字，不能只有图没有解读
7. 使用专业但可读的中文写作风格"""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract",
                title="摘要",
                level=1,
                min_chars=400,
                target_chars=600,
                max_chars=1000,
                relevance_keys=["problem_text", "execution_result", "result_analysis"],
            ),
            ChapterSpec(
                id="market_background",
                title="一、市场背景与研究意义",
                level=1,
                min_chars=1000,
                target_chars=1500,
                max_chars=2500,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="data_description",
                title="二、数据来源与描述性统计",
                level=1,
                min_chars=1000,
                target_chars=1500,
                max_chars=2500,
                relevance_keys=["data_files", "execution_result"],
                requires_data=True,
            ),
            ChapterSpec(
                id="methodology",
                title="三、分析方法与模型构建",
                level=1,
                min_chars=1500,
                target_chars=2500,
                max_chars=4000,
                relevance_keys=["problem_text", "modeling", "algorithm", "formulas"],
            ),
            ChapterSpec(
                id="empirical_results",
                title="四、实证分析结果",
                level=1,
                min_chars=2000,
                target_chars=3500,
                max_chars=5000,
                relevance_keys=["execution_result", "result_analysis", "charts"],
                requires_coding=True,
                requires_data=True,
            ),
            ChapterSpec(
                id="risk_assessment",
                title="五、风险评估",
                level=1,
                min_chars=1200,
                target_chars=2000,
                max_chars=3500,
                relevance_keys=["execution_result", "result_analysis", "modeling"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="investment_recommendation",
                title="六、投资建议",
                level=1,
                min_chars=1000,
                target_chars=1500,
                max_chars=2500,
                relevance_keys=["execution_result", "result_analysis"],
            ),
            ChapterSpec(
                id="conclusion",
                title="七、结论与展望",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=2000,
                relevance_keys=["execution_result", "result_analysis", "modeling"],
            ),
            ChapterSpec(
                id="references",
                title="参考文献",
                level=1,
                min_chars=200,
                target_chars=500,
                max_chars=1000,
                relevance_keys=["problem_text", "modeling"],
            ),
        ]


class NeurIPS2024Template(PaperTemplate):
    """
    NeurIPS 2024 论文模板 (ML/CCF-A)

    标准 ML 顶会结构：
    Abstract → Introduction → Related Work → Preliminaries →
    Method → Experiments → Discussion → Conclusion →
    References → Appendix

    本模板在 ICML/NeurIPS 常见拒稿点（线性标定无因果识别、无回测、无基线、
    代码不可复现、缺乏消融/敏感性、忽视异质性与网络传染）上强制注入严谨性清单。
    """

    name = "neurips_2024"
    description = "NeurIPS 2024 机器学习顶会论文（CCF-A，英文）"
    is_ccf_a = True

    def get_system_prompt(self) -> str:
        return """You are an expert ML researcher and writer targeting NeurIPS 2024 / ICML / ICLR (CCF-A).

Writing requirements:
1. Write in formal academic English suitable for top-tier ML venues
2. Use LaTeX notation for all mathematical formulations ($...$ or $$...$$)
3. Provide rigorous theoretical justification with proofs in appendices when needed
4. Include comprehensive ablation studies (>=3 components) and statistical significance tests
5. Compare against at least 5 recent baselines (2022-2024), including established systemic-risk / network baselines where relevant (e.g. DebtRank/SDECM, diffusion-spectral, ABM contagion)
6. Report all results with standard deviations / confidence intervals across multiple seeds; release seeds
7. Discuss limitations and broader impact honestly
8. Total paper length: 8-10 pages (excluding references and appendix)
9. Follow NeurIPS style guidelines (neurips_2024.sty)
10. Reproducibility: release full code, parameter priors/covariances, distributions, correlations, and random seeds; describe all hyperparameters

RIGOR MANDATES (reviewers will reject if missing):
- Causal identification: do not rely on linear calibrated elasticities alone; identify causal effects or state explicitly what is identified vs assumed; address endogeneity / reverse causality.
- Out-of-sample validation: backtest the model (e.g. fit on pre-treatment data, forecast held-out window) and report RMSE / MAE / CRPS. A scenario engine without predictive validation is insufficient.
- Heterogeneity: if the phenomenon varies across units (regions/banks/firms), model it with a hierarchical / panel structure rather than national aggregates only; report dispersion.
- Feedback loops: encode endogenous feedback (e.g. credit supply -> demand -> prices) rather than one-way chains; justify direction and magnitude, ideally with an SVAR or structural block.
- Network/topology: when systemic risk is central, add a network loss-propagation layer (DebtRank / SDECM / diffusion-spectral PDE / TGNN) and benchmark it against the aggregate block.
- Definitions: formalize every constructed quantity (e.g. "land net income", policy multipliers) with explicit reconciliation tables from raw inputs to the figure used.
- Sensitivity: provide tornado charts / elasticity-of-outcome-to-priors; do not report only point paths."""

    def get_rigor_checklist(self) -> List[str]:
        return [
            "必须提供因果识别或显式区分'已识别'与'假设'部分，处理内生性/反向因果",
            "必须包含样本外回测/验证并报告 RMSE/MAE/CRPS（场景引擎无预测验证不予接收）",
            "必须对比至少 5 个基线，含系统性风险/网络基线（DebtRank/SDECM、扩散谱、ABM）",
            "必须做消融实验（>=3 个组件）与敏感性分析（tornado/结果对先验的弹性）",
            "必须建模异质性（层级/面板结构），报告跨单元离散度，而非仅全国聚合",
            "必须编码内生反馈环（如信贷供给->需求->价格），用 SVAR/结构块验证方向与量级",
            "系统性风险为内核时必须加网络损失传染层（DebtRank/SDECM/扩散谱 PDE/TGNN）并与聚合块对比",
            "必须形式化所有构造量（如'土地净收入'、政策乘数），给出原始输入到使用值的对账表",
            "必须公开完整代码、参数先验/协方差、分布、相关性与随机种子",
            "必须诚实陈述局限（recognition 实践、重组、表外渠道等未被建模的部分）",
        ]

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract",
                title="Abstract",
                level=1,
                min_chars=100,
                target_chars=150,
                max_chars=200,
                relevance_keys=["problem_text", "method_summary", "key_results"],
                prompt_template=(
                    "Abstract must (a) state problem + gap, (b) state approach, "
                    "(c) give one headline quantitative result with uncertainty, "
                    "(d) state validation/backtest metric in one phrase. <=250 words, double-blind."
                ),
            ),
            ChapterSpec(
                id="introduction",
                title="1 Introduction",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=1800,
                relevance_keys=["problem_text", "analysis", "method_summary"],
                prompt_template=(
                    "Include: a concrete motivating example; explicit limitations of prior work "
                    "('X is limited because...'); 3-4 numbered, verifiable contributions as bullets; "
                    "paper organization. At least one contribution must mention causal identification, "
                    "backtesting, or a network/contagion layer."
                ),
            ),
            ChapterSpec(
                id="related_work",
                title="2 Related Work",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=1800,
                relevance_keys=["problem_text", "analysis"],
                prompt_template=(
                    "Cluster by theme (not year). MUST engage with: systemic-risk network models "
                    "(SDECM + DebtRank / NEVA), diffusion-spectral contagion, ABM/dynamic-graph "
                    "contagion, system-dynamics housing models, and empirical identification around "
                    "implicit guarantees / central supervision. For each cluster, position this paper "
                    "relative to the state-of-the-art and state the incremental contribution."
                ),
            ),
            ChapterSpec(
                id="preliminaries",
                title="3 Preliminaries",
                level=1,
                min_chars=500,
                target_chars=800,
                max_chars=1200,
                relevance_keys=["problem_text", "modeling", "formulas"],
                prompt_template=(
                    "Provide a notation table for ALL symbols. Formalize every constructed quantity "
                    "(e.g. 'land net income', policy multipliers) with an explicit reconciliation "
                    "table from raw inputs to the figure used in analysis. State the problem formulation."
                ),
            ),
            ChapterSpec(
                id="method",
                title="4 Method",
                level=1,
                min_chars=1500,
                target_chars=2500,
                max_chars=3500,
                relevance_keys=["modeling", "algorithm", "formulas"],
                requires_coding=True,
                prompt_template=(
                    "MUST cover: (i) causal identification strategy or explicit split of identified "
                    "vs assumed elasticities; (ii) hierarchical/panel structure for regional/bank "
                    "heterogeneity (not national aggregates only); (iii) endogenous feedback loop "
                    "(credit supply -> demand -> prices) with direction/magnitude justification; "
                    "(iv) a network loss-propagation layer (DebtRank / SDECM / diffusion-spectral PDE "
                    "/ TGNN) when systemic risk is central; (v) full mathematical derivation + at least "
                    "one algorithm box with complexity. Document all parameter priors, distributions, "
                    "and correlations."
                ),
            ),
            ChapterSpec(
                id="experiments",
                title="5 Experiments",
                level=1,
                min_chars=2000,
                target_chars=3000,
                max_chars=4500,
                relevance_keys=["execution_result", "result_analysis", "charts"],
                requires_coding=True,
                prompt_template=(
                    "MUST include: (1) Out-of-sample backtest (e.g. fit pre-2021, forecast 2021-2025) "
                    "with RMSE/MAE/CRPS for land revenue, prices, NPLs; (2) comparison against >=5 "
                    "baselines incl. established systemic-risk/network models; (3) ablation removing "
                    "each policy lever / network layer / feedback block; (4) sensitivity tornado charts "
                    "and elasticity of key outcomes to priors; (5) heterogeneity decomposition by "
                    "region/portfolio. Report all numbers with std/CI over multiple seeds."
                ),
            ),
            ChapterSpec(
                id="discussion",
                title="6 Discussion",
                level=1,
                min_chars=500,
                target_chars=800,
                max_chars=1200,
                relevance_keys=["execution_result", "result_analysis"],
                requires_coding=True,
                prompt_template=(
                    "Explicitly enumerate limitations (NPL recognition practices, restructuring, "
                    "off-balance-sheet channels not modeled), broader impact (positive + negative), "
                    "and a reproducibility statement (code/data release plan, seeds, priors)."
                ),
            ),
            ChapterSpec(
                id="conclusion",
                title="7 Conclusion",
                level=1,
                min_chars=300,
                target_chars=500,
                max_chars=800,
                relevance_keys=["result_analysis", "method_summary"],
            ),
            ChapterSpec(
                id="references",
                title="References",
                level=1,
                min_chars=300,
                target_chars=500,
                max_chars=1000,
                relevance_keys=["problem_text", "modeling"],
            ),
            ChapterSpec(
                id="appendix",
                title="Appendix",
                level=1,
                min_chars=500,
                target_chars=1000,
                max_chars=2000,
                relevance_keys=["code", "execution_result", "formulas"],
                requires_coding=True,
                prompt_template=(
                    "MUST contain: full code listing (or repository URL), complete parameter priors / "
                    "covariance matrix, distribution family for each random parameter, correlations, "
                    "random seeds, proof sketches, extended tables, and the NeurIPS reproducibility "
                    "checklist answers."
                ),
            ),
        ]


class IEEEConferenceTemplate(PaperTemplate):
    """
    IEEE Conference 论文模板 (Systems/Security/CCF-A)

    标准 IEEE 会议结构：
    Abstract → Introduction → Related Work → Background →
    Method → Experiments → Discussion → Conclusion →
    References → Appendix

    注入 CCF-A 严谨性清单：复现性、回测/OOS、基线对比、消融、敏感性、
    因果识别、异质性、网络传染、反馈环、定义形式化。
    """

    name = "ieee_conference"
    description = "IEEE 会议论文（系统/安全方向，CCF-A，英文）"
    is_ccf_a = True

    def get_system_prompt(self) -> str:
        return """You are an expert systems/security/applied-quantitative researcher writing for a top IEEE conference (CCF-A).

Writing requirements:
1. Write in formal academic English following IEEE style
2. Use IEEE citation format [1], [2], etc.
3. Clearly state research questions and hypotheses upfront
4. Provide detailed threat models (security) or structural identification (quantitative) for the studied channels
5. Include formal security proofs or game-based reductions when applicable; for empirical models, provide causal identification or explicit identified-vs-assumed split
6. Benchmark on standard datasets with realistic threat models; for systemic-risk models benchmark against established baselines (DebtRank/SDECM, diffusion-spectral, ABM)
7. Discuss practical deployment considerations and threats to validity (internal/external/construct)
8. Total paper length: 10-12 pages (IEEE two-column format)
9. Follow IEEE conference template (IEEEtran.cls)
10. Include a clear ethics statement for security/privacy work
11. Reproducibility: release full code, parameter priors/covariances, random seeds; backtest out-of-sample with RMSE/MAE/CRPS

RIGOR MANDATES (common reject points):
- No purely linear calibrated elasticities without causal identification; address endogeneity / reverse causality.
- Out-of-sample backtest mandatory for any forecasting/scenario engine; report RMSE/MAE/CRPS.
- Heterogeneity across units (regions/banks/firms) via hierarchical/panel modeling, not national aggregates only.
- Endogenous feedback loops (credit supply -> demand -> prices) with direction/magnitude justification.
- Network/topology loss propagation (DebtRank/SDECM/diffusion-spectral/TGNN) when systemic risk is central; benchmark vs aggregate block.
- Formalize constructed quantities (e.g. 'land net income', policy multipliers) with reconciliation tables.
- Ablation (>=3 components) + sensitivity tornado charts; do not report only point paths."""

    def get_rigor_checklist(self) -> List[str]:
        return [
            "必须提供因果识别或显式区分'已识别'与'假设'部分，处理内生性/反向因果",
            "必须包含样本外回测/验证并报告 RMSE/MAE/CRPS",
            "必须对比基线，含系统性风险/网络基线（DebtRank/SDECM、扩散谱、ABM）",
            "必须做消融实验（>=3 个组件）与敏感性分析（tornado）",
            "必须建模异质性（层级/面板），报告跨单元离散度",
            "必须编码内生反馈环，用 SVAR/结构块验证方向与量级",
            "系统性风险为内核时必须加网络损失传染层并与聚合块对比",
            "必须形式化所有构造量，给出对账表",
            "必须公开完整代码、参数先验/协方差、随机种子",
            "必须陈述 threats to validity（internal/external/construct）与局限",
        ]

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract",
                title="Abstract",
                level=1,
                min_chars=100,
                target_chars=150,
                max_chars=200,
                relevance_keys=["problem_text", "method_summary", "key_results"],
                prompt_template=(
                    "150-250 words. State problem, prior-work gap, approach, and the strongest "
                    "quantitative result with uncertainty. Mention the backtest/OOS metric in one phrase. "
                    "No citations, no 'in this paper'."
                ),
            ),
            ChapterSpec(
                id="introduction",
                title="I. Introduction",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=1800,
                relevance_keys=["problem_text", "analysis", "method_summary"],
                prompt_template=(
                    "Include: real-world pain point; explicit limitations of prior work ('X is limited because...'); "
                    "approach overview; 3-5 concrete contributions as bullets (at least one must mention causal "
                    "identification, backtesting, or a network/contagion layer); roadmap."
                ),
            ),
            ChapterSpec(
                id="related_work",
                title="II. Related Work",
                level=1,
                min_chars=600,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["problem_text", "analysis"],
                prompt_template=(
                    "Group by theme. MUST engage with systemic-risk network models (SDECM + DebtRank/NEVA), "
                    "diffusion-spectral contagion, ABM/dynamic-graph contagion, system-dynamics housing models, "
                    "and empirical identification around implicit guarantees / central supervision. >=20 recent "
                    "top-venue references."
                ),
            ),
            ChapterSpec(
                id="background",
                title="III. Background",
                level=1,
                min_chars=600,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["problem_text", "modeling", "formulas"],
                prompt_template=(
                    "Notation table for ALL symbols. Formalize constructed quantities (e.g. 'land net income', "
                    "policy multipliers) with reconciliation tables from raw inputs. Problem formulation."
                ),
            ),
            ChapterSpec(
                id="method",
                title="IV. Proposed Method",
                level=1,
                min_chars=1500,
                target_chars=2500,
                max_chars=3500,
                relevance_keys=["modeling", "algorithm", "formulas"],
                requires_coding=True,
                prompt_template=(
                    "MUST cover: causal identification or identified-vs-assumed split; hierarchical/panel "
                    "heterogeneity; endogenous feedback loop (credit supply -> demand -> prices); network "
                    "loss-propagation layer (DebtRank/SDECM/diffusion-spectral/TGNN) when systemic risk is "
                    "central; full derivation + complexity + correctness argument. Document all parameter "
                    "priors, distributions, correlations."
                ),
            ),
            ChapterSpec(
                id="experiments",
                title="V. Evaluation",
                level=1,
                min_chars=2000,
                target_chars=3000,
                max_chars=4500,
                relevance_keys=["execution_result", "result_analysis", "charts"],
                requires_coding=True,
                prompt_template=(
                    "MUST include: (1) out-of-sample backtest with RMSE/MAE/CRPS; (2) comparison against "
                    ">=5 baselines incl. established systemic-risk/network models; (3) ablation (>=3 components); "
                    "(4) sensitivity tornado + elasticity of outcomes to priors; (5) heterogeneity decomposition "
                    "by region/portfolio; (6) statistical significance (p-values/CI) over multiple seeds."
                ),
            ),
            ChapterSpec(
                id="discussion",
                title="VI. Discussion",
                level=1,
                min_chars=500,
                target_chars=800,
                max_chars=1200,
                relevance_keys=["execution_result", "result_analysis"],
                requires_coding=True,
                prompt_template=(
                    "Threats to validity (internal/external/construct); honest limitations (NPL recognition, "
                    "restructuring, off-balance-sheet channels); ethical considerations; reproducibility statement."
                ),
            ),
            ChapterSpec(
                id="conclusion",
                title="VII. Conclusion",
                level=1,
                min_chars=300,
                target_chars=500,
                max_chars=800,
                relevance_keys=["result_analysis", "method_summary"],
            ),
            ChapterSpec(
                id="references",
                title="References",
                level=1,
                min_chars=300,
                target_chars=500,
                max_chars=1000,
                relevance_keys=["problem_text", "modeling"],
            ),
            ChapterSpec(
                id="appendix",
                title="Appendix",
                level=1,
                min_chars=500,
                target_chars=1000,
                max_chars=2000,
                relevance_keys=["code", "execution_result"],
                requires_coding=True,
                prompt_template=(
                    "Full code listing / repository URL, complete parameter priors / covariance matrix, "
                    "distribution families, correlations, random seeds, proof details, reproducibility checklist."
                ),
            ),
        ]


class ACMSigConfTemplate(PaperTemplate):
    """
    ACM SIGCONF 论文模板 (Graphics/Networking/CCF-A)

    标准 ACM 会议结构：
    Abstract → Introduction → Related Work → Method →
    Implementation → Evaluation → Discussion → Conclusion →
    References → Appendix

    注入 CCF-A 严谨性清单。
    """

    name = "acm_sigconf"
    description = "ACM SIGCONF 会议论文（图形/网络方向，CCF-A，英文）"
    is_ccf_a = True

    def get_system_prompt(self) -> str:
        return """You are an expert researcher writing for a top ACM conference (SIGGRAPH, SIGCOMM, etc., CCF-A).

Writing requirements:
1. Write in formal academic English following ACM style
2. Use ACM citation format (numeric [1] or author-year)
3. Include detailed system/architecture diagrams description
4. Provide algorithmic complexity analysis (time and space)
5. Report experiments on standard benchmarks with multiple metrics; for systemic-risk models benchmark against established baselines (DebtRank/SDECM, diffusion-spectral, ABM)
6. Include qualitative and quantitative results with ablations (>=3) and sensitivity analysis
7. Discuss limitations and future work candidly
8. Total paper length: 10-14 pages (ACM sigconf template)
9. Follow ACM formatting guidelines (acmart.cls, sigconf option)
10. Include artifact description for reproducibility (code, parameter priors/covariances, random seeds)
11. For empirical/quantitative channels: causal identification or explicit identified-vs-assumed split; out-of-sample backtest with RMSE/MAE/CRPS

RIGOR MANDATES (common reject points):
- No purely linear calibrated elasticities without causal identification; address endogeneity.
- Out-of-sample backtest mandatory for forecasting/scenario engines; report RMSE/MAE/CRPS.
- Heterogeneity across units via hierarchical/panel modeling, not aggregates only.
- Endogenous feedback loops with direction/magnitude justification.
- Network/topology loss propagation when systemic risk is central; benchmark vs aggregate block.
- Formalize constructed quantities with reconciliation tables.
- Ablation (>=3 components) + sensitivity tornado charts."""

    def get_rigor_checklist(self) -> List[str]:
        return [
            "必须提供因果识别或显式区分'已识别'与'假设'部分",
            "必须包含样本外回测/验证并报告 RMSE/MAE/CRPS",
            "必须对比基线，含系统性风险/网络基线（DebtRank/SDECM、扩散谱、ABM）",
            "必须做消融实验（>=3 个组件）与敏感性分析（tornado）",
            "必须建模异质性（层级/面板），报告跨单元离散度",
            "必须编码内生反馈环，用 SVAR/结构块验证方向与量级",
            "系统性风险为内核时必须加网络损失传染层并与聚合块对比",
            "必须形式化所有构造量，给出对账表",
            "必须公开完整代码、参数先验/协方差、随机种子（artifact description）",
            "必须陈述局限与未来工作",
        ]

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract",
                title="Abstract",
                level=1,
                min_chars=100,
                target_chars=150,
                max_chars=200,
                relevance_keys=["problem_text", "method_summary", "key_results"],
                prompt_template=(
                    "State problem, gap, approach, headline result with uncertainty, and backtest metric "
                    "in one phrase. No citations."
                ),
            ),
            ChapterSpec(
                id="introduction",
                title="1. Introduction",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=1800,
                relevance_keys=["problem_text", "analysis", "method_summary"],
                prompt_template=(
                    "Concrete motivating example; explicit prior-work limitations; approach overview; "
                    "3-5 concrete contributions (>=1 on causal identification / backtesting / network layer); roadmap."
                ),
            ),
            ChapterSpec(
                id="related_work",
                title="2. Related Work",
                level=1,
                min_chars=600,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["problem_text", "analysis"],
                prompt_template=(
                    "Cluster by theme. MUST engage with systemic-risk network models (SDECM + DebtRank/NEVA), "
                    "diffusion-spectral contagion, ABM/dynamic-graph contagion, system-dynamics housing models, "
                    "and empirical identification around implicit guarantees / central supervision."
                ),
            ),
            ChapterSpec(
                id="method",
                title="3. Method",
                level=1,
                min_chars=1500,
                target_chars=2500,
                max_chars=3500,
                relevance_keys=["modeling", "algorithm", "formulas"],
                requires_coding=True,
                prompt_template=(
                    "MUST cover: causal identification or identified-vs-assumed split; hierarchical/panel "
                    "heterogeneity; endogenous feedback loop (credit supply -> demand -> prices); network "
                    "loss-propagation layer (DebtRank/SDECM/diffusion-spectral/TGNN) when systemic risk is "
                    "central; full derivation + complexity. Document all parameter priors, distributions, correlations."
                ),
            ),
            ChapterSpec(
                id="implementation",
                title="4. Implementation",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=1800,
                relevance_keys=["code", "algorithm", "execution_result"],
                requires_coding=True,
                prompt_template=(
                    "Architecture diagram description; engineering decisions; parameter priors / covariance "
                    "matrix; distribution families; correlations; random seeds. State the code/release plan."
                ),
            ),
            ChapterSpec(
                id="evaluation",
                title="5. Evaluation",
                level=1,
                min_chars=2000,
                target_chars=3000,
                max_chars=4500,
                relevance_keys=["execution_result", "result_analysis", "charts"],
                requires_coding=True,
                prompt_template=(
                    "MUST include: (1) out-of-sample backtest with RMSE/MAE/CRPS; (2) comparison against >=5 "
                    "baselines incl. established systemic-risk/network models; (3) ablation (>=3 components); "
                    "(4) sensitivity tornado + elasticity of outcomes to priors; (5) heterogeneity decomposition "
                    "by region/portfolio; (6) multiple metrics with std/CI over seeds."
                ),
            ),
            ChapterSpec(
                id="discussion",
                title="6. Discussion",
                level=1,
                min_chars=500,
                target_chars=800,
                max_chars=1200,
                relevance_keys=["execution_result", "result_analysis"],
                requires_coding=True,
                prompt_template=(
                    "Honest limitations (NPL recognition, restructuring, off-balance-sheet channels); "
                    "future work; artifact description / reproducibility statement."
                ),
            ),
            ChapterSpec(
                id="conclusion",
                title="7. Conclusion",
                level=1,
                min_chars=300,
                target_chars=500,
                max_chars=800,
                relevance_keys=["result_analysis", "method_summary"],
            ),
            ChapterSpec(
                id="references",
                title="References",
                level=1,
                min_chars=300,
                target_chars=500,
                max_chars=1000,
                relevance_keys=["problem_text", "modeling"],
            ),
            ChapterSpec(
                id="appendix",
                title="Appendix",
                level=1,
                min_chars=500,
                target_chars=1000,
                max_chars=2000,
                relevance_keys=["code", "execution_result"],
                requires_coding=True,
                prompt_template=(
                    "Full code listing / repository URL, complete parameter priors / covariance matrix, "
                    "distribution families, correlations, random seeds, proof details, extended tables, "
                    "artifact description."
                ),
            ),
        ]


class SpringerLNCSWriterTemplate(PaperTemplate):
    """
    Springer LNCS 论文模板 (Computer Science/CCF-B)

    标准 Springer LNCS 结构：
    Abstract → Introduction → Related Work → Preliminaries →
    Method → Experiments → Conclusion → References
    """

    name = "springer_lncs"
    description = "Springer LNCS 期刊论文（计算机科学，CCF-B，英文）"

    def get_system_prompt(self) -> str:
        return """You are an expert computer science researcher writing for a Springer LNCS journal.

Writing requirements:
1. Write in formal academic English following Springer LNCS style
2. Provide clear mathematical notation with consistent symbol usage
3. Include comprehensive experimental validation
4. Compare with state-of-the-art methods from 2022-2024
5. Report metrics with confidence intervals where applicable
6. Discuss theoretical foundations before presenting the method
7. Include a dedicated section on experimental setup and datasets
8. Total paper length: 16-20 pages (LNCS template)
9. Follow Springer formatting guidelines (llncs.cls)
10. Ensure clarity for interdisciplinary readers"""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract",
                title="Abstract",
                level=1,
                min_chars=100,
                target_chars=150,
                max_chars=200,
                relevance_keys=["problem_text", "method_summary", "key_results"],
            ),
            ChapterSpec(
                id="introduction",
                title="1. Introduction",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=1800,
                relevance_keys=["problem_text", "analysis", "method_summary"],
            ),
            ChapterSpec(
                id="related_work",
                title="2. Related Work",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=1800,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="preliminaries",
                title="3. Preliminaries",
                level=1,
                min_chars=600,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["problem_text", "modeling", "formulas"],
            ),
            ChapterSpec(
                id="method",
                title="4. Proposed Method",
                level=1,
                min_chars=1500,
                target_chars=2500,
                max_chars=3500,
                relevance_keys=["modeling", "algorithm", "formulas"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="experiments",
                title="5. Experiments",
                level=1,
                min_chars=2000,
                target_chars=3000,
                max_chars=4500,
                relevance_keys=["execution_result", "result_analysis", "charts"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="conclusion",
                title="6. Conclusion",
                level=1,
                min_chars=400,
                target_chars=600,
                max_chars=1000,
                relevance_keys=["result_analysis", "method_summary"],
            ),
            ChapterSpec(
                id="references",
                title="References",
                level=1,
                min_chars=300,
                target_chars=500,
                max_chars=1000,
                relevance_keys=["problem_text", "modeling"],
            ),
        ]


class ResearchSurveyTemplate(PaperTemplate):
    """
    文献综述论文模板 (Literature Survey)

    结构：
    摘要 → 研究全景图 → Research Gaps → 交叉学科启发 →
    创新点提案 → 必读文献清单 → 数据集与实验设置 →
    结果对比与讨论 → 结论与展望
    """

    name = "research_survey"
    description = "文献综述论文（中文）"

    def get_system_prompt(self) -> str:
        return """你是一位资深的学术文献综述专家，擅长系统性地梳理和分析研究领域的发展脉络。

写作要求：
1. 系统全面地覆盖领域内的重要文献，按主题/时间/方法分类组织
2. 对每篇关键文献给出客观评价，指出其贡献和局限
3. 识别现有研究的空白和不足，提出未来方向
4. 使用学术中文写作风格，术语准确规范
5. 引用格式统一（GB/T 7714 或 APA 格式）
6. 注重跨学科视角，发掘不同领域的交叉启发
7. 总字数约 8,000-12,000 中文字符
8. 图表辅助说明：研究分类图、时间线、对比表格"""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract",
                title="摘要",
                level=1,
                min_chars=300,
                target_chars=500,
                max_chars=700,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="research_landscape",
                title="一、研究全景图",
                level=1,
                min_chars=1500,
                target_chars=2500,
                max_chars=3500,
                relevance_keys=["problem_text", "analysis", "sub_problems"],
            ),
            ChapterSpec(
                id="research_gaps",
                title="二、Research Gaps",
                level=1,
                min_chars=1000,
                target_chars=1500,
                max_chars=2500,
                relevance_keys=["problem_text", "analysis", "sub_problems"],
            ),
            ChapterSpec(
                id="interdisciplinary",
                title="三、交叉学科启发",
                level=1,
                min_chars=1000,
                target_chars=1500,
                max_chars=2500,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="innovation_proposal",
                title="四、创新点提案",
                level=1,
                min_chars=1000,
                target_chars=1500,
                max_chars=2500,
                relevance_keys=["problem_text", "analysis", "modeling"],
            ),
            ChapterSpec(
                id="must_read_literature",
                title="五、必读文献清单",
                level=1,
                min_chars=1000,
                target_chars=1500,
                max_chars=2500,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="dataset_experiment",
                title="六、数据集与实验设置",
                level=1,
                min_chars=1000,
                target_chars=1500,
                max_chars=2500,
                relevance_keys=["problem_text", "analysis", "execution_result"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="result_comparison",
                title="七、结果对比与讨论",
                level=1,
                min_chars=1200,
                target_chars=2000,
                max_chars=3000,
                relevance_keys=["execution_result", "result_analysis", "charts"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="conclusion",
                title="八、结论与展望",
                level=1,
                min_chars=600,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["result_analysis", "analysis"],
            ),
        ]


# =============================================================================
# CCF-A 三大 ML 顶会细分模板：ICLR / ICML / AAAI
# =============================================================================
# 三家风格差异（审稿人会在第一眼判断是否套错模板）：
# - ICLR 2024: 无严格页限（推荐 8-10 页），OpenReview 双盲，强调理论+实证并重，
#   iclr2024_conference.sty，单栏 11pt。评审重视"为什么 work"的可解释性与
#   reproducibility checklist。
# - ICML 2024: 8 页正文 + 无限附录/参考，icml_2024.sty，单栏 10pt。理论深度
#   要求最高，必须有定理/收敛性/复杂度证明 sketch。
# - AAAI 2024: 7 页正文 + 2 页附录，aaai24.sty，双栏 10pt。偏应用/AI 通用，
#   评审更看 application value + 实验充分性，理论可略轻。
# 三者共享 ML CCF-A 严谨性清单（因果识别/回测/基线/消融/敏感性/异质性/
# 反馈环/网络传染/形式化/复现性），但在 system_prompt 与章节配比上有差异。


class _MLCCFAMixin:
    """三大 ML 顶会共享的严谨性清单（避免重复定义）。

    每条直接对应 ICML/ICLR/AAAI 评审常见拒稿点。
    """
    _SHARED_RIGOR = [
        "必须提供因果识别或显式区分'已识别'与'假设'部分，处理内生性/反向因果",
        "必须包含样本外回测/验证并报告 RMSE/MAE/CRPS",
        "必须对比至少 5 个基线，含系统性风险/网络基线（DebtRank/SDECM、扩散谱、ABM）",
        "必须做消融实验（>=3 个组件）与敏感性分析（tornado/结果对先验的弹性）",
        "必须建模异质性（层级/面板结构），报告跨单元离散度，而非仅聚合",
        "必须编码内生反馈环（如信贷供给->需求->价格），用 SVAR/结构块验证方向与量级",
        "系统性风险为内核时必须加网络损失传染层（DebtRank/SDECM/扩散谱 PDE/TGNN）并与聚合块对比",
        "必须形式化所有构造量（如'土地净收入'、政策乘数），给出原始输入到使用值的对账表",
        "必须公开完整代码、参数先验/协方差、分布、相关性与随机种子",
        "必须诚实陈述局限与 broader impact（正面+负面）",
    ]

    def get_rigor_checklist(self) -> List[str]:
        return list(self._SHARED_RIGOR)


class ICLR2024Template(_MLCCFAMixin, PaperTemplate):
    """ICLR 2024 论文模板 (CCF-A ML).

    结构与 NeurIPS 相近但：(1) 无严格页限，重视可解释性与 reproducibility
    checklist；(2) OpenReview 双盲；(3) 评审常追问"为什么 work"。
    """

    name = "iclr_2024"
    description = "ICLR 2024 机器学习顶会论文（CCF-A，英文，OpenReview）"
    is_ccf_a = True

    def get_system_prompt(self) -> str:
        return """You are an expert ML researcher writing for ICLR 2024 (CCF-A, OpenReview, double-blind).

Writing requirements:
1. Formal academic English; LaTeX notation for all math ($...$ or $$...$$)
2. No strict page limit (target 8-10 main pages); references and appendix excluded
3. Double-blind: no author names, affiliations, or self-identifying citations
4. Sections: Abstract -> 1 Introduction -> 2 Related Work -> 3 Preliminaries ->
   4 Method -> 5 Experiments -> 6 Discussion -> 7 Conclusion -> References -> Appendix
5. Use iclr2024_conference.sty (letterpaper, 11pt, single-column)

ICLR-SPECIFIC EMPHASIS (reviewers prize "why it works"):
- Provide intuition for design choices; ablate to show each component's causal role.
- Reproducibility checklist in appendix (seeds, code, data, compute).
- Engage with theoretical AND empirical reviewers — give a proof sketch even if empirical.

RIGOR MANDATES (reject points):
- Causal identification or explicit identified-vs-assumed split; no pure linear calibration.
- Out-of-sample backtest with RMSE/MAE/CRPS.
- >=5 baselines incl. systemic-risk/network models (DebtRank/SDECM, diffusion-spectral, ABM) where relevant.
- Ablation >=3 components; sensitivity tornado; heterogeneity (hierarchical/panel).
- Endogenous feedback loops (credit supply -> demand -> prices) with SVAR/structural justification.
- Network loss-propagation layer when systemic risk is central.
- Formalize all constructed quantities with reconciliation tables.
- Release full code, parameter priors/covariances, distributions, correlations, seeds."""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract", title="Abstract", level=1,
                min_chars=100, target_chars=150, max_chars=200,
                relevance_keys=["problem_text", "method_summary", "key_results"],
                prompt_template=(
                    "<=250 words. One sentence each: problem, gap, approach, headline result with uncertainty, "
                    "validation metric. Double-blind."
                ),
            ),
            ChapterSpec(
                id="introduction", title="1 Introduction", level=1,
                min_chars=800, target_chars=1200, max_chars=1800,
                relevance_keys=["problem_text", "analysis", "method_summary"],
                prompt_template=(
                    "Concrete motivating example; explicit prior-work limitations; approach overview; "
                    "3-4 numbered contributions (>=1 on causal identification/backtesting/network layer); roadmap."
                ),
            ),
            ChapterSpec(
                id="related_work", title="2 Related Work", level=1,
                min_chars=800, target_chars=1200, max_chars=1800,
                relevance_keys=["problem_text", "analysis"],
                prompt_template=(
                    "Cluster by theme. MUST engage systemic-risk network models (SDECM+DebtRank/NEVA), "
                    "diffusion-spectral contagion, ABM/dynamic-graph contagion, system-dynamics housing models, "
                    "empirical identification around implicit guarantees / central supervision."
                ),
            ),
            ChapterSpec(
                id="preliminaries", title="3 Preliminaries", level=1,
                min_chars=500, target_chars=800, max_chars=1200,
                relevance_keys=["problem_text", "modeling", "formulas"],
                prompt_template=(
                    "Notation table for ALL symbols. Formalize constructed quantities (e.g. 'land net income', "
                    "policy multipliers) with reconciliation tables. Problem formulation."
                ),
            ),
            ChapterSpec(
                id="method", title="4 Method", level=1,
                min_chars=1500, target_chars=2500, max_chars=3500,
                relevance_keys=["modeling", "algorithm", "formulas"], requires_coding=True,
                prompt_template=(
                    "MUST cover: causal identification / identified-vs-assumed split; hierarchical/panel "
                    "heterogeneity; endogenous feedback loop (credit supply -> demand -> prices); network "
                    "loss-propagation layer (DebtRank/SDECM/diffusion-spectral/TGNN) when systemic risk is "
                    "central; full derivation + algorithm box + complexity + proof sketch. Document all "
                    "parameter priors, distributions, correlations."
                ),
            ),
            ChapterSpec(
                id="experiments", title="5 Experiments", level=1,
                min_chars=2000, target_chars=3000, max_chars=4500,
                relevance_keys=["execution_result", "result_analysis", "charts"], requires_coding=True,
                prompt_template=(
                    "MUST include: (1) out-of-sample backtest with RMSE/MAE/CRPS; (2) >=5 baselines incl. "
                    "systemic-risk/network models; (3) ablation >=3 components; (4) sensitivity tornado + "
                    "elasticity to priors; (5) heterogeneity decomposition; (6) std/CI over multiple seeds."
                ),
            ),
            ChapterSpec(
                id="discussion", title="6 Discussion", level=1,
                min_chars=500, target_chars=800, max_chars=1200,
                relevance_keys=["execution_result", "result_analysis"], requires_coding=True,
                prompt_template=(
                    "Limitations (NPL recognition, restructuring, off-balance-sheet); broader impact "
                    "(positive+negative); reproducibility statement."
                ),
            ),
            ChapterSpec(
                id="conclusion", title="7 Conclusion", level=1,
                min_chars=300, target_chars=500, max_chars=800,
                relevance_keys=["result_analysis", "method_summary"],
            ),
            ChapterSpec(
                id="references", title="References", level=1,
                min_chars=300, target_chars=500, max_chars=1000,
                relevance_keys=["problem_text", "modeling"],
            ),
            ChapterSpec(
                id="appendix", title="Appendix", level=1,
                min_chars=500, target_chars=1000, max_chars=2000,
                relevance_keys=["code", "execution_result", "formulas"], requires_coding=True,
                prompt_template=(
                    "Full code/repository URL; complete parameter priors/covariance matrix; distribution "
                    "families; correlations; seeds; proof details; ICLR reproducibility checklist answers."
                ),
            ),
        ]


class ICML2024Template(_MLCCFAMixin, PaperTemplate):
    """ICML 2024 论文模板 (CCF-A ML).

    与 NeurIPS/ICLR 的关键差异：8 页硬限 + 理论深度要求最高（必须有定理/
    收敛性/复杂度证明 sketch）。评审最看重"方法的新颖性与理论贡献"。
    """

    name = "icml_2024"
    description = "ICML 2024 机器学习顶会论文（CCF-A，英文，8页强理论）"
    is_ccf_a = True

    def get_system_prompt(self) -> str:
        return """You are an expert ML researcher writing for ICML 2024 (CCF-A, double-blind).

Writing requirements:
1. Formal academic English; LaTeX notation for all math
2. STRICT 8-page main limit (excluding references and appendix); be dense
3. Double-blind; icml_2024.sty (letterpaper, 10pt, single-column)
4. Sections: Abstract -> 1 Introduction -> 2 Related Work -> 3 Preliminaries ->
   4 Method -> 5 Experiments -> 6 Discussion -> 7 Conclusion -> References -> Appendix

ICML-SPECIFIC EMPHASIS (reviewers prize theoretical contribution):
- At least one theorem/proposition with a proof sketch in main paper; full proof in appendix.
- Convergence / generalization / sample complexity analysis for any iterative method.
- Novelty of the methodological contribution must be stated crisply (not just "we apply X to Y").

RIGOR MANDATES (reject points):
- Causal identification or explicit identified-vs-assumed split; no pure linear calibration.
- Out-of-sample backtest with RMSE/MAE/CRPS.
- >=5 baselines incl. systemic-risk/network models (DebtRank/SDECM, diffusion-spectral, ABM) where relevant.
- Ablation >=3 components; sensitivity tornado; heterogeneity (hierarchical/panel).
- Endogenous feedback loops (credit supply -> demand -> prices) with SVAR/structural justification.
- Network loss-propagation layer when systemic risk is central.
- Formalize all constructed quantities with reconciliation tables.
- Release full code, parameter priors/covariances, distributions, correlations, seeds."""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract", title="Abstract", level=1,
                min_chars=100, target_chars=150, max_chars=200,
                relevance_keys=["problem_text", "method_summary", "key_results"],
                prompt_template="<=250 words. problem, gap, approach, headline result+uncertainty, validation metric. Double-blind.",
            ),
            ChapterSpec(
                id="introduction", title="1 Introduction", level=1,
                min_chars=800, target_chars=1100, max_chars=1600,
                relevance_keys=["problem_text", "analysis", "method_summary"],
                prompt_template=(
                    "Concrete motivating example; prior-work limitations; approach; 3-4 numbered contributions "
                    "(>=1 on causal identification/backtesting/network layer); roadmap. Be dense — 8-page limit."
                ),
            ),
            ChapterSpec(
                id="related_work", title="2 Related Work", level=1,
                min_chars=600, target_chars=900, max_chars=1300,
                relevance_keys=["problem_text", "analysis"],
                prompt_template=(
                    "Cluster by theme. MUST engage systemic-risk network models (SDECM+DebtRank/NEVA), "
                    "diffusion-spectral contagion, ABM/dynamic-graph contagion, system-dynamics housing, "
                    "empirical identification around implicit guarantees / central supervision."
                ),
            ),
            ChapterSpec(
                id="preliminaries", title="3 Preliminaries", level=1,
                min_chars=400, target_chars=700, max_chars=1000,
                relevance_keys=["problem_text", "modeling", "formulas"],
                prompt_template="Notation table; formalize constructed quantities with reconciliation tables; problem formulation.",
            ),
            ChapterSpec(
                id="method", title="4 Method", level=1,
                min_chars=1500, target_chars=2200, max_chars=3000,
                relevance_keys=["modeling", "algorithm", "formulas"], requires_coding=True,
                prompt_template=(
                    "MUST cover: causal identification / identified-vs-assumed split; hierarchical/panel "
                    "heterogeneity; endogenous feedback loop; network loss-propagation layer when systemic "
                    "risk is central; full derivation + algorithm box + complexity + >=1 theorem with proof "
                    "sketch. Document all parameter priors, distributions, correlations."
                ),
            ),
            ChapterSpec(
                id="experiments", title="5 Experiments", level=1,
                min_chars=1800, target_chars=2600, max_chars=3800,
                relevance_keys=["execution_result", "result_analysis", "charts"], requires_coding=True,
                prompt_template=(
                    "MUST include: (1) out-of-sample backtest with RMSE/MAE/CRPS; (2) >=5 baselines incl. "
                    "systemic-risk/network models; (3) ablation >=3 components; (4) sensitivity tornado + "
                    "elasticity to priors; (5) heterogeneity decomposition; (6) std/CI over multiple seeds."
                ),
            ),
            ChapterSpec(
                id="discussion", title="6 Discussion", level=1,
                min_chars=400, target_chars=600, max_chars=900,
                relevance_keys=["execution_result", "result_analysis"], requires_coding=True,
                prompt_template="Limitations; broader impact; reproducibility statement.",
            ),
            ChapterSpec(
                id="conclusion", title="7 Conclusion", level=1,
                min_chars=250, target_chars=400, max_chars=600,
                relevance_keys=["result_analysis", "method_summary"],
            ),
            ChapterSpec(
                id="references", title="References", level=1,
                min_chars=300, target_chars=500, max_chars=1000,
                relevance_keys=["problem_text", "modeling"],
            ),
            ChapterSpec(
                id="appendix", title="Appendix", level=1,
                min_chars=500, target_chars=1000, max_chars=2000,
                relevance_keys=["code", "execution_result", "formulas"], requires_coding=True,
                prompt_template=(
                    "Full proofs; full code/repository URL; complete parameter priors/covariance matrix; "
                    "distribution families; correlations; seeds; extended tables."
                ),
            ),
        ]


class AAAI2024Template(_MLCCFAMixin, PaperTemplate):
    """AAAI 2024 论文模板 (CCF-A AI).

    与 NeurIPS/ICML/ICLR 的关键差异：7+2 页硬限、双栏、偏应用/AI 通用。
    评审更看 application value + 实验充分性，理论可略轻但严谨性清单不变。
    """

    name = "aaai_2024"
    description = "AAAI 2024 人工智能顶会论文（CCF-A，英文，7+2页双栏应用导向）"
    is_ccf_a = True

    def get_system_prompt(self) -> str:
        return """You are an expert AI researcher writing for AAAI 2024 (CCF-A).

Writing requirements:
1. Formal academic English; LaTeX notation for all math
2. STRICT 7-page main limit + 2-page appendix (references excluded from 7); be concise
3. aaai24.sty (letterpaper, 10pt, double-column)
4. Sections: Abstract -> 1 Introduction -> 2 Related Work -> 3 Preliminaries ->
   4 Method -> 5 Experiments -> 6 Discussion -> 7 Conclusion -> References -> Appendix

AAAI-SPECIFIC EMPHASIS (reviewers prize application value + experimental thoroughness):
- Motivate with a concrete real-world application scenario.
- Experiments should be the strongest section: multiple datasets, baselines, ablations.
- Theory welcome but can be lighter than ICML; rigor checklist still applies.

RIGOR MANDATES (reject points):
- Causal identification or explicit identified-vs-assumed split; no pure linear calibration.
- Out-of-sample backtest with RMSE/MAE/CRPS.
- >=5 baselines incl. systemic-risk/network models (DebtRank/SDECM, diffusion-spectral, ABM) where relevant.
- Ablation >=3 components; sensitivity tornado; heterogeneity (hierarchical/panel).
- Endogenous feedback loops (credit supply -> demand -> prices) with SVAR/structural justification.
- Network loss-propagation layer when systemic risk is central.
- Formalize all constructed quantities with reconciliation tables.
- Release full code, parameter priors/covariances, distributions, correlations, seeds."""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract", title="Abstract", level=1,
                min_chars=100, target_chars=150, max_chars=200,
                relevance_keys=["problem_text", "method_summary", "key_results"],
                prompt_template="150-250 words. problem, gap, approach, headline result+uncertainty, validation metric, application value.",
            ),
            ChapterSpec(
                id="introduction", title="1 Introduction", level=1,
                min_chars=700, target_chars=1000, max_chars=1400,
                relevance_keys=["problem_text", "analysis", "method_summary"],
                prompt_template=(
                    "Concrete real-world application scenario; prior-work limitations; approach; 3-4 numbered "
                    "contributions (>=1 on causal identification/backtesting/network layer); roadmap. Concise — 7-page limit."
                ),
            ),
            ChapterSpec(
                id="related_work", title="2 Related Work", level=1,
                min_chars=500, target_chars=800, max_chars=1100,
                relevance_keys=["problem_text", "analysis"],
                prompt_template=(
                    "Cluster by theme. MUST engage systemic-risk network models (SDECM+DebtRank/NEVA), "
                    "diffusion-spectral contagion, ABM/dynamic-graph contagion, system-dynamics housing, "
                    "empirical identification around implicit guarantees / central supervision."
                ),
            ),
            ChapterSpec(
                id="preliminaries", title="3 Preliminaries", level=1,
                min_chars=400, target_chars=600, max_chars=900,
                relevance_keys=["problem_text", "modeling", "formulas"],
                prompt_template="Notation table; formalize constructed quantities with reconciliation tables; problem formulation.",
            ),
            ChapterSpec(
                id="method", title="4 Method", level=1,
                min_chars=1200, target_chars=1800, max_chars=2600,
                relevance_keys=["modeling", "algorithm", "formulas"], requires_coding=True,
                prompt_template=(
                    "MUST cover: causal identification / identified-vs-assumed split; hierarchical/panel "
                    "heterogeneity; endogenous feedback loop; network loss-propagation layer when systemic "
                    "risk is central; derivation + algorithm box + complexity. Document all parameter priors."
                ),
            ),
            ChapterSpec(
                id="experiments", title="5 Experiments", level=1,
                min_chars=1800, target_chars=2600, max_chars=3800,
                relevance_keys=["execution_result", "result_analysis", "charts"], requires_coding=True,
                prompt_template=(
                    "STRONGEST section. MUST include: (1) out-of-sample backtest with RMSE/MAE/CRPS; "
                    "(2) >=5 baselines incl. systemic-risk/network models; (3) ablation >=3 components; "
                    "(4) sensitivity tornado + elasticity to priors; (5) heterogeneity decomposition; "
                    "(6) multiple datasets; (7) std/CI over seeds."
                ),
            ),
            ChapterSpec(
                id="discussion", title="6 Discussion", level=1,
                min_chars=300, target_chars=500, max_chars=700,
                relevance_keys=["execution_result", "result_analysis"], requires_coding=True,
                prompt_template="Limitations; broader impact; reproducibility statement.",
            ),
            ChapterSpec(
                id="conclusion", title="7 Conclusion", level=1,
                min_chars=250, target_chars=400, max_chars=600,
                relevance_keys=["result_analysis", "method_summary"],
            ),
            ChapterSpec(
                id="references", title="References", level=1,
                min_chars=300, target_chars=500, max_chars=1000,
                relevance_keys=["problem_text", "modeling"],
            ),
            ChapterSpec(
                id="appendix", title="Appendix", level=1,
                min_chars=500, target_chars=1000, max_chars=2000,
                relevance_keys=["code", "execution_result", "formulas"], requires_coding=True,
                prompt_template=(
                    "Full code/repository URL; complete parameter priors/covariance matrix; distribution "
                    "families; correlations; seeds; extended tables; proofs."
                ),
            ),
        ]


# 模板注册表
_TEMPLATE_REGISTRY = {
    "math_modeling": MathModelingTemplate,
    "coursework": CourseworkTemplate,
    "financial_analysis": FinancialAnalysisTemplate,
    "neurips_2024": NeurIPS2024Template,
    "iclr_2024": ICLR2024Template,
    "icml_2024": ICML2024Template,
    "aaai_2024": AAAI2024Template,
    "ieee_conference": IEEEConferenceTemplate,
    "acm_sigconf": ACMSigConfTemplate,
    "springer_lncs": SpringerLNCSWriterTemplate,
    "research_survey": ResearchSurveyTemplate,
}


def get_template(name: str) -> PaperTemplate:
    """获取指定名称的论文模板"""
    if name not in _TEMPLATE_REGISTRY:
        print(f"[Template] 未知模板 '{name}'，使用默认数学建模模板")
        name = "math_modeling"
    return _TEMPLATE_REGISTRY[name]()


def list_templates() -> Dict[str, str]:
    """列出所有可用模板"""
    return {k: v().description for k, v in _TEMPLATE_REGISTRY.items()}
