"""
论文模板系统
============

支持多种论文类型的通用模板：
- 数学建模论文 (Math Modeling)
- 课程作业论文 (Coursework)
- 金融分析论文 (Financial Analysis)

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
8. 使用学术中文写作风格，术语准确"""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(
                id="abstract",
                title="摘要",
                level=1,
                min_chars=400,
                target_chars=600,
                max_chars=1000,
                relevance_keys=["problem_text", "analysis", "modeling", "execution_result", "result_analysis"],
            ),
            ChapterSpec(
                id="problem_restated",
                title="一、问题重述",
                level=1,
                min_chars=800,
                target_chars=1200,
                max_chars=2000,
                relevance_keys=["problem_text", "analysis"],
            ),
            ChapterSpec(
                id="problem_analysis",
                title="二、问题分析",
                level=1,
                min_chars=1500,
                target_chars=2500,
                max_chars=4000,
                relevance_keys=["problem_text", "analysis", "sub_problems"],
            ),
            ChapterSpec(
                id="assumptions",
                title="三、模型假设",
                level=1,
                min_chars=600,
                target_chars=1000,
                max_chars=1500,
                relevance_keys=["analysis", "modeling"],
            ),
            ChapterSpec(
                id="notations",
                title="四、符号说明",
                level=1,
                min_chars=400,
                target_chars=800,
                max_chars=1200,
                relevance_keys=["modeling"],
            ),
            ChapterSpec(
                id="model_establishment",
                title="五、模型的建立",
                level=1,
                min_chars=2500,
                target_chars=4000,
                max_chars=6000,
                relevance_keys=["problem_text", "analysis", "modeling", "formulas"],
            ),
            ChapterSpec(
                id="model_solution",
                title="六、模型的求解",
                level=1,
                min_chars=2000,
                target_chars=3000,
                max_chars=5000,
                relevance_keys=["algorithm", "code", "execution_result"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="result_analysis",
                title="七、结果分析",
                level=1,
                min_chars=2000,
                target_chars=3000,
                max_chars=5000,
                relevance_keys=["execution_result", "result_analysis", "charts"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="sensitivity",
                title="八、灵敏度分析",
                level=1,
                min_chars=1000,
                target_chars=1500,
                max_chars=2500,
                relevance_keys=["modeling", "execution_result", "result_analysis"],
                requires_coding=True,
            ),
            ChapterSpec(
                id="evaluation",
                title="九、模型评价与改进",
                level=1,
                min_chars=1000,
                target_chars=1500,
                max_chars=2500,
                relevance_keys=["modeling", "algorithm", "result_analysis"],
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
            ChapterSpec(
                id="appendix",
                title="附录",
                level=1,
                min_chars=300,
                target_chars=800,
                max_chars=2000,
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
6. 中文学术写作风格"""

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
                id="references",
                title="参考文献",
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


# 模板注册表
_TEMPLATE_REGISTRY = {
    "math_modeling": MathModelingTemplate,
    "coursework": CourseworkTemplate,
    "financial_analysis": FinancialAnalysisTemplate,
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
