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
    description: str = "基础模板"

    @abstractmethod
    def get_outline(self) -> List[ChapterSpec]:
        """获取论文大纲"""
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """获取论文写作系统提示词"""
        pass

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
    """

    name = "neurips_2024"
    description = "NeurIPS 2024 机器学习顶会论文（CCF-A，英文）"

    def get_system_prompt(self) -> str:
        return """You are an expert ML researcher and writer targeting NeurIPS 2024.

Writing requirements:
1. Write in formal academic English suitable for top-tier ML venues
2. Use LaTeX notation for all mathematical formulations ($...$ or $$...$$)
3. Provide rigorous theoretical justification with proofs in appendices when needed
4. Include comprehensive ablation studies and statistical significance tests
5. Compare against at least 5 recent baselines (2022-2024)
6. Report all results with standard deviations across multiple runs
7. Discuss limitations and broader impact honestly
8. Total paper length: 8-10 pages (excluding references and appendix)
9. Follow NeurIPS style guidelines (neurips_2024.sty)
10. Ensure reproducibility: release code and describe all hyperparameters"""

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
                min_chars=500,
                target_chars=800,
                max_chars=1200,
                relevance_keys=["problem_text", "modeling", "formulas"],
            ),
            ChapterSpec(
                id="method",
                title="4. Method",
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
                id="discussion",
                title="6. Discussion",
                level=1,
                min_chars=500,
                target_chars=800,
                max_chars=1200,
                relevance_keys=["execution_result", "result_analysis"],
                requires_coding=True,
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
                relevance_keys=["code", "execution_result", "formulas"],
                requires_coding=True,
            ),
        ]


class IEEEConferenceTemplate(PaperTemplate):
    """
    IEEE Conference 论文模板 (Systems/Security/CCF-A)

    标准 IEEE 会议结构：
    Abstract → Introduction → Related Work → Background →
    Method → Experiments → Discussion → Conclusion →
    References → Appendix
    """

    name = "ieee_conference"
    description = "IEEE 会议论文（系统/安全方向，CCF-A，英文）"

    def get_system_prompt(self) -> str:
        return """You are an expert systems/security researcher writing for a top IEEE conference.

Writing requirements:
1. Write in formal academic English following IEEE style
2. Use IEEE citation format [1], [2], etc.
3. Clearly state research questions and hypotheses upfront
4. Provide detailed threat models for security papers
5. Include formal security proofs or game-based reductions when applicable
6. Benchmark on standard datasets with realistic threat models
7. Discuss practical deployment considerations
8. Total paper length: 10-12 pages (IEEE two-column format)
9. Follow IEEE conference template (IEEEtran.cls)
10. Include a clear ethics statement for security/privacy work"""

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
                title="I. Introduction",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=1800,
                relevance_keys=["problem_text", "analysis", "method_summary"],
            ),
            ChapterSpec(
                id="related_work",
                title="II. Related Work",
                level=1,
                min_chars=600,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="background",
                title="III. Background",
                level=1,
                min_chars=600,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["problem_text", "modeling", "formulas"],
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
            ),
        ]


class ACMSigConfTemplate(PaperTemplate):
    """
    ACM SIGCONF 论文模板 (Graphics/Networking/CCF-A)

    标准 ACM 会议结构：
    Abstract → Introduction → Related Work → Method →
    Implementation → Evaluation → Discussion → Conclusion →
    References → Appendix
    """

    name = "acm_sigconf"
    description = "ACM SIGCONF 会议论文（图形/网络方向，CCF-A，英文）"

    def get_system_prompt(self) -> str:
        return """You are an expert researcher writing for a top ACM conference (SIGGRAPH, SIGCOMM, etc.).

Writing requirements:
1. Write in formal academic English following ACM style
2. Use ACM citation format (numeric [1] or author-year)
3. Include detailed system/architecture diagrams description
4. Provide algorithmic complexity analysis (time and space)
5. Report experiments on standard benchmarks with multiple metrics
6. Include qualitative and quantitative results
7. Discuss limitations and future work candidly
8. Total paper length: 10-14 pages (ACM sigconf template)
9. Follow ACM formatting guidelines (acmart.cls, sigconf option)
10. Include artifact description for reproducibility"""

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
                min_chars=600,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["problem_text", "analysis"],
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


# 模板注册表
_TEMPLATE_REGISTRY = {
    "math_modeling": MathModelingTemplate,
    "coursework": CourseworkTemplate,
    "financial_analysis": FinancialAnalysisTemplate,
    "neurips_2024": NeurIPS2024Template,
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
