"""
通用论文整合器
=============

将各问题的论文部分整合为完整论文
按照cumcmthesis.cls格式输出
"""

from typing import Dict
from pathlib import Path


def merge_generic_sections(
    work_units: Dict,
    title: str = "数学建模论文",
    authors: str = "数学建模团队",
    affiliation: str = "某某大学数学与统计学院"
) -> str:
    """
    整合所有问题的论文部分为完整论文（通用模板）

    论文结构（按cumcmthesis格式）：
    1. 承诺书
    2. 摘要
    3. 各问题论文部分
    4. 参考文献
    5. 附录
    """

    parts = []

    # 1. 承诺书
    parts.append(_build_commitment())

    # 2. 摘要
    parts.append(_build_abstract(work_units))

    # 3. 各问题论文部分
    for unit in work_units.values():
        if unit.paper_section:
            parts.append(unit.paper_section)

    # 4. 参考文献
    parts.append(_build_references())

    # 5. 附录
    parts.append(_build_appendix())

    # 合并
    full_paper = "\n\n".join(parts)

    return full_paper


def _build_commitment() -> str:
    """构建承诺书"""
    return """## 承诺书

我们仔细阅读了《全国大学生数学建模竞赛章程》和《全国大学生数学建模竞赛参赛规则》。我们完全清楚，在竞赛开始后参赛队员不能以任何方式与队外的任何人交流、讨论与赛题有关的问题。我们完全清楚，必须合法合规地使用文献资料和软件工具。我们以中国大学生名誉和诚信郑重承诺，严格遵守竞赛章程和参赛规则。

**参赛报名队号**：XXXXXX

**参赛选择题号**：X

**参赛学校**：某某大学

**参赛队员**：张三、李四、王五

**指导教师**：某某教授

---

"""


def _build_abstract(work_units: Dict) -> str:
    """构建摘要"""

    # 收集各问题的关键结果
    problem_summaries = []
    for unit in work_units.values():
        problem_type = unit.model_result.get('problem_type', '分析')
        problem_name = unit.problem_name

        # 尝试获取求解结果
        solve_result = unit.solve_result
        if solve_result and solve_result.get('status') == 'success':
            problem_summaries.append(f"{problem_name}已求解")
        else:
            problem_summaries.append(f"{problem_name}已完成建模")

    summary_text = "；".join(problem_summaries)

    return f"""
## 摘要

**研究背景**：数学建模是解决实际工程和科学问题的重要方法。本论文针对多个相关问题建立数学模型并进行求解。

**研究方法**：通过对问题进行分析，建立数学模型，设计算法进行求解，并对结果进行验证分析。

**研究内容**：
{summary_text}。

**研究结论**：通过本论文的研究，验证了所建立模型的有效性和算法的可行性。

**关键词**：数学建模；优化；预测；分析；算法设计

---

## Abstract

**Background**: Mathematical modeling is an important approach for solving practical engineering and scientific problems. This paper establishes mathematical models and solves several related problems.

**Methods**: Through problem analysis, we establish mathematical models, design algorithms for solutions, and validate the results.

**Results**: {summary_text}.

**Conclusions**: The research validates the effectiveness of the proposed models and algorithms.

**Keywords**: Mathematical Modeling; Optimization; Prediction; Analysis; Algorithm Design
"""


def _build_references() -> str:
    """构建参考文献"""
    return """
---

## 参考文献

[1] 全国大学生数学建模竞赛组委会. 全国大学生数学建模竞赛章程[S]. 2024.

[2] 姜启源, 谢金星, 叶俊. 数学模型(第五版)[M]. 北京: 高等教育出版社, 2018.

[3] 司守奎, 孙玺菁. 数学建模算法与应用(第三版)[M]. 北京: 国防工业出版社, 2021.

[4] 王小东, 等. 优化理论与算法[M]. 北京: 清华大学出版社, 2019.

[5] Ross S M. 概率论与数理统计[M]. 贾乃光, 译. 北京: 中国统计出版社, 2019.

[6] Johnson R A, Wichern D W. 实用多元统计分析[M]. 陆璇, 译. 北京: 清华大学出版社, 2018.

[7] 张文修, 梁怡. 不确定性数学方法研究[M]. 北京: 科学出版社, 2020.

[8] 李德毅, 于剑. 人工智能导论[M]. 北京: 中国科学技术大学出版社, 2018.

[9] Bishop C M. Pattern Recognition and Machine Learning[M]. Springer, 2006.

[10] Hastie T, Tibshirani R, Friedman J. The Elements of Statistical Learning[M]. Springer, 2009.
"""


def _build_appendix() -> str:
    """构建附录"""
    return """
---

## 附录

### 附录A：工作目录结构

各问题的工作成果保存在 `work/` 目录下：

```
work/
├── problem_1/
│   ├── analysis/    # 问题分析
│   ├── modeling/    # 数学模型
│   ├── solving/     # 求解代码
│   ├── visual/      # 可视化代码
│   └── paper/       # 论文部分
├── problem_2/
│   └── ...
├── problem_3/
│   └── ...
└── final/           # 最终论文
    └── Final_Paper.md
```

### 附录B：主要代码

主要求解代码位于各问题的 `solving/` 子目录中。

### 附录C：原始数据

原始数据文件位于项目根目录的附件文件中。
"""
