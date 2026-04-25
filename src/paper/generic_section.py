"""
通用论文章节撰写器
================

按照cumcmthesis.cls格式撰写各问题的论文部分

特点：
- 中文标题格式：一、问题一、二、三...
- 二级标题格式：1.1, 1.2
- 公式使用LaTeX格式
- 表格使用Markdown格式
"""

from typing import Dict, Any
from workflow import WorkUnit


def write_generic_section(unit: WorkUnit) -> str:
    """
    撰写单个问题的论文部分（通用模板）

    根据问题类型生成对应的论文章节
    """
    problem_id = unit.problem_id
    problem_name = unit.problem_name
    problem_type = unit.model_result.get('problem_type', 'analysis')
    keywords = unit.analysis_result.get('keywords', [])

    # 根据问题编号确定章节号
    problem_num = int(problem_id.split('_')[1]) if '_' in problem_id else 1
    section_prefix = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"][problem_num - 1]

    # 根据问题类型生成不同的模型描述
    if problem_type == 'measurement':
        return _write_measurement_section(unit, section_prefix, problem_num)
    elif problem_type == 'optimization':
        return _write_optimization_section(unit, section_prefix, problem_num)
    else:
        return _write_generic_model_section(unit, section_prefix, problem_num)


def _write_measurement_section(unit: WorkUnit, section_prefix: str, problem_num: int) -> str:
    """撰写测量类问题的论文部分"""

    model = unit.model_result
    solve_result = unit.solve_result

    # 获取厚度值（如果有）
    thickness = "待计算"
    if 'thickness' in str(solve_result):
        thickness = f"{solve_result.get('thickness', 0):.2f} μm"

    return f"""
## {section_prefix}、{unit.problem_name}

### {problem_num}.1 问题分析

#### {problem_num}.1.1 问题背景

本题要求对物理量进行精确测量。FTIR干涉光谱法是一种非接触、高精度的测量方法，适用于半导体外延层厚度测量。

#### {problem_num}.1.2 测量原理

当红外光垂直入射到样品表面时，在各界面发生反射。两束反射光具有光程差：

$$\\Delta = 2nd$$

其中 $n$ 为折射率，$d$ 为厚度。

干涉条件：

$$2nd\\sigma = m$$

条纹间距与厚度的关系：

$$d = \\frac{{10^4}}{{2n\\Delta\\sigma}} \\; \\mu m$$

### {problem_num}.2 模型建立

#### {problem_num}.2.1 变量定义

| 变量 | 符号 | 说明 | 单位 |
|------|------|------|------|
| 波数 | $\\sigma$ | 红外光波数 | cm⁻¹ |
| 条纹间距 | $\\Delta\\sigma$ | 相邻干涉极大值间距 | cm⁻¹ |
| 折射率 | $n$ | 材料折射率 | - |
| 厚度 | $d$ | 待测量 | μm |

#### {problem_num}.2.2 假设条件

1. 红外光垂直入射
2. 测量区域无明显吸收
3. 层厚均匀一致
4. 忽略多次反射

### {problem_num}.3 求解算法

#### {problem_num}.3.1 算法流程

```
输入：光谱数据 (波数, 反射率)
    ↓
数据预处理（平滑滤波）
    ↓
峰/谷检测
    ↓
计算条纹间距
    ↓
厚度计算
    ↓
输出：测量结果
```

#### {problem_num}.3.2 参数选择

- 平滑窗口：31点
- 峰检测距离阈值：30 cm⁻¹
- 峰显著性阈值：2.0%

### {problem_num}.4 结果分析

测量结果：{thickness}

测量不确定度主要来源于：
1. 条纹间距测量不确定度
2. 折射率不确定度

### {problem_num}.5 结论

本节完成了测量问题的建模与求解，建立了干涉光谱测量模型，设计了相应的求解算法。
"""


def _write_optimization_section(unit: WorkUnit, section_prefix: str, problem_num: int) -> str:
    """撰写优化类问题的论文部分"""

    return f"""
## {section_prefix}、{unit.problem_name}

### {problem_num}.1 问题分析

#### {problem_num}.1.1 问题背景

本问题是一个优化问题，需要在给定约束条件下找到最优决策。

#### {problem_num}.1.2 问题要求

1. 确定决策变量
2. 建立目标函数
3. 识别约束条件
4. 求解最优解

### {problem_num}.2 模型建立

#### {problem_num}.2.1 决策变量

设决策变量为 $x = (x_1, x_2, ..., x_n)$

#### {problem_num}.2.2 目标函数

$$\\min / \\max \\; f(x) = f(x_1, x_2, ..., x_n)$$

#### {problem_num}.2.3 约束条件

$$g_i(x) \\leq 0, \\quad i = 1, 2, ..., m$$

$$h_j(x) = 0, \\quad j = 1, 2, ..., p$$

### {problem_num}.3 求解方法

根据问题特点，可采用以下方法：
- 线性规划
- 非线性规划
- 整数规划
- 动态规划

### {problem_num}.4 结论

本节完成了优化问题的建模，确立了目标函数和约束条件。
"""


def _write_generic_model_section(unit: WorkUnit, section_prefix: str, problem_num: int) -> str:
    """撰写通用模型的论文部分"""

    return f"""
## {section_prefix}、{unit.problem_name}

### {problem_num}.1 问题分析

本问题需要进行数学建模分析。

#### {problem_num}.1.1 问题描述

根据题目要求建立数学模型。

#### {problem_num}.1.2 研究目标

建立能准确描述问题本质的数学模型。

### {problem_num}.2 模型假设

1. 假设一
2. 假设二
3. 假设三

### {problem_num}.3 模型建立

#### {problem_num}.3.1 变量说明

| 变量 | 符号 | 说明 |
|------|------|------|
| 变量1 | $x_1$ | 说明1 |
| 变量2 | $x_2$ | 说明2 |

#### {problem_num}.3.2 数学公式

建立如下数学关系：

$$y = f(x; \\theta)$$

其中 $\\theta$ 为模型参数。

### {problem_num}.4 模型求解

采用数值方法或解析方法进行求解。

### {problem_num}.5 结论

本节完成了问题的数学建模工作。
"""
